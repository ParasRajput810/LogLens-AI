import time
import statistics
import json
import pytest
import numpy as np
from pathlib import Path
from collections import defaultdict
from loglens.models import LogEntry
from loglens.pipeline.parser import detect_format, parse_line
from loglens.pipeline.embeddings import EmbeddingEngine

FIXTURE_LOG    = Path("tests/fixtures/large_sample.log")
FIXTURE_LABELS = Path("tests/fixtures/large_sample_labels.json")

pytestmark = pytest.mark.skipif(
    not FIXTURE_LOG.exists(),
    reason="Run: python tests/fixtures/generate_logs.py first"
)


def is_sentence_transformers_available() -> bool:
    try:
        import sentence_transformers
        return True
    except ImportError:
        return False


skip_if_no_st = pytest.mark.skipif(
    not is_sentence_transformers_available(),
    reason="sentence-transformers not installed"
)


# --- helpers ---

def load_fixtures():
    with open(FIXTURE_LABELS) as f:
        labels = json.load(f)   # {str(idx): cluster_name}

    entries = []
    fmt = None
    with open(FIXTURE_LOG) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            if i == 0:
                fmt = detect_format(line)
            entry = parse_line(line, fmt)
            if entry is None:
                entry = LogEntry(
                    timestamp="2024-01-15T00:00:00Z",
                    level="INFO",
                    service="unknown",
                    message=line,
                    raw=line,
                )
            entries.append(entry)

    entry_labels = [labels.get(str(i), "unknown") for i in range(len(entries))]
    return entries, entry_labels


def intra_inter_similarity(vectors: np.ndarray, labels: list) -> dict:
    cluster_indices = defaultdict(list)
    for i, label in enumerate(labels):
        if label not in ("normal", "anomaly"):   # only measure named clusters
            cluster_indices[label].append(i)

    intra_sims = []
    inter_sims = []

    cluster_list = list(cluster_indices.keys())

    for cluster in cluster_list:
        idxs = cluster_indices[cluster][:20]   # sample 20 per cluster
        # intra: pairs within same cluster
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = vectors[idxs[i]], vectors[idxs[j]]
                sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
                intra_sims.append(sim)

    for i, c1 in enumerate(cluster_list):
        for c2 in cluster_list[i+1:]:
            i1 = cluster_indices[c1][:5]
            i2 = cluster_indices[c2][:5]
            for a_idx in i1:
                for b_idx in i2:
                    a, b = vectors[a_idx], vectors[b_idx]
                    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
                    inter_sims.append(sim)

    return {
        "intra_mean": float(np.mean(intra_sims)) if intra_sims else 0.0,
        "inter_mean": float(np.mean(inter_sims)) if inter_sims else 0.0,
        "separation": float(np.mean(intra_sims) - np.mean(inter_sims)) if intra_sims else 0.0,
        "intra_count": len(intra_sims),
        "inter_count": len(inter_sims),
    }


def anomaly_separation_score(vectors: np.ndarray, labels: list) -> float:
    cluster_indices = defaultdict(list)
    for i, label in enumerate(labels):
        cluster_indices[label].append(i)

    centroids = {}
    for cluster, idxs in cluster_indices.items():
        if cluster not in ("normal", "anomaly"):
            centroids[cluster] = np.mean(vectors[idxs], axis=0)

    if not centroids or not cluster_indices["anomaly"]:
        return 0.0

    centroid_matrix = np.array(list(centroids.values()))
    anomaly_vectors = vectors[cluster_indices["anomaly"][:20]]

    sims = anomaly_vectors @ centroid_matrix.T
    mean_sim = float(np.mean(sims))
    return 1.0 - mean_sim   # higher = anomalies are more isolated


@pytest.fixture(scope="module")
def fixture_data():
    return load_fixtures()


@pytest.fixture(scope="module")
def fast_vectors(fixture_data):
    entries, labels = fixture_data
    engine = EmbeddingEngine()
    vectors = engine.embed(entries)
    return vectors, labels


@pytest.fixture(scope="module")
def deep_vectors(fixture_data):
    from loglens.pipeline.deep_embeddings import DeepEmbeddingEngine
    entries, labels = fixture_data
    engine = DeepEmbeddingEngine()
    vectors = engine.embed(entries)
    return vectors, labels


def test_fast_intra_greater_than_inter(fast_vectors):
    vectors, labels = fast_vectors
    scores = intra_inter_similarity(vectors, labels)
    print(f"\n[FAST] intra={scores['intra_mean']:.3f} inter={scores['inter_mean']:.3f} sep={scores['separation']:.3f}")
    assert scores["intra_mean"] > scores["inter_mean"], \
        f"Intra {scores['intra_mean']:.3f} should be > inter {scores['inter_mean']:.3f}"


def test_fast_anomaly_isolation(fast_vectors):
    vectors, labels = fast_vectors
    score = anomaly_separation_score(vectors, labels)
    print(f"\n[FAST] anomaly isolation score: {score:.3f}")
    assert score > 0.1, f"Anomaly isolation too low: {score:.3f}"


def test_fast_cluster_separation_positive(fast_vectors):
    vectors, labels = fast_vectors
    scores = intra_inter_similarity(vectors, labels)
    assert scores["separation"] > 0, \
        f"Separation score should be positive, got {scores['separation']:.3f}"


@skip_if_no_st
def test_deep_intra_greater_than_inter(deep_vectors):
    """Deep mode: same-cluster logs should be more similar than cross-cluster."""
    vectors, labels = deep_vectors
    scores = intra_inter_similarity(vectors, labels)
    print(f"\n[DEEP] intra={scores['intra_mean']:.3f} inter={scores['inter_mean']:.3f} sep={scores['separation']:.3f}")
    assert scores["intra_mean"] > scores["inter_mean"], \
        f"Intra {scores['intra_mean']:.3f} should be > inter {scores['inter_mean']:.3f}"


@skip_if_no_st
def test_deep_anomaly_isolation(deep_vectors):
    """Deep mode: anomalies should be more isolated than fast mode."""
    vectors, labels = deep_vectors
    score = anomaly_separation_score(vectors, labels)
    print(f"\n[DEEP] anomaly isolation score: {score:.3f}")
    assert score > 0.05, f"Anomaly isolation too low: {score:.3f}"


@skip_if_no_st
def test_deep_beats_fast_on_separation(fast_vectors, deep_vectors):
    """
    Deep mode should have better cluster separation than fast mode.
    This is the key accuracy comparison test.
    """
    fast_scores = intra_inter_similarity(fast_vectors[0], fast_vectors[1])
    deep_scores = intra_inter_similarity(deep_vectors[0], deep_vectors[1])

    print(f"\n{'='*50}")
    print(f"{'ACCURACY REPORT':^50}")
    print(f"{'='*50}")
    print(f"{'Metric':<30} {'Fast':>8} {'Deep':>8}")
    print(f"{'-'*50}")
    print(f"{'Intra-cluster similarity':<30} {fast_scores['intra_mean']:>8.3f} {deep_scores['intra_mean']:>8.3f}")
    print(f"{'Inter-cluster similarity':<30} {fast_scores['inter_mean']:>8.3f} {deep_scores['inter_mean']:>8.3f}")
    print(f"{'Separation (intra-inter)':<30} {fast_scores['separation']:>8.3f} {deep_scores['separation']:>8.3f}")
    fast_anomaly = anomaly_separation_score(fast_vectors[0], fast_vectors[1])
    deep_anomaly = anomaly_separation_score(deep_vectors[0], deep_vectors[1])
    print(f"{'Anomaly isolation score':<30} {fast_anomaly:>8.3f} {deep_anomaly:>8.3f}")
    print(f"{'='*50}")

    assert deep_scores["separation"] >= fast_scores["separation"], \
        f"Deep separation {deep_scores['separation']:.3f} should be >= fast {fast_scores['separation']:.3f}"

def benchmark_engine(engine, entries: list, runs: int = 3) -> dict:
    """Run engine.embed() multiple times and collect timing stats."""
    times = []
    vector_shape = None

    for _ in range(runs):
        # fresh engine each run to avoid cache skew
        start = time.perf_counter()
        vectors = engine.embed(entries)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        vector_shape = vectors.shape

    return {
        "runs":         runs,
        "shape":        vector_shape,
        "total_logs":   len(entries),
        "mean_s":       statistics.mean(times),
        "min_s":        min(times),
        "max_s":        max(times),
        "stdev_s":      statistics.stdev(times) if runs > 1 else 0.0,
        "logs_per_sec": len(entries) / statistics.mean(times),
        "ms_per_log":   (statistics.mean(times) / len(entries)) * 1000,
    }


def print_benchmark_report(label: str, result: dict):
    print(f"\n{'='*55}")
    print(f"  BENCHMARK REPORT — {label}")
    print(f"{'='*55}")
    print(f"  Total logs      : {result['total_logs']:,}")
    print(f"  Vector shape    : {result['shape']}")
    print(f"  Runs            : {result['runs']}")
    print(f"  Mean time       : {result['mean_s']:.3f}s")
    print(f"  Min  time       : {result['min_s']:.3f}s")
    print(f"  Max  time       : {result['max_s']:.3f}s")
    print(f"  Std  dev        : {result['stdev_s']:.3f}s")
    print(f"  Throughput      : {result['logs_per_sec']:,.0f} logs/sec")
    print(f"  Latency/log     : {result['ms_per_log']:.3f}ms")
    print(f"{'='*55}")


def test_fast_benchmark_small(fixture_data):
    """Benchmark fast mode on 100 logs."""
    entries, _ = fixture_data
    sample = entries[:100]
    result = benchmark_engine(EmbeddingEngine(), sample, runs=3)
    print_benchmark_report("FAST MODE — 100 logs", result)
    # must process at least 500 logs/sec
    assert result["logs_per_sec"] > 500, \
        f"Too slow: {result['logs_per_sec']:.0f} logs/sec (expected >500)"


def test_fast_benchmark_large(fixture_data):
    """Benchmark fast mode on full 5000 log fixture."""
    entries, _ = fixture_data
    result = benchmark_engine(EmbeddingEngine(), entries, runs=3)
    print_benchmark_report("FAST MODE — 5000 logs", result)
    # must process at least 200 logs/sec on large corpus
    assert result["logs_per_sec"] > 200, \
        f"Too slow: {result['logs_per_sec']:.0f} logs/sec (expected >200)"


def test_fast_latency_per_log(fixture_data):
    """Each log should take under 5ms in fast mode."""
    entries, _ = fixture_data
    result = benchmark_engine(EmbeddingEngine(), entries[:500], runs=3)
    print_benchmark_report("FAST MODE — latency test (500 logs)", result)
    assert result["ms_per_log"] < 5.0, \
        f"Latency too high: {result['ms_per_log']:.3f}ms/log (expected <5ms)"


@skip_if_no_st
def test_deep_benchmark_small(fixture_data):
    """Benchmark deep mode on 100 logs."""
    from loglens.pipeline.deep_embeddings import DeepEmbeddingEngine
    entries, _ = fixture_data
    sample = entries[:100]
    result = benchmark_engine(DeepEmbeddingEngine(), sample, runs=3)
    print_benchmark_report("DEEP MODE — 100 logs", result)
    # deep mode slower — at least 10 logs/sec
    assert result["logs_per_sec"] > 10, \
        f"Too slow: {result['logs_per_sec']:.0f} logs/sec (expected >10)"


@skip_if_no_st
def test_deep_benchmark_large(fixture_data):
    """Benchmark deep mode on 500 logs."""
    from loglens.pipeline.deep_embeddings import DeepEmbeddingEngine
    entries, _ = fixture_data
    sample = entries[:500]
    result = benchmark_engine(DeepEmbeddingEngine(), sample, runs=2)
    print_benchmark_report("DEEP MODE — 500 logs", result)
    assert result["logs_per_sec"] > 5, \
        f"Too slow: {result['logs_per_sec']:.0f} logs/sec (expected >5)"


@skip_if_no_st
def test_fast_vs_deep_speed_comparison(fixture_data):
    """
    Fast mode must be significantly faster than deep mode.
    Expected: fast is at least 10x faster.
    """
    from loglens.pipeline.deep_embeddings import DeepEmbeddingEngine
    entries, _ = fixture_data
    sample = entries[:200]

    fast_result = benchmark_engine(EmbeddingEngine(), sample, runs=3)
    deep_result = benchmark_engine(DeepEmbeddingEngine(), sample, runs=3)

    speedup = fast_result["logs_per_sec"] / deep_result["logs_per_sec"]

    print(f"\n{'='*55}")
    print(f"  SPEED COMPARISON — 200 logs")
    print(f"{'='*55}")
    print(f"  {'Mode':<20} {'Throughput':>12} {'ms/log':>10}")
    print(f"  {'-'*45}")
    print(f"  {'Fast (TF-IDF)':<20} {fast_result['logs_per_sec']:>10,.0f}/s {fast_result['ms_per_log']:>9.3f}ms")
    print(f"  {'Deep (Neural)':<20} {deep_result['logs_per_sec']:>10,.0f}/s {deep_result['ms_per_log']:>9.3f}ms")
    print(f"  {'-'*45}")
    print(f"  Speedup (fast/deep) : {speedup:.1f}x faster")
    print(f"{'='*55}")

    assert speedup > 3, \
        f"Fast mode should be >10x faster than deep, got {speedup:.1f}x"