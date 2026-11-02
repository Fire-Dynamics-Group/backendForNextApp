"""Pydantic schemas for the i-macs -> upload-canvas MACS results hand-off.

The envelope follows i-macs issue #48 ("fd-macs-reliability/1"). Everything is
`extra="forbid"`: an unknown field or schema version is a 422, never silently
dropped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MACS_SCHEMA = "fd-macs-reliability/1"

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MacsEnvelope(BaseModel):
    """The i-macs reliability envelope, exactly as the sidecar emits it."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    # `schema` shadows a BaseModel attribute, so the field is `schema_` with the
    # wire name `schema`.
    schema_: Literal["fd-macs-reliability/1"] = Field(alias="schema")
    # Governing (lowest) perimeter-beam critical temperature, degC.
    critical_temp: float = Field(gt=0, le=1200, strict=True)
    governing_side: Literal["A", "B", "C", "D"]
    section: NonEmptyStr
    exposure: Literal["3-sided", "4-sided"]
    # Ap/V in 1/m.
    section_factor: float = Field(gt=0, le=1000, strict=True)


class MacsResultCreate(MacsEnvelope):
    """Upload wrapper: the envelope plus client-supplied metadata."""

    windows_user: NonEmptyStr
    client_timestamp: datetime
    client_version: str | None = None
    run_id: str | None = None
    label: str | None = None


ENVELOPE_FIELDS = frozenset(MacsEnvelope.model_fields)


class MacsResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    envelope: dict[str, Any]
    critical_temp: float
    section_factor: float
    governing_side: str
    section: str
    exposure: str
    windows_user: str
    client_timestamp: datetime
    client_version: str | None = None
    run_id: str | None = None
    label: str | None = None
    received_at: datetime


class ImacsProjectOut(BaseModel):
    """Minimal project projection for the i-macs project picker."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    mode: str
    updated_at: datetime | None = None
