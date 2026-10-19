from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from costpilot_core.models.tender.tender import ParsedTender, TenderItem


@dataclass(frozen=True, slots=True)
class TenderDocument:
    id: int
    project_id: int
    file_name: str
    file_type: str
    file_hash: str | None
    status: str
    parsed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TenderPositionReference:
    position_id: int
    path: tuple[int, ...]


@dataclass(slots=True)
class TenderDetail:
    document: TenderDocument
    structure: ParsedTender
    positions: list[TenderPositionReference]


@dataclass(frozen=True, slots=True)
class TenderItemRecord:
    position_id: int
    item: TenderItem
