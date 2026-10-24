from collections.abc import Sequence

from costpilot_core.reranking.reranker_model import RerankerModel
from sentence_transformers import CrossEncoder
from torch import nn


class CrossEncoderReranker(RerankerModel):
    def __init__(
        self,
        *,
        model: CrossEncoder,
        name: str,
        version: str,
        batch_size: int = 16,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0.")

        self._model = model
        self._name = name
        self._version = version
        self._batch_size = batch_size

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def score(self, query: str, document: str) -> float:
        return self.score_batch(query, [document])[0]

    def score_batch(
        self,
        query: str,
        documents: Sequence[str],
    ) -> list[float]:
        if not documents:
            return []

        pairs = [(query, document) for document in documents]

        scores = self._model.predict(
            inputs=pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            activation_fn=nn.Sigmoid(),
        )

        return [float(score) for score in scores]
