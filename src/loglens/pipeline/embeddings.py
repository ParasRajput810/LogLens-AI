import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from typing import List
from loglens.models import LogEntry
from loglens.pipeline.synonyms import SynonymLearner, normalize_message, get_learner

LEVEL_MAP = {
    "DEBUG": 0.0, "INFO": 0.2, "WARN": 0.6,
    "WARNING": 0.6, "ERROR": 1.0, "CRITICAL": 1.0
}

ERROR_KEYWORDS = [
    "error", "fail", "fatal", "exception", "timeout", "refused",
    "denied", "crash", "panic", "killed", "oom", "unavailable",
    "reset", "abort", "corrupt", "overflow", "underflow", "deadlock",
    "leak", "violation", "invalid", "missing", "unreachable",
]

HTTP_PATTERN     = re.compile(r'\b([2345]\d{2})\b')
NUMBER_PATTERN   = re.compile(r'\b(\d+\.?\d*)\b')
IP_PATTERN       = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')
PORT_PATTERN     = re.compile(r'\b(:\d{2,5})\b')
DURATION_PATTERN = re.compile(r'\b(\d+\.?\d*)\s*(ms|s|sec|seconds|minutes|min)\b')
MEMORY_PATTERN   = re.compile(r'\b(\d+\.?\d*)\s*(mb|gb|kb|bytes|mib|gib)\b', re.IGNORECASE)
REPEAT_PATTERN   = re.compile(r'repeated\s+(\d+)\s+times?', re.IGNORECASE)

LOG_FEATURE_WEIGHT = 3.0


def extract_features(entry: LogEntry) -> np.ndarray:
    msg = entry.message.lower()

    level_score = LEVEL_MAP.get(entry.level.upper(), 0.2)

    normalized = normalize_message(msg)
    error_score = sum(1 for kw in ERROR_KEYWORDS if kw in normalized) / len(ERROR_KEYWORDS)

    http_match = HTTP_PATTERN.findall(msg)
    if http_match:
        status = int(http_match[-1])
        http_score = 0.0 if status < 400 else (0.5 if status < 500 else 1.0)
    else:
        http_score = 0.0

    numbers = [float(n) for n in NUMBER_PATTERN.findall(msg)]
    has_number = 1.0 if numbers else 0.0
    max_number = min(np.log1p(max(numbers)), 1.0) if numbers else 0.0

    length_score = min(len(msg) / 200.0, 1.0)

    has_stack = 1.0 if any(x in msg for x in ["traceback", "at line", "stack", "caused by"]) else 0.0

    has_ip = 1.0 if IP_PATTERN.search(msg) else 0.0

    has_port = 1.0 if PORT_PATTERN.search(msg) else 0.0

    duration_match = DURATION_PATTERN.findall(msg)
    has_duration = 1.0 if duration_match else 0.0
    max_duration = 0.0
    if duration_match:
        val = float(duration_match[-1][0])
        unit = duration_match[-1][1]
        if unit == "ms":
            val /= 1000
        elif unit in ("minutes", "min"):
            val *= 60
        max_duration = min(np.log1p(val) / 10.0, 1.0)

    has_memory = 1.0 if MEMORY_PATTERN.search(msg) else 0.0

    repeat_match = REPEAT_PATTERN.search(msg)
    repeat_score = min(int(repeat_match.group(1)) / 100.0, 1.0) if repeat_match else 0.0

    has_service = 1.0 if entry.service and entry.service.lower() not in ("unknown", "") else 0.0

    return np.array([
        level_score, error_score, http_score,
        has_number, max_number, length_score,
        has_stack, has_ip, has_port,
        has_duration, max_duration, has_memory,
        repeat_score, has_service,
    ], dtype=np.float32)


class EmbeddingEngine:
    def __init__(self, tfidf_features: int = 256):
        self.tfidf_features = tfidf_features
        self.vectorizer = TfidfVectorizer(
            max_features=tfidf_features,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
            strip_accents="unicode",
            token_pattern=r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b',
        )
        self.fitted = False
        self._learner: SynonymLearner | None = None  # set after corpus scan

    def fit(self, entries: List[LogEntry]):
        raw_messages = [e.message for e in entries]

        self._learner = get_learner()
        self._learner.fit(raw_messages)

        synonyms = self._learner.get_all_synonyms()
        normalized = [normalize_message(m, synonyms) for m in raw_messages]

        min_df = 2 if len(normalized) >= 10 else 1
        self.vectorizer.set_params(min_df=min_df)
        self.vectorizer.fit(normalized)
        self.fitted = True

    def _get_normalized(self, entries: List[LogEntry]) -> List[str]:
        synonyms = (
            self._learner.get_all_synonyms()
            if self._learner
            else get_learner().get_all_synonyms()
        )
        return [normalize_message(e.message, synonyms) for e in entries]

    def embed(self, entries: List[LogEntry]) -> np.ndarray:
        if not self.fitted:
            self.fit(entries)

        normalized = self._get_normalized(entries)
        tfidf_matrix = self.vectorizer.transform(normalized).toarray().astype(np.float32)

        log_features = np.array(
            [extract_features(e) for e in entries], dtype=np.float32
        ) * LOG_FEATURE_WEIGHT

        combined = np.hstack([tfidf_matrix, log_features])
        norms = np.linalg.norm(combined, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return combined / norms


_engine: EmbeddingEngine | None = None

def get_engine() -> EmbeddingEngine:
    global _engine
    if _engine is None:
        _engine = EmbeddingEngine()
    return _engine