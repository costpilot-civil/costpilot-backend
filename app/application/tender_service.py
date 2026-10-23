import hashlib
import tempfile
from pathlib import Path
from typing import BinaryIO
from xml.etree.ElementTree import ParseError

from costpilot_core.material.material_extractor import MaterialExtractor
from costpilot_core.models.material.extracted_material import ExtractedMaterial
from costpilot_core.parsers.gaeb_tender_parser import GAEBTenderParser
from costpilot_core.text.text_builder import TextBuilder
from defusedxml.common import DefusedXmlException

from app.domain.tender import TenderDetail, TenderDocument, TenderItemRecord
from app.persistence.tender_repository import ProjectNotFoundError, TenderRepository


class InvalidTenderError(Exception):
    pass


class UnsupportedTenderError(Exception):
    pass


class TenderTooLargeError(Exception):
    pass


class TenderItemNotFoundError(Exception):
    pass


class MaterialExtractionError(Exception):
    pass


class TenderService:
    ALLOWED_EXTENSIONS = frozenset({".xml", ".x83", ".x84", ".x86"})
    CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        *,
        repository: TenderRepository,
        parser: GAEBTenderParser,
        max_upload_bytes: int,
        material_extractor: MaterialExtractor,
    ) -> None:
        self._repository = repository
        self._parser = parser
        self._max_upload_bytes = max_upload_bytes
        self._material_extractor = material_extractor

    def import_tender(
        self, *, project_id: int, file_name: str | None, stream: BinaryIO
    ) -> TenderDocument:
        if not self._repository.project_exists(project_id):
            raise ProjectNotFoundError("Project not found.")

        filename = self._validate_filename(file_name)
        suffix = Path(filename).suffix.lower()

        with tempfile.TemporaryDirectory(prefix="costpilot_tender_") as directory:
            temp_path = Path(directory) / f"upload{suffix}"
            file_hash = self._copy_upload_and_hash(stream, temp_path)

            try:
                structure = self._parser.parse(temp_path)
            except (ParseError, DefusedXmlException, UnicodeError, ValueError) as exc:
                raise InvalidTenderError(
                    "Invalid or unsupported GAEB/XML Tender."
                ) from exc

            if not structure.nodes:
                raise InvalidTenderError("Tender has no supported nodes.")

            try:
                return self._repository.create_tender(
                    project_id=project_id,
                    file_name=filename,
                    file_hash=file_hash,
                    structure=structure,
                )
            except ValueError as exc:
                raise InvalidTenderError(str(exc)) from exc

    def list_tenders(self, project_id: int) -> list[TenderDocument]:
        if not self._repository.project_exists(project_id):
            raise ProjectNotFoundError("Project not found.")
        return self._repository.list_tenders(project_id)

    def get_tender(self, *, project_id: int, tender_id: int) -> TenderDetail | None:
        return self._repository.get_tender(project_id=project_id, tender_id=tender_id)

    def list_items(
        self, *, project_id: int, tender_id: int
    ) -> list[TenderItemRecord] | None:
        return self._repository.list_items(project_id=project_id, tender_id=tender_id)

    def extract_position_attributes(
        self,
        *,
        project_id: int,
        tender_id: int,
        position_id: int,
    ) -> ExtractedMaterial | None:
        record = self._repository.get_item(
            project_id=project_id,
            tender_id=tender_id,
            position_id=position_id,
        )

        if record is None:
            raise TenderItemNotFoundError("Tender or position not found.")

        text = TextBuilder.build_tender_item_text(record.item)

        try:
            return self._material_extractor.extract(text)
        except ValueError as exc:
            raise MaterialExtractionError(
                "Material attribute extraction is ambiguous."
            ) from exc

    @classmethod
    def _validate_filename(cls, filename: str | None) -> str:
        if not filename:
            raise UnsupportedTenderError("A file name is required.")
        basename = filename.replace("\\", "/").split("/")[-1].strip()
        if not basename or len(basename) > 255:
            raise UnsupportedTenderError("Invalid file name.")
        if Path(basename).suffix.lower() not in cls.ALLOWED_EXTENSIONS:
            raise UnsupportedTenderError(
                "Only GAEB XML (.xml, .x83, .x84, .x86) is supported."
            )
        return basename

    def _copy_upload_and_hash(self, stream: BinaryIO, path: Path) -> str:
        digest = hashlib.sha256()
        size = 0
        stream.seek(0)
        with path.open("wb") as destination:
            while chunk := stream.read(self.CHUNK_SIZE):
                size += len(chunk)
                if size > self._max_upload_bytes:
                    raise TenderTooLargeError("Tender upload exceeds the size limit.")
                destination.write(chunk)
                digest.update(chunk)
        if size == 0:
            raise InvalidTenderError("Tender upload is empty.")
        return digest.hexdigest()
