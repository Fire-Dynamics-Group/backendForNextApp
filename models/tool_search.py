"""Tool-search analytics models (email-search search_logs + search_clicks)."""

import uuid
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, DateTime, Integer, Text, Uuid
from sqlalchemy import JSON as JSONB

from database import Base
from models.db_models import utcnow


class ToolSearchLog(Base):
    __tablename__ = "tool_search_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    client_search_id = Column(Uuid, nullable=False, index=True)
    query = Column(Text, nullable=False)
    query_normalized = Column(Text, nullable=False, default="")
    result_count = Column(Integer, nullable=False, default=0)
    top_ids = Column(JSONB, nullable=False, default=list)
    suggestion_id = Column(Text, nullable=True)
    confidence = Column(Text, nullable=True)
    mode = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    anon_id = Column(Text, nullable=True, default="")
    user_id = Column(Text, nullable=True)
    user_email = Column(Text, nullable=True)
    source = Column(Text, nullable=False, default="toolstation-home")


class ToolSearchClick(Base):
    __tablename__ = "tool_search_clicks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    client_search_id = Column(Uuid, nullable=False, index=True)
    part_id = Column(Text, nullable=False)
    rank = Column(Integer, nullable=False, default=0)
    anon_id = Column(Text, nullable=True, default="")
    user_id = Column(Text, nullable=True)
    user_email = Column(Text, nullable=True)
    source = Column(Text, nullable=False, default="toolstation-home")


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ToolSearchLogIn(CamelModel):
    client_search_id: uuid.UUID
    query: str
    query_normalized: str = ""
    result_count: int = 0
    top_ids: List[Any] = []
    suggestion_id: Optional[str] = None
    confidence: Optional[str] = None
    mode: Optional[str] = None
    latency_ms: Optional[int] = None
    anon_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    source: str = "toolstation-home"
    ts: Optional[str] = None


class ToolSearchClickIn(CamelModel):
    client_search_id: uuid.UUID
    part_id: str
    rank: int = 0
    anon_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    source: str = "toolstation-home"
    ts: Optional[str] = None
