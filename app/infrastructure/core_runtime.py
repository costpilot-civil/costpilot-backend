"""Reuse Core interfaces, without replicating model inference or RRF algorithms.

The current costpilot-core zip provides ONLY abstract EmbeddingModel and
RerankerModel; it has no ModelLoader and no RRFFusion implementation yet.
Those two Core symbols are the precise pending integration contracts.
"""

from functools import lru_cache

import torch
from costpilot_core.models.matching.match_candidate import MatchCandidate
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.domain.cross_encoder_reranker import CrossEncoderReranker
from app.domain.sentence_transformer_embedding import SentenceTransformerEmbedding
from app.infrastructure.model_config import load_model_config


class CoreUnavailableError(RuntimeError):
    pass


@lru_cache(maxsize=2)
def load_embedding_model(config_path: str) -> SentenceTransformerEmbedding:
    embedding_cfg, _ = load_model_config(config_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    return SentenceTransformerEmbedding(
        model=SentenceTransformer(embedding_cfg["path"], device=device),
        name=embedding_cfg["name"],
        version=embedding_cfg["version"],
    )


@lru_cache(maxsize=2)
def load_reranker_model(config_path: str) -> CrossEncoderReranker:
    _, reranker_cfg = load_model_config(config_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    return CrossEncoderReranker(
        model=CrossEncoder(reranker_cfg["path"], device=device),
        name=reranker_cfg["name"],
        version=reranker_cfg["version"],
    )


def fuse_in_core(
    lists: list[list[MatchCandidate]], *, top_k: int, rrf_k: int
) -> list[MatchCandidate]:
    try:
        # TODO in costpilot-core: port legacy RRFFusion to Core MatchCandidate,
        # which uses `.commodity` (legacy code used `.candidate`).
        from costpilot_core.fusion.rrf_fusion import RRFFusion
    except ImportError as exc:
        raise CoreUnavailableError(
            "CostPilot Core RRFFusion is not implemented yet. "
            "Expected costpilot_core.fusion.rrf_fusion.RRFFusion.fuse."
        ) from exc

    fused = RRFFusion.fuse(candidate_lists=lists, top_k=top_k, rrf_k=rrf_k)
    allowed = {c.commodity.id for ranking in lists for c in ranking}
    ids = [c.commodity.id for c in fused]
    if len(ids) != len(set(ids)) or len(ids) > top_k or not set(ids) <= allowed:
        raise CoreUnavailableError("Core RRF returned invalid candidate IDs.")
    return fused
