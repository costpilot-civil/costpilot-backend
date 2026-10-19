from costpilot_core.parsers.gaeb_tender_parser import GAEBTenderParser
from fastapi import Request

from app.application.project_service import ProjectService
from app.application.tender_service import TenderService
from app.persistence.project_repository import ProjectRepository
from app.persistence.tender_repository import TenderRepository


def get_project_service(request: Request) -> ProjectService:
    # Keep the existing Project API dependency.
    return ProjectService(ProjectRepository(request.app.state.db_pool))


def get_tender_service(request: Request) -> TenderService:
    return TenderService(
        repository=TenderRepository(request.app.state.db_pool),
        parser=GAEBTenderParser(),
        max_upload_bytes=request.app.state.settings.tender_max_upload_bytes,
    )
