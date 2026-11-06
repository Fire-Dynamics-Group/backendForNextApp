"""Pydantic schemas for the i-macs <-> upload-canvas MACS link and run history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MACS_SCHEMA_1 = "fd-macs-reliability/1"
MACS_SCHEMA_2 = "fd-macs-reliability/2"

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MacsRunCreate(BaseModel):
    """Upload wrapper for a MACS+ run: envelope + metadata."""

    model_config = ConfigDict(extra="forbid")

    schema_: Literal["fd-macs-reliability/1", "fd-macs-reliability/2"] = Field(
        alias="schema"
    )
    critical_temp: float = Field(gt=0, le=1200, strict=True)
    governing_side: Literal["A", "B", "C", "D"]
    section: NonEmptyStr
    exposure: Literal["3-sided", "4-sided"]
    section_factor: float = Field(gt=0, le=1000, strict=True)
    windows_user: NonEmptyStr
    client_timestamp: datetime
    machine_name: str | None = None
    client_version: str | None = None
    run_id: str | None = None
    label: str | None = None
    project_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    time_series: list[dict[str, Any]] = Field(default_factory=list)
    imacs_job_id: str | None = None
    macs_batch: dict[str, Any] | None = None


# Backwards compat alias
MacsResultCreate = MacsRunCreate


class MacsRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    project_id: uuid.UUID | None = None
    schema_: str = Field(alias="schema")
    critical_temp: float
    section_factor: float
    governing_side: str
    section: str
    exposure: str
    windows_user: str
    machine_name: str | None = None
    client_timestamp: datetime
    client_version: str | None = None
    run_id: str | None = None
    label: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    time_series: list[dict[str, Any]] = Field(default_factory=list)
    imacs_job_id: str | None = None
    macs_batch: dict[str, Any] | None = None
    received_at: datetime


# Backwards compat alias
MacsResultOut = MacsRunOut


class MacsHandoffResponse(BaseModel):
    handoff_id: uuid.UUID
    expires_at: datetime


class MacsHandoffDetail(BaseModel):
    handoff_id: uuid.UUID
    expires_at: datetime
    created_at: datetime
    imacs_job_id: str | None = None
    run: MacsRunOut


class ImacsJobLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID


class ImacsJobLinkOut(BaseModel):
    imacs_job_id: str
    project_id: uuid.UUID
    linked: bool = True


class ImacsJobSummary(BaseModel):
    project_id: uuid.UUID
    project_name: str
    last_sent_at: datetime | None = None
    outcome: dict[str, Any] | None = None


class ImacsProjectOut(BaseModel):
    """Minimal project projection for the i-macs project picker."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    mode: str
    updated_at: datetime | None = None
