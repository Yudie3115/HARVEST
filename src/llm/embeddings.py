"""
Embedding generation – OpenAI (primary) with local sentence-transformers fallback
"""
from typing import List, Optional
from loguru import logger

from src.config.settings import settings


class EmbeddingClient:
    """
    Unified embedding client supporting:
    - OpenAI text-embedding-3-small (1 536 dims, default)
    - Local sentence-transformers all-MiniLM-L6-v2 (384 dims, fallback)
    """

    def __init__(
        self,
        provider: str = None,
        model: str = None,
    ):
        self.provider = provider or settings.embedding_provider
        self.model = model

        if self.provider == "openai":
            self._init_openai()
        elif self.provider == "local":
            self._init_local()
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    # Known valid OpenAI embedding model prefixes
    _OPENAI_MODEL_PREFIXES = ("text-embedding-", "text-search-")

    def _init_openai(self):
        from openai import OpenAI

        if not settings.openai_api_key:
            logger.warning("OpenAI key not found – falling back to local embeddings")
            self.provider = "local"
            self._init_local()
            return

        self.client = OpenAI(api_key=settings.openai_api_key)
        chosen_model = self.model or settings.embedding_model

        # Detect obvious misconfiguration: a local/HuggingFace model name used
        # with the OpenAI provider (e.g. EMBEDDING_MODEL=all-MiniLM-L6-v2 in .env)
        if not any(chosen_model.startswith(p) for p in self._OPENAI_MODEL_PREFIXES):
            logger.warning(
                f"EMBEDDING_MODEL='{chosen_model}' does not look like an OpenAI model "
                f"(expected prefix: {self._OPENAI_MODEL_PREFIXES}). "
                f"Falling back to default 'text-embedding-3-small'. "
                f"Set EMBEDDING_PROVIDER=local in .env to use local sentence-transformers models."
            )
            chosen_model = "text-embedding-3-small"
            # Dimension must match the fallback model
            self.dimension = 1536
        else:
            self.dimension = settings.embedding_dimension

        self.model = chosen_model
        logger.info(f"Initialized OpenAI embedding client: {self.model} (dim={self.dimension})")

    def _init_local(self):
        try:
            from sentence_transformers import SentenceTransformer

            self.model = self.model or settings.embedding_model_local
            self._st_model = SentenceTransformer(self.model)
            self.dimension = self._st_model.get_sentence_embedding_dimension()
            logger.info(
                f"Initialized local embedding model: {self.model} (dim={self.dimension})"
            )
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a single text string

        Args:
            text: Input text

        Returns:
            Embedding as a list of floats
        """
        return self.embed_batch([text])[0]

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts, batching to stay within API limits

        Args:
            texts: List of input texts
            batch_size: Texts per API call (default from settings)

        Returns:
            List of embedding vectors (same order as input)
        """
        batch_size = batch_size or settings.embedding_batch_size
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self._embed_batch_impl(batch)
            all_embeddings.extend(embeddings)

        logger.debug(f"Generated {len(all_embeddings)} embeddings via {self.provider}")
        return all_embeddings

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _embed_batch_impl(self, texts: List[str]) -> List[List[float]]:
        # Strip empty strings to avoid API errors
        safe_texts = [t if t.strip() else " " for t in texts]

        if self.provider == "openai":
            return self._openai_embed(safe_texts)
        return self._local_embed(safe_texts)

    def _openai_embed(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise

    def _local_embed(self, texts: List[str]) -> List[List[float]]:
        try:
            vectors = self._st_model.encode(texts, show_progress_bar=False)
            return [v.tolist() for v in vectors]
        except Exception as e:
            logger.error(f"Local embedding error: {e}")
            raise

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Verify that the embedding service is accessible"""
        try:
            self.embed("test")
            return True
        except Exception as e:
            logger.error(f"Embedding connection check failed: {e}")
            return False
