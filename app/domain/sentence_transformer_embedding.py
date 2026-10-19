from collections.abc import Sequence

from costpilot_core.embedding.embedding_model import EmbeddingModel
from sentence_transformers import SentenceTransformer


class SentenceTransformerEmbedding(EmbeddingModel):
    def __init__(
        self,
        *,
        model: SentenceTransformer,
        name: str,
        version: str,
        batch_size: int = 16,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0.")

        dimension = model.get_embedding_dimension()
        if dimension is None or dimension <= 0:
            raise ValueError("Unable to determine embedding dimension.")

        self._model = model
        self._name = name
        self._version = version
        self._dimension = dimension
        self._batch_size = batch_size

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, text: str) -> list[float]:
        return self.encode_batch([text])[0]

    def encode_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()
