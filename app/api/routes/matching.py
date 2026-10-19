from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.api.dependencies import get_matching_service
from app.api.schemas.matching import (
    CandidateResponse,
    CommodityResponse,
    ItemMatchResponse,
    RunMatchingResponse,
    StoredMatchResponse,
)
from app.application.matching_service import MatchingService
from app.infrastructure.core_runtime import CoreUnavailableError
from app.persistence.commodity_search_repository import SearchDataUnavailableError
from app.persistence.match_repository import TenderNotFoundError

router = APIRouter(
    prefix="/projects/{project_id}/tenders/{tender_id}",
    tags=["Matching"],
)
Service = Annotated[MatchingService, Depends(get_matching_service)]
ProjectId = Annotated[int, Path(gt=0)]
TenderId = Annotated[int, Path(gt=0)]


@router.post("/match", response_model=RunMatchingResponse)
def run_matching(
    project_id: ProjectId, tender_id: TenderId, service: Service
) -> RunMatchingResponse:
    try:
        matches = service.run(project_id=project_id, tender_id=tender_id)
    except TenderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (CoreUnavailableError, SearchDataUnavailableError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return RunMatchingResponse(
        project_id=project_id,
        tender_id=tender_id,
        results=[
            ItemMatchResponse(
                position_id=match.position_id,
                oz=match.item.oz,
                short_text=match.item.short_text,
                status=match.result.status.value.upper(),
                commodity_id=(
                    match.result.commodity.id if match.result.commodity else None
                ),
                candidates=[
                    CandidateResponse(
                        commodity=CommodityResponse(
                            id=c.commodity.id,
                            code=c.commodity.code,
                            description=c.commodity.description,
                            unit=c.commodity.unit,
                            category_path=c.commodity.category_path,
                        ),
                        score=c.score,
                    )
                    for c in match.candidates
                ],
            )
            for match in matches
        ],
    )


@router.get("/matches", response_model=list[StoredMatchResponse])
def list_matches(
    project_id: ProjectId, tender_id: TenderId, service: Service
) -> list[StoredMatchResponse]:
    try:
        rows = service.list_results(project_id=project_id, tender_id=tender_id)
    except TenderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [StoredMatchResponse.model_validate(row) for row in rows]
