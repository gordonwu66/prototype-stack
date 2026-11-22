from collections.abc import Sequence
from typing import Literal, Protocol

from openai import AsyncOpenAI

from api.config import Settings

EmbedKind = Literal["query", "document"]


class EmbeddingProvider(Protocol):
    # Recorded on each chunk, so a later model change can find what needs re-embedding.
    model: str

    async def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]: ...


class OpenAICompatibleEmbeddings:
    """Any OpenAI-compatible /embeddings endpoint: OpenAI, Fireworks, Ollama, TEI, vLLM.

    `kind` is unused: OpenAI embeds queries and documents the same way. Models that want an
    instruction prefix or input_type for queries (Qwen3-Embedding, Voyage) get it here.
    """

    def __init__(self, *, model: str, dims: int, api_key: str, base_url: str | None) -> None:
        self.model = model
        self._dims = dims
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=3)

    async def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self.model, input=list(texts), dimensions=self._dims
        )
        vectors = [d.embedding for d in sorted(response.data, key=lambda d: d.index)]
        if any(len(v) != self._dims for v in vectors):
            got = len(vectors[0])
            raise ValueError(
                f"{self.model} returned {got}-dim vectors; the column holds {self._dims}"
            )
        return vectors


def embedding_provider(s: Settings, dims: int) -> EmbeddingProvider | None:
    key = s.embedding_api_key or s.openai_api_key
    if key is None and s.embedding_base_url is None:
        return None
    return OpenAICompatibleEmbeddings(
        model=s.embedding_model,
        dims=dims,
        api_key=key.get_secret_value() if key else "unused",
        base_url=s.embedding_base_url,
    )
