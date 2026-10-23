from datetime import datetime
from typing import Any

from costpilot_core.models.tender.tender import ParsedTender, TenderItem
from pydantic import BaseModel, ConfigDict


class TenderDocumentResponse(BaseModel):
    id: int
    project_id: int
    file_name: str
    file_type: str
    file_hash: str | None
    status: str
    parsed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenderPositionReferenceResponse(BaseModel):
    position_id: int
    path: tuple[int, ...]

    model_config = ConfigDict(from_attributes=True)


class TenderDetailResponse(BaseModel):
    document: TenderDocumentResponse
    structure: ParsedTender
    positions: list[TenderPositionReferenceResponse]

    model_config = ConfigDict(from_attributes=True)


class TenderItemRecordResponse(BaseModel):
    position_id: int
    item: TenderItem

    model_config = ConfigDict(from_attributes=True)


class ExtractedMaterialResponse(BaseModel):
    material_type: str
    core_attributes: dict[str, Any]
    supplementary_attributes: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class PositionAttributesResponse(BaseModel):
    position_id: int
    extracted_material: ExtractedMaterialResponse | None
