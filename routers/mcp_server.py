"""
MCP (Model Context Protocol) server exposing read-only project data and code to
Claude.ai via Connectors. Mounted on the FastAPI app at /mcp.

Tools:
- list_projects()                    → summary of all projects in the DB
- get_project(project_id)            → project + floors
- get_floor(floor_id)                → floor + elements (the full stored payload)
- read_backend_file(path, ref?)      → file from Fire-Dynamics-Group/backendForNextApp
- read_frontend_file(path, ref?)     → file from Fire-Dynamics-Group/upload-canvas
- search_code(query, repo?)          → GitHub code search across both repos

Auth: Authorization: Bearer $MCP_BEARER_TOKEN on every request to /mcp.
GitHub reads use $GH_TOKEN (PAT with `repo:read`).
"""

from __future__ import annotations

import base64
import contextlib
import os
from typing import Any, Literal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import ASGIApp

from database import async_session
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from models.db_models import Floor, Project


MCP_BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
BACKEND_REPO = os.environ.get("MCP_BACKEND_REPO", "Fire-Dynamics-Group/backendForNextApp")
FRONTEND_REPO = os.environ.get("MCP_FRONTEND_REPO", "Fire-Dynamics-Group/upload-canvas")
BACKEND_DEFAULT_REF = os.environ.get("MCP_BACKEND_REF", "feature/fire-config")
FRONTEND_DEFAULT_REF = os.environ.get("MCP_FRONTEND_REF", "main")


mcp = FastMCP(
    "upload-canvas",
    instructions=(
        "Read-only access to the upload-canvas FDS generator: project data from "
        "the Railway Postgres DB and source code from GitHub. Use list_projects "
        "to discover projects, get_floor to pull the real stored element JSON "
        "(polygons, doors, zones) for a given floor, and read_*_file / "
        "search_code to inspect source across the two repos."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


# --- DB tools ---------------------------------------------------------------


def _require_db():
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured on the backend")


@mcp.tool()
async def list_projects() -> list[dict[str, Any]]:
    """List every project in the DB with id, name, floor count, updated_at."""
    _require_db()
    async with async_session() as db:
        result = await db.execute(
            select(Project)
            .options(selectinload(Project.floors))
            .order_by(Project.updated_at.desc())
        )
        projects = result.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "floor_count": len(p.floors),
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "created_by": p.created_by,
            }
            for p in projects
        ]


@mcp.tool()
async def get_project(project_id: str) -> dict[str, Any]:
    """Get a project with its settings and list of floors (no elements)."""
    _require_db()
    async with async_session() as db:
        result = await db.execute(
            select(Project)
            .where(Project.id == UUID(project_id))
            .options(selectinload(Project.floors))
        )
        p = result.scalar_one_or_none()
        if not p:
            raise ValueError(f"Project {project_id} not found")
        return {
            "id": str(p.id),
            "name": p.name,
            "settings": p.settings,
            "created_by": p.created_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "floors": [
                {
                    "id": str(f.id),
                    "floor_number": f.floor_number,
                    "name": f.name,
                    "pixels_per_mesh": f.pixels_per_mesh,
                    "origin_pixels": f.origin_pixels,
                    "canvas_dimensions": f.canvas_dimensions,
                    "settings": f.settings,
                }
                for f in sorted(p.floors, key=lambda f: f.floor_number)
            ],
        }


@mcp.tool()
async def get_floor(floor_id: str) -> dict[str, Any]:
    """Get a floor with every stored element (obstructions, doors, zones, points). Polygons are in frontend pixel space; backend applies Y-flip + px_per_m at FDS-gen time."""
    _require_db()
    async with async_session() as db:
        result = await db.execute(
            select(Floor)
            .where(Floor.id == UUID(floor_id))
            .options(selectinload(Floor.elements))
        )
        f = result.scalar_one_or_none()
        if not f:
            raise ValueError(f"Floor {floor_id} not found")
        return {
            "id": str(f.id),
            "project_id": str(f.project_id),
            "floor_number": f.floor_number,
            "name": f.name,
            "pixels_per_mesh": f.pixels_per_mesh,
            "origin_pixels": f.origin_pixels,
            "canvas_dimensions": f.canvas_dimensions,
            "settings": f.settings,
            "elements": [
                {
                    "id": str(e.id),
                    "index": e.element_index,
                    "type": e.type,
                    "points": e.points,
                    "comments": e.comments,
                }
                for e in sorted(f.elements, key=lambda e: e.element_index)
            ],
        }


# --- GitHub tools -----------------------------------------------------------


async def _gh_get_file(repo: str, path: str, ref: str) -> str:
    if not GH_TOKEN:
        raise RuntimeError("GH_TOKEN not configured — cannot read GitHub files")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers, params={"ref": ref})
        if r.status_code == 404:
            raise ValueError(f"{repo}:{ref} has no file at {path}")
        r.raise_for_status()
        data = r.json()
    if isinstance(data, list):
        raise ValueError(
            f"{path} is a directory; pass a file path. Entries: "
            + ", ".join(item["name"] for item in data[:50])
        )
    if data.get("encoding") != "base64":
        raise RuntimeError(f"Unexpected encoding: {data.get('encoding')}")
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


@mcp.tool()
async def read_backend_file(path: str, ref: str | None = None) -> str:
    """Read a file from the FastAPI backend repo. `path` is repo-root-relative."""
    return await _gh_get_file(BACKEND_REPO, path, ref or BACKEND_DEFAULT_REF)


@mcp.tool()
async def read_frontend_file(path: str, ref: str | None = None) -> str:
    """Read a file from the upload-canvas frontend repo. `path` is repo-root-relative."""
    return await _gh_get_file(FRONTEND_REPO, path, ref or FRONTEND_DEFAULT_REF)


@mcp.tool()
async def search_code(
    query: str,
    repo: Literal["backend", "frontend", "both"] = "both",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search code via GitHub code-search across backend, frontend, or both repos. Returns list of {repo, path, fragments, url} — fragments are short snippet strings around each match."""
    if not GH_TOKEN:
        raise RuntimeError("GH_TOKEN not configured")
    repos = {
        "backend": [BACKEND_REPO],
        "frontend": [FRONTEND_REPO],
        "both": [BACKEND_REPO, FRONTEND_REPO],
    }[repo]
    qualifier = " ".join(f"repo:{r}" for r in repos)
    q = f"{query} {qualifier}"
    url = "https://api.github.com/search/code"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github.text-match+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers, params={"q": q, "per_page": max_results})
        r.raise_for_status()
        data = r.json()
    out = []
    for item in data.get("items", []):
        out.append({
            "repo": item["repository"]["full_name"],
            "path": item["path"],
            "fragments": [m.get("fragment", "") for m in item.get("text_matches", [])],
            "url": item.get("html_url"),
        })
    return out


# --- Auth + mounting --------------------------------------------------------


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not MCP_BEARER_TOKEN:
            return JSONResponse(
                {"error": "MCP_BEARER_TOKEN not set on server"}, status_code=503
            )
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)
        if auth[len("Bearer ") :].strip() != MCP_BEARER_TOKEN:
            return JSONResponse({"error": "bad token"}, status_code=401)
        return await call_next(request)


def build_mcp_asgi_app() -> ASGIApp:
    """
    Return an ASGI app that serves the MCP streamable-HTTP endpoint at /
    (so mounting it at /mcp on the parent app gives you POST /mcp).
    Bearer-token protected.
    """
    inner = mcp.streamable_http_app()
    app = Starlette(routes=[Mount("/", app=inner)])
    app.add_middleware(BearerTokenMiddleware)
    return app


@contextlib.asynccontextmanager
async def mcp_lifespan(app):
    """FastAPI lifespan context that runs the MCP session manager."""
    async with mcp.session_manager.run():
        yield
