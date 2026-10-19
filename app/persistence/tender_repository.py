from __future__ import annotations

from decimal import Decimal
from typing import Any

from costpilot_core.models.tender.tender import ParsedTender, TenderCategory, TenderItem
from psycopg import Cursor
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from app.domain.tender import (
    TenderDetail,
    TenderDocument,
    TenderItemRecord,
    TenderPositionReference,
)


class ProjectNotFoundError(Exception):
    pass


class TenderRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def project_exists(self, project_id: int) -> bool:
        with self._pool.connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM projects WHERE id = %s;",
                (project_id,),
            )
            return cursor.fetchone() is not None

    def create_tender(
        self,
        *,
        project_id: int,
        file_name: str,
        file_hash: str,
        structure: ParsedTender,
    ) -> TenderDocument:
        # One transaction covers the document and all nested nodes.
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "SELECT id FROM projects WHERE id = %s FOR KEY SHARE;",
                (project_id,),
            )
            if cursor.fetchone() is None:
                raise ProjectNotFoundError("Project not found.")

            cursor.execute(
                """
                INSERT INTO lv_documents (
                    project_id, file_name, file_type,
                    storage_path, file_hash, status, parsed_at
                )
                VALUES (%s, %s, 'GAEB_XML', NULL, %s, 'PARSED', NOW())
                RETURNING id, project_id, file_name, file_type,
                          file_hash, status, parsed_at,
                          created_at, updated_at;
                """,
                (project_id, file_name, file_hash),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Unable to create Tender document.")
            document = TenderDocument(**row)

            self._insert_nodes(
                cursor=cursor,
                document_id=document.id,
                nodes=structure.nodes,
                category_id=None,
                level=0,
            )
            return document

    def _insert_nodes(
        self,
        *,
        cursor: Cursor[DictRow],
        document_id: int,
        nodes: list[TenderCategory | TenderItem],
        category_id: int | None,
        level: int,
    ) -> None:
        for sort_order, node in enumerate(nodes):
            if isinstance(node, TenderCategory):
                cursor.execute(
                    """
                    INSERT INTO lv_categories (
                        lv_document_id, parent_id, oz, number_part,
                        name, level, sort_order
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        document_id,
                        category_id,
                        node.oz,
                        node.number_part,
                        node.name,
                        level,
                        sort_order,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Unable to create Tender category.")
                self._insert_nodes(
                    cursor=cursor,
                    document_id=document_id,
                    nodes=node.children,
                    category_id=row["id"],
                    level=level + 1,
                )
            elif isinstance(node, TenderItem):
                self._validate_quantity(node.quantity)
                cursor.execute(
                    """
                    INSERT INTO lv_positions (
                        lv_document_id, parent_id, category_id,
                        oz, positionsnummer, kurztext, langtext,
                        menge, einheit, level, sort_order
                    )
                    VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        document_id,
                        category_id,
                        node.oz,
                        node.number_part,
                        node.short_text,
                        node.long_text,
                        node.quantity,
                        node.unit,
                        level,
                        sort_order,
                    ),
                )
            else:
                raise TypeError(f"Unsupported node type: {type(node)!r}")

    @staticmethod
    def _validate_quantity(value: Decimal | None) -> None:
        if value is None:
            return
        if not value.is_finite() or value < 0:
            raise ValueError("Tender item quantity must be finite and nonnegative.")
        # NUMERIC(18, 4): 14 digits before the decimal point.
        if value >= Decimal(100000000000000):
            raise ValueError("Tender item quantity exceeds NUMERIC(18, 4).")
        if value != value.quantize(Decimal("0.0001")):
            raise ValueError("Tender item quantity has more than four decimals.")

    def list_tenders(self, project_id: int) -> list[TenderDocument]:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
                SELECT id, project_id, file_name, file_type,
                       file_hash, status, parsed_at,
                       created_at, updated_at
                FROM lv_documents
                WHERE project_id = %s
                ORDER BY created_at DESC, id DESC;
                """,
                (project_id,),
            )
            return [TenderDocument(**row) for row in cursor.fetchall()]

    def get_tender(self, *, project_id: int, tender_id: int) -> TenderDetail | None:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
                SELECT id, project_id, file_name, file_type,
                       file_hash, status, parsed_at,
                       created_at, updated_at
                FROM lv_documents
                WHERE id = %s AND project_id = %s;
                """,
                (tender_id, project_id),
            )
            document_row = cursor.fetchone()
            if document_row is None:
                return None
            document = TenderDocument(**document_row)

            cursor.execute(
                """
                SELECT id, parent_id, oz, number_part, name, sort_order
                FROM lv_categories
                WHERE lv_document_id = %s;
                """,
                (tender_id,),
            )
            category_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT id, category_id, oz, positionsnummer,
                       kurztext, langtext, menge, einheit, sort_order
                FROM lv_positions
                WHERE lv_document_id = %s;
                """,
                (tender_id,),
            )
            item_rows = cursor.fetchall()

        structure, references = self._rebuild_structure(category_rows, item_rows)
        return TenderDetail(
            document=document, structure=structure, positions=references
        )

    def list_items(
        self, *, project_id: int, tender_id: int
    ) -> list[TenderItemRecord] | None:
        detail = self.get_tender(project_id=project_id, tender_id=tender_id)
        if detail is None:
            return None

        result: list[TenderItemRecord] = []

        for reference in detail.positions:
            if not reference.path:
                raise ValueError("Tender item path is empty.")

            nodes = detail.structure.nodes

            for index in reference.path[:-1]:
                parent = nodes[index]

                if not isinstance(parent, TenderCategory):
                    raise TypeError("Invalid Tender category path.")

                nodes = parent.children

            node = nodes[reference.path[-1]]

            if not isinstance(node, TenderItem):
                raise TypeError("Tender reference does not point to an item.")

            result.append(
                TenderItemRecord(
                    position_id=reference.position_id,
                    item=node,
                )
            )

        return result

    @staticmethod
    def _rebuild_structure(
        category_rows: list[dict[str, Any]],
        item_rows: list[dict[str, Any]],
    ) -> tuple[ParsedTender, list[TenderPositionReference]]:
        categories: dict[int, TenderCategory] = {}
        ordering: dict[int, tuple[int, int]] = {}
        position_ids: dict[int, int] = {}
        roots: list[TenderCategory | TenderItem] = []

        for row in category_rows:
            category = TenderCategory(
                oz=row["oz"],
                number_part=row["number_part"],
                name=row["name"],
            )
            categories[row["id"]] = category
            ordering[id(category)] = (row["sort_order"] or 0, row["id"])

        for row in category_rows:
            category = categories[row["id"]]
            parent_id = row["parent_id"]
            if parent_id is None:
                roots.append(category)
            else:
                parent = categories.get(parent_id)
                if parent is None:
                    raise RuntimeError("Invalid Tender category parent.")
                parent.children.append(category)

        for row in item_rows:
            item = TenderItem(
                oz=row["oz"],
                number_part=row["positionsnummer"],
                short_text=row["kurztext"],
                long_text=row["langtext"],
                quantity=row["menge"],
                unit=row["einheit"],
            )
            ordering[id(item)] = (row["sort_order"] or 0, row["id"])
            position_ids[id(item)] = row["id"]
            category_id = row["category_id"]
            if category_id is None:
                roots.append(item)
            else:
                parent = categories.get(category_id)
                if parent is None:
                    raise RuntimeError("Invalid Tender item category.")
                parent.children.append(item)

        references: list[TenderPositionReference] = []

        def walk(
            nodes: list[TenderCategory | TenderItem], path: tuple[int, ...]
        ) -> None:
            nodes.sort(key=lambda node: ordering[id(node)])
            for index, node in enumerate(nodes):
                node_path = (*path, index)
                if isinstance(node, TenderCategory):
                    walk(node.children, node_path)
                else:
                    references.append(
                        TenderPositionReference(
                            position_id=position_ids[id(node)],
                            path=node_path,
                        )
                    )

        walk(roots, ())
        return ParsedTender(nodes=roots), references
