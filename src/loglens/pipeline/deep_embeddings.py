from __future__ import annotations
import numpy as np
from typing import List
from loglens.models import LogEntry
from loglens.pipeline.embeddings import extract_features, LOG_FEATURE_WEIGHT
from loglens.pipeline.synonyms import normalize_message, get_learner

_model = None

def _load_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")  # 80MB, free, local
        except ImportError:
            raise ImportError(
                "Deep mode requires sentence-transformers.\n"
                "Install it with: pip install sentence-transformers"
            )
    return _model


class DeepEmbeddingEngine:
    def __init__(self):
        self._learner = get_learner()

    def fit(self, entries: List[LogEntry]):
        messages = [e.message for e in entries]
        self._learner.fit(messages)

    def embed(self, entries: List[LogEntry]) -> np.ndarray:
        model = _load_model()
        synonyms = self._learner.get_all_synonyms()

        messages = [normalize_message(e.message, synonyms) for e in entries]

        semantic = model.encode(messages, show_progress_bar=False).astype(np.float32)

        log_features = np.array(
            [extract_features(e) for e in entries], dtype=np.float32
        ) * LOG_FEATURE_WEIGHT

        combined = np.hstack([semantic, log_features])
        norms = np.linalg.norm(combined, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return combined / norms


_deep_engine: DeepEmbeddingEngine | None = None

def get_deep_engine() -> DeepEmbeddingEngine:
    global _deep_engine
    if _deep_engine is None:
        _deep_engine = DeepEmbeddingEngine()
    return _deep_engine