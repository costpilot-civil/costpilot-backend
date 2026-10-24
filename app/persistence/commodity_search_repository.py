"""PostgreSQL-backed BM25 and pgvector retrieval using Core data models.

Keyword flow: PostgreSQL GIN filters a candidate pool, then genuine BM25
scores candidates using corpus-wide statistics from the search projection.
Vector flow: PostgreSQL orders stored embeddings by the configured metric.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any

from costpilot_core.models.commodity.commodity import Commodity
from costpilot_core.models.matching.match_candidate import MatchCandidate
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.logging.performance import StageTimer

logger = logging.getLogger(__name__)


class SearchDataUnavailableError(RuntimeError):
    pass


# PostgreSQL tsvector::text (positions are comma-delimited, optional weights).
_LEXEME = re.compile(r"'((?:''|[^'])+)'(?::([0-9A-D*,]+))?")


def _frequencies(vector: str) -> Counter[str]:
    result: Counter[str] = Counter()
    for match in _LEXEME.finditer(vector):
        term = match.group(1).replace("''", "'")
        positions = match.group(2)
        result[term] = len(positions.split(",")) if positions else 1
    return result


class CommoditySearchRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self._corpus_stats: tuple[int, float, Counter[str]] | None = None

    def _stats(self) -> tuple[int, float, Counter[str]]:
        if self._corpus_stats is not None:
            return self._corpus_stats

        timer = StageTimer()

        with self._pool.connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT search_vector::text FROM commodity_search;")
            vectors = [row[0] for row in cursor.fetchall()]

        timer.mark("database_read")

        if not vectors:
            raise SearchDataUnavailableError("commodity_search has no rows.")

        doc_freq: Counter[str] = Counter()
        lengths = []

        for vector in vectors:
            tf = _frequencies(vector)
            doc_freq.update(tf.keys())
            lengths.append(sum(tf.values()))

        self._corpus_stats = (
            len(vectors),
            max(1.0, sum(lengths) / len(vectors)),
            doc_freq,
        )

        timer.mark("statistics_calculation")

        timer.report(
            logger,
            "bm25_corpus_statistics",
            documents=len(vectors),
        )

        return self._corpus_stats

    def bm25_search(
        self,
        *,
        query: str,
        top_k: int,
        candidate_pool: int,
        k1: float,
        b: float,
    ) -> list[MatchCandidate]:
        timer = StageTimer()

        document_count, average_length, doc_freq = self._stats()
        timer.mark("corpus_statistics")

        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "SELECT tsvector_to_array(to_tsvector('simple', %s)) AS terms;",
                (query,),
            )
            row = cursor.fetchone()
            tokens = list(row["terms"])[:64] if row and row["terms"] else []
            timer.mark("tokenization_db")

            if not tokens:
                timer.report(
                    logger,
                    "bm25_search",
                    candidates=0,
                    skipped="empty_tokens",
                )
                return []

            # All terms have first passed through the database analyzer. The
            # resulting tsquery is still bound as a parameter, never SQL code.
            tsquery = " | ".join(
                "'" + term.replace("\\", "\\\\").replace("'", "''") + "'"
                for term in tokens
            )
            cursor.execute(
                """
                SELECT s.commodity_id, s.search_vector::text AS vector
                FROM commodity_search AS s
                WHERE s.search_vector @@ to_tsquery('simple', %s)
                ORDER BY ts_rank_cd(s.search_vector, to_tsquery('simple', %s)) DESC,
                         s.commodity_id ASC
                LIMIT %s;
                """,
                (tsquery, tsquery, candidate_pool),
            )
            timer.mark("query_preprocess")

            matches = cursor.fetchall()
            timer.mark("candidate_search_db")

        scored: list[tuple[int, float]] = []
        for match in matches:
            tf = _frequencies(match["vector"])
            length_factor = k1 * (1 - b + b * sum(tf.values()) / average_length)
            score = 0.0
            for token in tokens:
                frequency = tf[token]
                if frequency == 0:
                    continue
                df = doc_freq[token]
                idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                score += idf * frequency * (k1 + 1) / (frequency + length_factor)
            if score > 0:
                scored.append((match["commodity_id"], score))
        timer.mark("bm25_scoring")

        scored.sort(key=lambda item: (-item[1], item[0]))
        top = scored[:top_k]
        timer.mark("sort_topk")

        commodities = self._load_commodities([commodity_id for commodity_id, _ in top])
        timer.mark("commodity_load")

        results = [
            MatchCandidate(
                commodity=commodities[commodity_id],
                score=score,
            )
            for commodity_id, score in top
        ]

        timer.mark("postprocess")

        timer.report(
            logger,
            "bm25_search",
            candidate_pool_size=len(matches),
            candidates=len(results),
        )

        return results

    def get_embedding_model(self, *, name: str, version: str) -> tuple[int, int, str]:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
                SELECT id, dimension, distance_metric
                FROM embedding_models WHERE name = %s AND version = %s;
                """,
                (name, version),
            )
            row = cursor.fetchone()
            if row is None:
                raise SearchDataUnavailableError(
                    f"Database embedding model {name!r} / {version!r} was not found."
                )
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM commodity_embeddings WHERE model_id = %s);",
                (row["id"],),
            )
            exists = cursor.fetchone()
            if not exists or not exists["exists"]:
                raise SearchDataUnavailableError(
                    "No commodity embeddings for the configured model."
                )
        return (row["id"], row["dimension"], row["distance_metric"])

    def vector_search(
        self,
        *,
        query_vector: list[float],
        model_id: int,
        dimension: int,
        metric: str,
        top_k: int,
    ) -> list[MatchCandidate]:
        timer = StageTimer()

        if len(query_vector) != dimension or any(
            not math.isfinite(float(value)) for value in query_vector
        ):
            raise ValueError("Invalid query embedding vector or dimension.")
        operators = {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}
        if metric not in operators:
            raise ValueError(f"Unknown vector distance metric: {metric!r}")
        # Operator is selected from an internal whitelist only.
        operator = operators[metric]
        vector = "[" + ",".join(str(float(value)) for value in query_vector) + "]"

        timer.mark("preprocess")

        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                f"""
                SELECT e.commodity_id, e.embedding {operator} %s::vector AS distance
                FROM commodity_embeddings AS e
                WHERE e.model_id = %s
                ORDER BY distance ASC, e.commodity_id ASC
                LIMIT %s;
                """,  # type: ignore
                (vector, model_id, top_k),
            )
            rows = cursor.fetchall()

        timer.mark("database_search")

        commodities = self._load_commodities([r["commodity_id"] for r in rows])
        timer.mark("commodity_load")

        results = [
            MatchCandidate(
                commodity=commodities[row["commodity_id"]],
                score=(1.0 - float(row["distance"]))
                if metric == "cosine"
                else -float(row["distance"]),
            )
            for row in rows
        ]

        timer.mark("postprocess")

        timer.report(
            logger,
            "vector_search",
            candidates=len(results),
        )

        return results

    def structured_search(
        self,
        *,
        material_type: str,
        attributes: dict[str, Any],
        query: str,
        top_k: int,
    ) -> list[MatchCandidate]:
        timer = StageTimer()

        if top_k <= 0:
            return []

        if not material_type.strip() or not attributes:
            return []

        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            # Analyze query text using the same PostgreSQL
            # configuration as BM25 retrieval.
            cursor.execute(
                """
                SELECT
                    tsvector_to_array(
                        to_tsvector('simple', %s)
                    ) AS terms;
                """,
                (query,),
            )

            row = cursor.fetchone()
            tokens = list(row["terms"])[:64] if row and row["terms"] else []
            timer.mark("tokenization_db")

            # Build an OR-based tsquery for candidate ranking.
            tsquery = " | ".join(
                "'" + term.replace("\\", "\\\\").replace("'", "''") + "'"
                for term in tokens
            )

            cursor.execute(
                """
                SELECT
                    s.commodity_id,
                    ts_rank_cd(
                        s.search_vector,
                        to_tsquery('simple', %s)
                    ) AS score
                FROM commodity_search AS s
                WHERE
                    s.material_type = %s
                    AND s.attributes @> %s::jsonb
                ORDER BY
                    score DESC,
                    s.commodity_id ASC
                LIMIT %s;
                """,
                (
                    tsquery,
                    material_type,
                    json.dumps(attributes),
                    top_k,
                ),
            )

            rows = cursor.fetchall()
        timer.mark("database_search")

        commodities = self._load_commodities([row["commodity_id"] for row in rows])
        timer.mark("commodity_load")

        results = [
            MatchCandidate(
                commodity=commodities[row["commodity_id"]],
                score=float(row["score"]),
            )
            for row in rows
        ]

        timer.mark("postprocess")

        timer.report(
            logger,
            "structured_search",
            material_type=material_type,
            attribute_count=len(attributes),
            candidates=len(results),
        )

        return results

    def _load_commodities(self, ids: list[int]) -> dict[int, Commodity]:
        """Populate the *existing* Core Commodity model, not a backend clone.

        A recursive CTE builds the complete group hierarchy; prices are not
        needed for retrieval and use the Core default empty price collections.
        """
        if not ids:
            return {}

        timer = StageTimer()
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
                WITH RECURSIVE ancestors AS (
                    SELECT c.id AS commodity_id, g.id AS group_id,
                           g.parent_id, g.product_group_id,
                           COALESCE(NULLIF(g.description, ''), g.code) AS label,
                           0 AS depth, ARRAY[g.id] AS visited
                    FROM commodities AS c
                    JOIN commodity_groups AS g ON g.id = c.commodity_group_id
                    WHERE c.id = ANY(%s::bigint[])
                    UNION ALL
                    SELECT a.commodity_id, p.id, p.parent_id, p.product_group_id,
                           COALESCE(NULLIF(p.description, ''), p.code),
                           a.depth + 1, a.visited || p.id
                    FROM ancestors AS a
                    JOIN commodity_groups AS p ON p.id = a.parent_id
                    WHERE NOT p.id = ANY(a.visited)
                )
                SELECT c.id, c.code, c.description, c.unit,
                       COALESCE((
                           SELECT string_agg(a.label, ' / ' ORDER BY a.depth DESC)
                           FROM ancestors AS a WHERE a.commodity_id = c.id
                       ), '') AS group_path,
                       COALESCE((
                           SELECT pg.name
                           FROM ancestors AS a
                           JOIN product_groups AS pg ON pg.id = a.product_group_id
                           WHERE a.commodity_id = c.id
                           ORDER BY a.depth DESC LIMIT 1
                       ), '') AS product_group_name
                FROM commodities AS c
                WHERE c.id = ANY(%s::bigint[]);
                """,
                (ids, ids),
            )
            rows: list[dict[str, Any]] = list(cursor.fetchall())
        timer.mark("database_query")

        commodities = {
            row["id"]: Commodity(
                id=row["id"],
                code=row["code"],
                description=row["description"],
                unit=row["unit"],
                category_path=" / ".join(
                    part
                    for part in (
                        row["product_group_name"],
                        row["group_path"],
                    )
                    if part
                ),
            )
            for row in rows
        }

        timer.mark("build_commodity_models")

        timer.report(
            logger,
            "load_commodities",
            requested=len(ids),
            loaded=len(commodities),
        )

        return commodities
