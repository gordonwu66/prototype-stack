from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    """Retrieval knobs. Frozen so a config can be hashed into eval results."""

    leg_limit: int = 100  # candidates from each of BM25 and vector search
    fused_limit: int = 50  # fused results kept; also the future reranker's candidate count
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    rrf_k: int = 60
    lexical_weight: float = 1.0
    semantic_weight: float = 1.0
    # HNSW returns at most ef_search rows per scan, so it must be >= leg_limit.
    hnsw_ef_search: int = 100
    # Chunking, in estimated tokens (characters / 4).
    chunk_target_tokens: int = 400
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 50
    # Background work: embedding batch size, and how often BM25 statistics may refresh.
    embed_batch_size: int = 128
    stats_refresh_s: float = 30.0
    sweep_interval_s: float = 60.0

    def __post_init__(self) -> None:
        if self.hnsw_ef_search < self.leg_limit:
            raise ValueError("hnsw_ef_search must be >= leg_limit")
        if self.chunk_target_tokens + self.chunk_overlap_tokens > self.chunk_max_tokens:
            raise ValueError(
                "chunk_target_tokens + chunk_overlap_tokens must be <= chunk_max_tokens"
            )


DEFAULT_CONFIG = SearchConfig()
