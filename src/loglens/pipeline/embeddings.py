from __future__ import annotations

import re
from typing import List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from loglens.models import LogEntry
from loglens.pipeline.synonyms import (
    STOPWORDS, SynonymLearner, normalize_message,
)

ENGINE_VERSION = "2"

LEVEL_MAP = {
    "EMERGENCY": 1.0, "EMERG": 1.0, "PANIC": 1.0,
    "ALERT": 0.95, "FATAL": 0.95,
    "CRITICAL": 0.9, "CRIT": 0.9,
    "ERROR": 0.75, "ERR": 0.75,
    "WARN": 0.5, "WARNING": 0.5,
    "NOTICE": 0.3,
    "INFO": 0.15,
    "DEBUG": 0.05,
    "TRACE": 0.0,
}
DEFAULT_LEVEL_SCORE = 0.15

ERROR_KEYWORDS = [
    "error", "fail", "fatal", "exception", "timeout", "refused",
    "denied", "crash", "panic", "killed", "oom", "unavailable",
    "reset", "abort", "corrupt", "overflow", "underflow", "deadlock",
    "leak", "violation", "invalid", "missing", "unreachable",
]

HTTP_PATTERN = re.compile(
    r"(?:\b(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+\S+\s+"
    r"|\bHTTP(?:/\d\.\d)?\"?\s+"
    r"|\b(?:status|code|response)\s*[=: ]\s*\"?"
    r"|\b(?:failed|error)\s+)"
    r"([1-5]\d{2})\b"
    r"|\b([1-5]\d{2})\s+(?=OK\b|Created\b|Accepted\b|No Content"
    r"|Moved|Found\b|Bad Request|Unauthorized|Forbidden|Not Found"
    r"|Too Many Requests|Internal Server Error|Bad Gateway"
    r"|Service Unavailable|Gateway Time-?out)",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"\b(\d+\.?\d*)\b")
IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
PORT_PATTERN = re.compile(r"(?<!\d):(\d{2,5})(?!\d)")
DURATION_PATTERN = re.compile(
    r"\b(\d+\.?\d*)\s*(ms|s|sec|seconds|minutes|min)\b")
MEMORY_PATTERN = re.compile(
    r"\b(\d+\.?\d*)\s*(mb|gb|kb|bytes|mib|gib)\b", re.IGNORECASE)
REPEAT_PATTERN = re.compile(r"repeated\s+(\d+)\s+times?", re.IGNORECASE)

N_LOG_FEATURES = 14


def _http_status(msg: str) -> Optional[int]:
    for m in HTTP_PATTERN.finditer(msg):
        g = m.group(1) or m.group(2)
        if g:
            return int(g)
    return None


def extract_features(entry: LogEntry) -> np.ndarray:
    msg = entry.message
    low = msg.lower()

    level_score = LEVEL_MAP.get(entry.level.upper(), DEFAULT_LEVEL_SCORE)

    normalized = normalize_message(low)
    error_score = sum(1 for kw in ERROR_KEYWORDS if kw in normalized) \
        / len(ERROR_KEYWORDS)

    status = _http_status(msg)
    if status is None:
        http_score = 0.0
    else:
        http_score = 0.0 if status < 400 else (0.5 if status < 500 else 1.0)

    numbers = [float(n) for n in NUMBER_PATTERN.findall(low)]
    has_number = 1.0 if numbers else 0.0
    max_number = min(np.log10(1.0 + max(numbers)) / 9.0, 1.0) if numbers else 0.0

    length_score = min(len(msg) / 200.0, 1.0)

    has_stack = 1.0 if any(x in low for x in (
        "traceback", "at line", "stack", "caused by")) else 0.0

    has_ip = 1.0 if IP_PATTERN.search(low) else 0.0
    has_port = 1.0 if PORT_PATTERN.search(low) else 0.0

    duration_match = DURATION_PATTERN.findall(low)
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

    has_memory = 1.0 if MEMORY_PATTERN.search(low) else 0.0

    repeat_match = REPEAT_PATTERN.search(low)
    repeat_score = min(int(repeat_match.group(1)) / 100.0, 1.0) \
        if repeat_match else 0.0

    has_service = 1.0 if entry.service and \
        entry.service.lower() not in ("unknown", "") else 0.0

    return np.array([
        level_score, error_score, http_score,
        has_number, max_number, length_score,
        has_stack, has_ip, has_port,
        has_duration, max_duration, has_memory,
        repeat_score, has_service,
    ], dtype=np.float32)


def _row_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return mat / norms


def combine_blocks(text_block: np.ndarray,
                   feature_block: np.ndarray,
                   feature_weight: float) -> np.ndarray:
    text_n = _row_normalize(text_block)
    feat_n = _row_normalize(feature_block)
    combined = np.hstack([(1.0 - feature_weight) * text_n,
                          feature_weight * feat_n])
    return _row_normalize(combined)


class EmbeddingEngine:

    def __init__(self,
                 tfidf_features: int = 256,
                 feature_weight: float = 0.4,
                 use_synonym_cache: bool = True):
        self.tfidf_features = tfidf_features
        self.feature_weight = feature_weight
        self.use_synonym_cache = use_synonym_cache
        self.vectorizer = TfidfVectorizer(
            max_features=tfidf_features,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
            strip_accents="unicode",
            token_pattern=r"(?u)\b[a-zA-Z0-9_]{2,}\b",
            stop_words=sorted(STOPWORDS),
        )
        self.fitted = False
        self._learner: SynonymLearner | None = None


    def fit(self, entries: List[LogEntry]) -> "EmbeddingEngine":
        raw_messages = [e.message for e in entries]

        if self._learner is None:
            self._learner = SynonymLearner(use_cache=self.use_synonym_cache)
            self._learner.fit(raw_messages)

        synonyms = self._learner.get_all_synonyms()
        normalized = [normalize_message(m, synonyms) for m in raw_messages]

        min_df = 2 if len(normalized) >= 10 else 1
        self.vectorizer.set_params(min_df=min_df)
        self.vectorizer.fit(normalized)
        self.fitted = True
        return self

    def _get_normalized(self, entries: List[LogEntry]) -> List[str]:
        synonyms = (self._learner.get_all_synonyms()
                    if self._learner else None)
        return [normalize_message(e.message, synonyms) for e in entries]

    def embed(self, entries: List[LogEntry]) -> np.ndarray:
        if not entries:
            return np.zeros((0, N_LOG_FEATURES), dtype=np.float32)
        if not self.fitted:
            self.fit(entries)

        normalized = self._get_normalized(entries)
        tfidf = self.vectorizer.transform(normalized).toarray().astype(np.float32)

        feats = np.array([
            e.metadata.get("_features")
            if isinstance(e.metadata.get("_features"), np.ndarray)
            else extract_features(e)
            for e in entries
        ], dtype=np.float32)

        return combine_blocks(tfidf, feats, self.feature_weight)


def get_engine() -> EmbeddingEngine:
    return EmbeddingEngine()