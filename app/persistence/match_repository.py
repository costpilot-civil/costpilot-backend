"""Persistence for current results only; Core owns matching result semantics."""

from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.domain.matching import TenderItemMatch


class TenderNotFoundError(Exception):
    pass


class MatchRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_results(
        self, *, project_id: int, tender_id: int, results: list[TenderItemMatch]
    ) -> None:
        with self._pool.connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM tender_documents
                WHERE id = %s AND project_id = %s FOR KEY SHARE;
                """,
                (tender_id, project_id),
            )
            if cursor.fetchone() is None:
                raise TenderNotFoundError("Tender not found.")

            cursor.execute(
                "SELECT id FROM tender_items WHERE tender_document_id = %s;",
                (tender_id,),
            )
            expected = {row[0] for row in cursor.fetchall()}
            submitted = {result.position_id for result in results}
            if submitted != expected or len(submitted) != len(results):
                raise ValueError(
                    "Matching results must cover exactly the Tender's items."
                )

            parameters: list[tuple[Any, ...]] = []
            for match in results:
                winner = match.candidates[0] if match.candidates else None
                score = None
                if winner is not None and 0 <= winner.score <= 1:
                    # Numeric(8,6), while Core scores may be raw logits.
                    score = Decimal(str(winner.score)).quantize(Decimal("0.000001"))

                parameters.append(
                    (
                        match.position_id,
                        match.result.commodity.id if match.result.commodity else None,
                        match.result.status.value.upper(),
                        score,
                    )
                )

            if parameters:
                cursor.executemany(
                    """
                    INSERT INTO match_results
                        (position_id, commodity_id, status, score, match_type)
                    VALUES (%s, %s, %s, %s, 'AUTO')
                    ON CONFLICT (position_id) DO UPDATE SET
                        commodity_id = EXCLUDED.commodity_id,
                        status = EXCLUDED.status,
                        score = EXCLUDED.score,
                        match_type = EXCLUDED.match_type;
                    """,
                    parameters,
                )

    def list_results(self, *, project_id: int, tender_id: int) -> list[dict[str, Any]]:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "SELECT id FROM tender_documents WHERE id = %s AND project_id = %s;",
                (tender_id, project_id),
            )
            if cursor.fetchone() is None:
                raise TenderNotFoundError("Tender not found.")

            cursor.execute(
                """
                SELECT t.id AS position_id, t.oz, t.short_text,
                       m.status, m.commodity_id,
                       c.code AS commodity_code,
                       c.description AS commodity_description,
                       m.score
                FROM match_results AS m
                JOIN tender_items AS t ON t.id = m.position_id
                LEFT JOIN commodities AS c ON c.id = m.commodity_id
                WHERE t.tender_document_id = %s
                ORDER BY t.oz, t.id;
                """,
                (tender_id,),
            )
            return list(cursor.fetchall())
