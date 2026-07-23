"""
BertScore-based answer faithfulness scorer.

Measures how well a generated answer is grounded in its source chunks.
High precision = most of what the answer says is supported by the sources.

The scorer is a lazy module-level singleton — the HuggingFace model is
loaded once on first use and reused across all subsequent calls.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.config.settings import settings

# Module-level singleton — loaded once, reused across requests
_scorer: Optional["BertScorer"] = None
_lock = threading.Lock()


def get_scorer() -> "BertScorer":
    global _scorer
    if _scorer is None:
        with _lock:
            if _scorer is None:
                _scorer = BertScorer()
    return _scorer


class BertScorer:
    """
    Thin wrapper around the bert_score library.

    Scores a candidate string against a list of reference strings and
    returns precision, recall, and F1 — all interpreted as faithfulness
    of the candidate relative to the references.
    """

    # Maximum combined reference length (chars) to avoid token overflow.
    # distilbert truncates at 512 tokens; 3 000 chars ≈ 500–600 tokens.
    _MAX_REFERENCE_CHARS = 3_000

    def __init__(self):
        self.model_type = settings.bertscore_model
        # Validate import at init time so failures are visible on startup
        try:
            import bert_score  # noqa: F401
        except ImportError:
            raise ImportError(
                "bert-score not installed. Add it with: poetry add bert-score"
            )
        logger.info(f"BertScorer initialised (model={self.model_type})")

    def score(self, candidate: str, references: list[str]) -> dict:
        """
        Score candidate faithfulness against the reference chunks.

        Args:
            candidate:  The generated answer (English).
            references: List of source chunk texts used to generate the answer.

        Returns:
            Dict with keys: precision, recall, f1, model, scored_at.
        """
        from bert_score import score as _bs_score

        joined = "\n\n".join(r for r in references if r.strip())
        if not joined:
            logger.warning("BertScorer called with empty references — skipping")
            return {}

        reference = joined[: self._MAX_REFERENCE_CHARS]

        try:
            P, R, F1 = _bs_score(
                cands=[candidate],
                refs=[reference],
                model_type=self.model_type,
                lang="en",
                verbose=False,
                device="cpu",
            )
            result = {
                "precision": round(P[0].item(), 4),
                "recall": round(R[0].item(), 4),
                "f1": round(F1[0].item(), 4),
                "model": self.model_type,
                "scored_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.debug(
                f"BertScore: P={result['precision']:.3f} "
                f"R={result['recall']:.3f} F1={result['f1']:.3f}"
            )
            return result
        except Exception as exc:
            logger.error(f"BertScore computation failed: {exc}")
            return {}
