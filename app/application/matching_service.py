"""Orchestrates Core algorithms and PostgreSQL retrieval, no duplicate models."""

import logging
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
from app.logging.performance import StageTimer
from app.persistence.commodity_search_repository import CommoditySearchRepository
from app.persistence.match_repository import MatchRepository, TenderNotFoundError
from app.persistence.tender_repository import TenderRepository

logger = logging.getLogger(__name__)


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
        run_timer = StageTimer()

        logger.info(
            "Matching started | project_id=%d | tender_id=%d",
            project_id,
            tender_id,
        )

        # --------------------------------------------------
        # 1. Load Tender Positions
        # --------------------------------------------------

        items = self._tenders.list_items(
            project_id=project_id,
            tender_id=tender_id,
        )
        run_timer.mark("load_tender_positions")

        if items is None:
            raise TenderNotFoundError("Tender not found.")

        if not items:
            save_timer = StageTimer()

            self._matches.save_results(
                project_id=project_id,
                tender_id=tender_id,
                results=[],
            )

            save_timer.mark("database_write")
            run_timer.mark("database_save")

            save_timer.report(
                logger,
                "matching_save",
                project_id=project_id,
                tender_id=tender_id,
                results=0,
            )

            run_timer.report(
                logger,
                "matching_total",
                project_id=project_id,
                tender_id=tender_id,
                positions=0,
            )

            return []

        # --------------------------------------------------
        # 2. Initialize Embedding Model
        # --------------------------------------------------

        embedder = load_embedding_model(self._model_config_path)
        run_timer.mark("embedding_model_load")

        model_id, dimension, metric = self._search.get_embedding_model(
            name=embedder.name,
            version=embedder.version,
        )
        run_timer.mark("embedding_model_metadata")

        if embedder.dimension != dimension:
            raise ValueError("Core embedding dimension differs from database metadata.")

        # --------------------------------------------------
        # 3. Process Each Tender Position
        # --------------------------------------------------

        results: list[TenderItemMatch] = []

        for record in items:
            timer = StageTimer()

            query = TextBuilder.build_tender_item_text(record.item)
            timer.mark("query_preprocess")

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

                timer.report(
                    logger,
                    "matching_position",
                    project_id=project_id,
                    tender_id=tender_id,
                    position_id=record.position_id,
                    skipped="empty_query",
                )
                continue

            # ----------------------------------------------
            # 3.1 Vector Retrieval
            # ----------------------------------------------

            query_vector = embedder.encode(query)
            timer.mark("vector_embedding")

            vector = self._search.vector_search(
                query_vector=query_vector,
                model_id=model_id,
                dimension=dimension,
                metric=metric,
                top_k=self._retrieval_top_k,
            )
            timer.mark("vector_search")

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
            timer.mark("bm25_search")

            # ----------------------------------------------
            # 3.3 Structured Retrieval
            # ----------------------------------------------

            structured: list[MatchCandidate] = []

            try:
                extracted = self._material_extractor.extract(query)
            except ValueError:
                extracted = None

            timer.mark("structured_extraction")

            if extracted is not None:
                attributes = {
                    **extracted.core_attributes,
                    **extracted.supplementary_attributes,
                }
                timer.mark("structured_preprocess")

                structured = self._search.structured_search(
                    material_type=extracted.material_type,
                    attributes=attributes,
                    query=query,
                    top_k=self._retrieval_top_k,
                )
                timer.mark("structured_search")

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
            timer.mark("rrf_fusion")

            # ----------------------------------------------
            # 5. Reranking
            # ----------------------------------------------

            reranker = load_reranker_model(self._model_config_path)
            timer.mark("reranker_model_load")

            ranked: list[MatchCandidate] = []

            if fused:
                documents = [
                    TextBuilder.build_commodity_text(candidate.commodity)
                    for candidate in fused
                ]
                timer.mark("reranker_preprocess")

                scores = reranker.score_batch(
                    query=query,
                    documents=documents,
                )
                timer.mark("reranker_inference")

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
                timer.mark("reranker_postprocess")

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

            timer.mark("result_build")

            timer.report(
                logger,
                "matching_position",
                project_id=project_id,
                tender_id=tender_id,
                position_id=record.position_id,
                vector_candidates=len(vector),
                bm25_candidates=len(bm25),
                structured_candidates=len(structured),
                fused_candidates=len(fused),
                ranked_candidates=len(ranked),
            )

        run_timer.mark("positions_processing")

        # --------------------------------------------------
        # 7. Persist Matching Results
        # --------------------------------------------------

        save_timer = StageTimer()

        self._matches.save_results(
            project_id=project_id,
            tender_id=tender_id,
            results=results,
        )

        save_timer.mark("database_write")
        run_timer.mark("database_save")

        save_timer.report(
            logger,
            "matching_save",
            project_id=project_id,
            tender_id=tender_id,
            results=len(results),
        )

        # --------------------------------------------------
        # 8. Matching Summary
        # --------------------------------------------------

        run_timer.report(
            logger,
            "matching_total",
            project_id=project_id,
            tender_id=tender_id,
            positions=len(items),
        )

        return results

    def list_results(self, *, project_id: int, tender_id: int) -> list[dict]:
        return self._matches.list_results(project_id=project_id, tender_id=tender_id)
