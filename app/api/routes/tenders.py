from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status

from app.api.dependencies import get_tender_service
from app.api.schemas.tender import (
    ExtractedMaterialResponse,
    PositionAttributesResponse,
    TenderDetailResponse,
    TenderDocumentResponse,
    TenderItemRecordResponse,
)
from app.application.tender_service import (
    InvalidTenderError,
    MaterialExtractionError,
    TenderItemNotFoundError,
    TenderService,
    TenderTooLargeError,
    UnsupportedTenderError,
)
from app.persistence.tender_repository import ProjectNotFoundError

router = APIRouter(prefix="/projects/{project_id}/tenders", tags=["Tenders"])
TenderServiceDep = Annotated[TenderService, Depends(get_tender_service)]
ProjectId = Annotated[int, Path(gt=0)]
TenderId = Annotated[int, Path(gt=0)]


@router.post(
    "", response_model=TenderDocumentResponse, status_code=status.HTTP_201_CREATED
)
def import_tender(
    project_id: ProjectId,
    file: Annotated[UploadFile, File()],
    service: TenderServiceDep,
) -> TenderDocumentResponse:
    try:
        document = service.import_tender(
            project_id=project_id, file_name=file.filename, stream=file.file
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedTenderError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except TenderTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except InvalidTenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TenderDocumentResponse.model_validate(document)


@router.get("", response_model=list[TenderDocumentResponse])
def list_tenders(
    project_id: ProjectId,
    service: TenderServiceDep,
) -> list[TenderDocumentResponse]:
    try:
        documents = service.list_tenders(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [TenderDocumentResponse.model_validate(doc) for doc in documents]


@router.get("/{tender_id}", response_model=TenderDetailResponse)
def get_tender(
    project_id: ProjectId,
    tender_id: TenderId,
    service: TenderServiceDep,
) -> TenderDetailResponse:
    detail = service.get_tender(project_id=project_id, tender_id=tender_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Tender not found.")
    return TenderDetailResponse.model_validate(detail)


@router.get("/{tender_id}/items", response_model=list[TenderItemRecordResponse])
def list_items(
    project_id: ProjectId,
    tender_id: TenderId,
    service: TenderServiceDep,
) -> list[TenderItemRecordResponse]:
    items = service.list_items(project_id=project_id, tender_id=tender_id)
    if items is None:
        raise HTTPException(status_code=404, detail="Tender not found.")
    return [TenderItemRecordResponse.model_validate(record) for record in items]


@router.get(
    "/{tender_id}/items/{position_id}/attributes",
    response_model=PositionAttributesResponse,
)
def get_position_attributes(
    project_id: ProjectId,
    tender_id: TenderId,
    position_id: Annotated[int, Path(gt=0)],
    service: TenderServiceDep,
) -> PositionAttributesResponse:
    try:
        extracted = service.extract_position_attributes(
            project_id=project_id,
            tender_id=tender_id,
            position_id=position_id,
        )
    except TenderItemNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except MaterialExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return PositionAttributesResponse(
        position_id=position_id,
        extracted_material=(
            ExtractedMaterialResponse.model_validate(extracted)
            if extracted is not None
            else None
        ),
    )
