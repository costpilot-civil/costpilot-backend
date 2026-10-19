"""HTTP schemas only; business entities come from costpilot_core."""

from decimal import Decimal

from pydantic import BaseModel


class CommodityResponse(BaseModel):
    id: int
    code: str
    description: str | None
    unit: str | None
    category_path: str


class CandidateResponse(BaseModel):
    commodity: CommodityResponse
    score: float


class ItemMatchResponse(BaseModel):
    position_id: int
    oz: str
    short_text: str
    status: str
    commodity_id: int | None
    candidates: list[CandidateResponse]


class RunMatchingResponse(BaseModel):
    project_id: int
    tender_id: int
    results: list[ItemMatchResponse]


class StoredMatchResponse(BaseModel):
    position_id: int
    oz: str
    short_text: str
    status: str
    commodity_id: int | None
    commodity_code: str | None
    commodity_description: str | None
    score: Decimal | None
