"""Orchestrates Core algorithms and PostgreSQL retrieval, no duplicate models."""

import math
from pathlib import Path

import yaml
from costpilot_core.models.matching.match_candidate import MatchCandidate
from costpilot_core.models.matching.match_result import MatchResult
from costpilot_core.models.matching.match_status import MatchStatus
from costpilot_core.text.text_builder import TextBuilder

from app.domain.matching import TenderItemMatch
from app.infrastructure.core_runtime import fuse_in_core, load_core_models
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
    ) -> None:
        self._tenders = tenders
        self._search = search
        self._matches = matches
        self._model_config_path = model_config_path

        with Path(model_config_path).expanduser().open(encoding="utf-8") as file:
            config = yaml.safe_load(file)

        if not isinstance(config, dict) or not isinstance(config.get("matching"), dict):
            raise ValueError("Missing 'matching' section in the model configuration.")

        matching = config["matching"]
        self._retrieval_top_k = matching["retrieval_top_k"]
        self._bm25_candidate_pool = matching["bm25_candidate_pool"]
        self._fusion_top_k = matching["fusion_top_k"]
        self._rerank_top_k = matching["rerank_top_k"]
        self._rrf_k = matching["rrf_k"]
        self._bm25_k1 = matching["bm25_k1"]
        self._bm25_b = matching["bm25_b"]

    def run(self, *, project_id: int, tender_id: int) -> list[TenderItemMatch]:
        items = self._tenders.list_items(project_id=project_id, tender_id=tender_id)
        if items is None:
            raise TenderNotFoundError("Tender not found.")
        if not items:
            self._matches.save_results(
                project_id=project_id, tender_id=tender_id, results=[]
            )
            return []

        embedder, reranker = load_core_models(self._model_config_path)
        model_id, dimension, metric = self._search.get_embedding_model(
            name=embedder.name, version=embedder.version
        )
        if embedder.dimension != dimension:
            raise ValueError("Core embedding dimension differs from database metadata.")

        results: list[TenderItemMatch] = []
        for record in items:
            query = TextBuilder.build_tender_item_text(record.item)
            if not query:
                results.append(
                    TenderItemMatch(
                        position_id=record.position_id,
                        item=record.item,
                        result=MatchResult(
                            status=MatchStatus.UNMATCHED, commodity=None
                        ),
                        candidates=[],
                    )
                )
                continue

            bm25 = self._search.bm25_search(
                query=query,
                top_k=self._retrieval_top_k,
                candidate_pool=self._bm25_candidate_pool,
                k1=self._bm25_k1,
                b=self._bm25_b,
            )
            vector = self._search.vector_search(
                query_vector=embedder.encode(query),
                model_id=model_id,
                dimension=dimension,
                metric=metric,
                top_k=self._retrieval_top_k,
            )
            fused = fuse_in_core(
                [bm25, vector], top_k=self._fusion_top_k, rrf_k=self._rrf_k
            )

            ranked: list[MatchCandidate] = []
            if fused:
                texts = [TextBuilder.build_commodity_text(c.commodity) for c in fused]
                scores = reranker.score_batch(query=query, documents=texts)
                if len(scores) != len(fused):
                    raise ValueError(
                        "Core reranker score count does not match candidates."
                    )
                ranked = [
                    MatchCandidate(commodity=c.commodity, score=float(score))
                    for c, score in zip(fused, scores, strict=True)
                ]
                if any(not math.isfinite(c.score) for c in ranked):
                    raise ValueError("Core reranker returned a non-finite score.")
                ranked.sort(key=lambda c: c.score, reverse=True)
                ranked = ranked[: self._rerank_top_k]

            result = MatchResult(
                status=(
                    MatchStatus.REVIEW_REQUIRED if ranked else MatchStatus.UNMATCHED
                ),
                commodity=ranked[0].commodity if ranked else None,
            )
            results.append(
                TenderItemMatch(
                    position_id=record.position_id,
                    item=record.item,
                    result=result,
                    candidates=ranked,
                )
            )

        # Database transaction is only held for persistence, not model inference.
        self._matches.save_results(
            project_id=project_id, tender_id=tender_id, results=results
        )
        return results

    def list_results(self, *, project_id: int, tender_id: int) -> list[dict]:
        return self._matches.list_results(project_id=project_id, tender_id=tender_id)
