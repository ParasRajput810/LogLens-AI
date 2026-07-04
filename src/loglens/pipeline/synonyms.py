import re
import json
import os
from collections import defaultdict
from typing import List, Dict

BASE_SYNONYMS: Dict[str, str] = {
    "db": "database",
    "conn": "connection",
    "auth": "authentication",
    "req": "request",
    "resp": "response",
    "err": "error",
    "msg": "message",
    "svc": "service",
    "k8s": "kubernetes",
    "cfg": "config",
    "env": "environment",
    "infra": "infrastructure",
    "perf": "performance",
    "proc": "process",
    "mem": "memory",
    "cpu": "processor",
    "net": "network",
    "cxn": "connection",
    "cnx": "connection",
    "svr": "server",
    "usr": "user",
    "pwd": "password",
    "cert": "certificate",
    "creds": "credentials",
    "oom": "memory",
    "latency": "timeout",
    "unreachable": "refused",
    "terminated": "killed",
    "segfault": "crash",
    "sigkill": "killed",
    "sigterm": "terminated",
    "nullpointer": "crash",
    "npe": "crash",
    "econnrefused": "refused",
    "econnreset": "reset",
    "etimedout": "timeout",
    "heap": "memory",
    "gc": "memory",
    "ioexception": "error",
    "nullpointerexception": "crash",
    "outofmemoryerror": "memory",
    "down": "unavailable",
    "degraded": "unavailable",
    "unresponsive": "unavailable",
    "hung": "timeout",
    "stuck": "timeout",
    "overloaded": "unavailable",
}

ERROR_CODE_PATTERNS = [
    (re.compile(r'^ECONN(\w+)$'),   lambda m: m.group(1).lower()),   # ECONNREFUSED → refused
    (re.compile(r'^ETIMED?OUT$'),   lambda m: "timeout"),
    (re.compile(r'^ENOENT$'),       lambda m: "missing"),
    (re.compile(r'^EPERM$'),        lambda m: "denied"),
    (re.compile(r'^EACCES$'),       lambda m: "denied"),
    (re.compile(r'^ESRCH$'),        lambda m: "missing"),
    (re.compile(r'^E[A-Z]{2,10}$'), lambda m: m.group(0)[1:].lower()),  # generic EXXX → xxx
]

CAMEL_CASE_PATTERN  = re.compile(r'([a-z])([A-Z])|([A-Z]+)([A-Z][a-z])')
WORD_NUM_PATTERN    = re.compile(r'([a-zA-Z]+)(\d+)')
NUM_WORD_PATTERN    = re.compile(r'(\d+)([a-zA-Z]+)')


def split_camel_case(word: str) -> List[str]:
    split = re.sub(r'([a-z])([A-Z])', r'\1 \2', word)
    split = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', split)
    return split.lower().split()


def split_word_number(word: str) -> List[str]:
    parts = []
    m = WORD_NUM_PATTERN.match(word)
    if m:
        parts = [m.group(1), m.group(2)]
    m2 = NUM_WORD_PATTERN.match(word)
    if m2 and not parts:
        parts = [m2.group(1), m2.group(2)]
    return parts if parts else [word]


def detect_unknown_word(word: str) -> str:
    upper = word.upper()

    for pattern, handler in ERROR_CODE_PATTERNS:
        m = pattern.match(upper)
        if m:
            return handler(m)

    if CAMEL_CASE_PATTERN.search(word):
        parts = split_camel_case(word)
        return " ".join(BASE_SYNONYMS.get(p, p) for p in parts)

    parts = split_word_number(word)
    if len(parts) > 1:
        return " ".join(BASE_SYNONYMS.get(p, p) for p in parts)

    return word


class SynonymLearner:

    def __init__(self, min_cooccurrence: int = 5, similarity_threshold: float = 0.7):
        self.min_cooccurrence = min_cooccurrence
        self.similarity_threshold = similarity_threshold
        self.learned: Dict[str, str] = {}               # auto-learned synonyms
        self.cooccurrence: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.word_freq: Dict[str, int] = defaultdict(int)
        self._cache_path = ".loglens_synonyms.json"     # persist learned synonyms

    def _load_cache(self):
        if os.path.exists(self._cache_path):
            with open(self._cache_path) as f:
                self.learned = json.load(f)

    def _save_cache(self):
        with open(self._cache_path, "w") as f:
            json.dump(self.learned, f, indent=2)

    def _tokenize(self, msg: str) -> List[str]:
        return re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', msg.lower())

    def fit(self, messages: List[str]):
        self._load_cache()

        for msg in messages:
            tokens = self._tokenize(msg)
            for token in tokens:
                self.word_freq[token] += 1
            for i, t1 in enumerate(tokens):
                # window of 3 words around each word
                for t2 in tokens[max(0, i-3): i+4]:
                    if t1 != t2:
                        self.cooccurrence[t1][t2] += 1

        for rare_word, neighbors in self.cooccurrence.items():
            rare_freq = self.word_freq[rare_word]

            for common_word, cooc_count in neighbors.items():
                common_freq = self.word_freq[common_word]

                if rare_word in BASE_SYNONYMS:
                    continue

                if cooc_count < self.min_cooccurrence:
                    continue

                if common_freq < rare_freq * 3:
                    continue

                ratio = cooc_count / rare_freq
                if ratio >= self.similarity_threshold:
                    self.learned[rare_word] = common_word

        self._save_cache()

    def get_all_synonyms(self) -> Dict[str, str]:
        merged = dict(BASE_SYNONYMS)
        merged.update(self.learned)
        return merged


_learner: SynonymLearner | None = None

def get_learner() -> SynonymLearner:
    global _learner
    if _learner is None:
        _learner = SynonymLearner()
        _learner._load_cache()
    return _learner


def normalize_message(msg: str, synonyms: Dict[str, str] | None = None) -> str:
    if synonyms is None:
        synonyms = get_learner().get_all_synonyms()

    words = msg.lower().split()
    result = []
    for word in words:
        clean = re.sub(r'[^a-zA-Z0-9]', '', word)
        if clean in synonyms:
            result.append(synonyms[clean])
        elif clean and not clean.isdigit():
            result.append(detect_unknown_word(clean))
        else:
            result.append(word)

    return " ".join(result)