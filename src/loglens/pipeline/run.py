from __future__ import annotations


from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from loglens.models import LogEntry
from loglens.pipeline.detector import (
    DetectorConfig, DetectionResult, detect,
)
from loglens.pipeline.embeddings import EmbeddingEngine
from loglens.pipeline.templates import TemplateRegistry


@dataclass
class RunConfig:
    mode: str = "fast"                 
    sensitivity: str = "normal"        
    template_level: bool = True       
    auto_threshold: bool = False
    eps: Optional[float] = None
    min_samples: int = 4


def _build_engine(mode: str):
    if mode == "deep":
        from loglens.pipeline.deep_embeddings import DeepEmbeddingEngine
        return DeepEmbeddingEngine()
    return EmbeddingEngine()


def run(entries: Sequence[LogEntry],
        config: Optional[RunConfig] = None,
        baseline: Optional[dict] = None) -> DetectionResult:
    
    cfg = config or RunConfig()
    entries = list(entries)
    det_cfg = DetectorConfig.from_sensitivity(
        cfg.sensitivity,
        eps=cfg.eps,
        min_samples=cfg.min_samples,
    )
    det_cfg.auto_threshold = cfg.auto_threshold

    if not entries:
        return detect(entries, np.zeros((0, 1), dtype=np.float32),
                      det_cfg, baseline=baseline)

    engine = _build_engine(cfg.mode)
    engine.fit(entries)

    if cfg.template_level and hasattr(engine, "embed_templates"):
        registry = TemplateRegistry(entries)
        embeddings = engine.embed_templates(entries, registry)
    else:
        embeddings = engine.embed(entries)

    return detect(entries, embeddings, det_cfg, baseline=baseline)


def run_turbo(path: str, workers: Optional[int] = None) -> dict:
    from loglens.pipeline.turbo import analyze
    return analyze(path, workers=workers)
