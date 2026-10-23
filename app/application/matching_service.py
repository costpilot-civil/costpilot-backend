"""Orchestrates Core algorithms and PostgreSQL retrieval, no duplicate models."""

import math
from pathlib import Path

import yaml
from costpilot_core.material.material_extractor import MaterialExtractor
from costpilot_core.models.matching.match_candidate import MatchCandidate
from costpilot_core.models.matching.match_result import MatchResult
from costpilot_core.models.matching.match_status import MatchStatus
from costpilot_core.text.text_builder import TextBuilder

from app.domain.matching import TenderItemMatch
from app.infrastructure.core_runtime import (
    fuse_in_core,
    load_embedding_model,
    load_reranker_model,
)
from app.persistence.commodity_search_repository import CommoditySearchRepository
from app.persistence.match_repository import MatchRepository, TenderNotFoundError
from app.persistence.tender_repository import TenderRepository


class MatchingService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        search: CommoditySearchRepository,
        matches: MatchRepository,
        model_config_path: str,
        material_extractor: MaterialExtractor,
    ) -> None:
        self._tenders = tenders
        self._search = search
        self._matches = matches
        self._model_config_path = model_config_path
        self._material_extractor = material_extractor

        with Path(model_config_path).expanduser().open(encoding="utf-8") as file:
            config = yaml.safe_load(file)

        if not isinstance(config, dict) or not isinstance(config.get("matching"), dict):
            raise TypeError("Missing 'matching' section in the model configuration.")

        matching = config["matching"]
        self._retrieval_top_k = matching["retrieval_top_k"]
        self._bm25_candidate_pool = matching["bm25_candidate_pool"]
        self._fusion_top_k = matching["fusion_top_k"]
        self._rerank_top_k = matching["rerank_top_k"]
        self._rrf_k = matching["rrf_k"]
        self._bm25_k1 = matching["bm25_k1"]
        self._bm25_b = matching["bm25_b"]

    def run(self, *, project_id: int, tender_id: int) -> list[TenderItemMatch]:
        # --------------------------------------------------
        # 1. Load Tender Positions
        # --------------------------------------------------

        items = self._tenders.list_items(
            project_id=project_id,
            tender_id=tender_id,
        )

        if items is None:
            raise TenderNotFoundError("Tender not found.")

        if not items:
            self._matches.save_results(
                project_id=project_id,
                tender_id=tender_id,
                results=[],
            )
            return []

        # --------------------------------------------------
        # 2. Initialize Embedding Model
        # --------------------------------------------------

        embedder = load_embedding_model(self._model_config_path)

        model_id, dimension, metric = self._search.get_embedding_model(
            name=embedder.name,
            version=embedder.version,
        )

        if embedder.dimension != dimension:
            raise ValueError("Core embedding dimension differs from database metadata.")

        # --------------------------------------------------
        # 3. Process Each Tender Position
        # --------------------------------------------------
        results: list[TenderItemMatch] = []

        for record in items:
            query = TextBuilder.build_tender_item_text(record.item)

            if not query:
                results.append(
                    TenderItemMatch(
                        position_id=record.position_id,
                        item=record.item,
                        result=MatchResult(
                            status=MatchStatus.UNMATCHED,
                            commodity=None,
                        ),
                        candidates=[],
                    )
                )
                continue

            # ----------------------------------------------
            # 3.1 Vector Retrieval
            # ----------------------------------------------

            query_vector = embedder.encode(query)

            vector = self._search.vector_search(
                query_vector=query_vector,
                model_id=model_id,
                dimension=dimension,
                metric=metric,
                top_k=self._retrieval_top_k,
            )

            # ----------------------------------------------
            # 3.2 BM25 Retrieval
            # ----------------------------------------------

            bm25 = self._search.bm25_search(
                query=query,
                top_k=self._retrieval_top_k,
                candidate_pool=self._bm25_candidate_pool,
                k1=self._bm25_k1,
                b=self._bm25_b,
            )

            # ----------------------------------------------
            # 3.3 Structured Retrieval
            # ----------------------------------------------

            structured: list[MatchCandidate] = []

            try:
                extracted = self._material_extractor.extract(query)
            except ValueError:
                extracted = None

            if extracted is not None:
                attributes = {
                    **extracted.core_attributes,
                    **extracted.supplementary_attributes,
                }

                structured = self._search.structured_search(
                    material_type=extracted.material_type,
                    attributes=attributes,
                    query=query,
                    top_k=self._retrieval_top_k,
                )

            # ----------------------------------------------
            # 4. RRF Fusion
            # ----------------------------------------------

            candidate_lists = [
                vector,
                bm25,
                structured,
            ]

            fused = fuse_in_core(
                candidate_lists,
                top_k=self._fusion_top_k,
                rrf_k=self._rrf_k,
            )

            # ----------------------------------------------
            # 5. Reranking
            # ----------------------------------------------
            reranker = load_reranker_model(self._model_config_path)

            ranked: list[MatchCandidate] = []
            if fused:
                documents = [
                    TextBuilder.build_commodity_text(candidate.commodity)
                    for candidate in fused
                ]

                scores = reranker.score_batch(
                    query=query,
                    documents=documents,
                )

                if len(scores) != len(fused):
                    raise ValueError(
                        "Core reranker score count does not match candidates."
                    )

                ranked = [
                    MatchCandidate(
                        commodity=candidate.commodity,
                        score=float(score),
                    )
                    for candidate, score in zip(
                        fused,
                        scores,
                        strict=True,
                    )
                ]

                if any(not math.isfinite(candidate.score) for candidate in ranked):
                    raise ValueError("Core reranker returned a non-finite score.")

                ranked.sort(
                    key=lambda candidate: candidate.score,
                    reverse=True,
                )

                ranked = ranked[: self._rerank_top_k]

            # ----------------------------------------------
            # 6. Build Matching Result
            # ----------------------------------------------

            result = MatchResult(
                status=(
                    MatchStatus.REVIEW_REQUIRED if ranked else MatchStatus.UNMATCHED
                ),
                commodity=(ranked[0].commodity if ranked else None),
            )

            results.append(
                TenderItemMatch(
                    position_id=record.position_id,
                    item=record.item,
                    result=result,
                    candidates=ranked,
                )
            )

        # --------------------------------------------------
        # 7. Persist Matching Results
        # --------------------------------------------------

        self._matches.save_results(
            project_id=project_id,
            tender_id=tender_id,
            results=results,
        )

        return results

    def list_results(self, *, project_id: int, tender_id: int) -> list[dict]:
        return self._matches.list_results(project_id=project_id, tender_id=tender_id)
