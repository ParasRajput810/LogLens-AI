"""Mocked tests for the LLM layer — no network, no real API keys."""
import io
import json
import os
from unittest import mock

import pytest

from loglens.llm.providers import LLMConfig, LLMClient, LLMError, TokenUsage
from loglens.llm.rca import run_rca, run_ask, build_rca_context, save_report, RCAResult
from loglens.output.html_report import render_html_report
from loglens.models import LogEntry


def _fake_response(content="## Incident Summary\nAll good.", usage=None):
    body = json.dumps({
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }).encode("utf-8")

    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    return FakeResp(body)


def _cfg(provider="openai", **kw):
    defaults = dict(provider=provider, api_key="test-key", model="test-model")
    if provider == "azure":
        defaults.update(azure_endpoint="https://res.openai.azure.com", azure_deployment="chat")
    defaults.update(kw)
    return LLMConfig(**defaults)


ANOMALIES = [
    LogEntry(level="CRITICAL", service="db", message="replication lag critical 500s"),
    LogEntry(level="ERROR", service="api", message="connection refused to db:5432"),
]



class TestLLMConfig:
    def test_missing_provider_raises(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("LOGLENS_"):
                monkeypatch.delenv(k, raising=False)
        with pytest.raises(LLMError, match="No LLM provider"):
            LLMConfig.from_env()

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("LOGLENS_LLM_API_KEY", "k")
        with pytest.raises(LLMError, match="Unknown provider"):
            LLMConfig.from_env(provider="claude")

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("LOGLENS_LLM_API_KEY", raising=False)
        with pytest.raises(LLMError, match="API key"):
            LLMConfig.from_env(provider="openai", api_key="")

    def test_defaults_applied(self, monkeypatch):
        monkeypatch.delenv("LOGLENS_LLM_MODEL", raising=False)
        cfg = LLMConfig.from_env(provider="groq", api_key="k")
        assert cfg.model == "llama-3.3-70b-versatile"

    def test_azure_requires_endpoint(self, monkeypatch):
        monkeypatch.delenv("LOGLENS_AZURE_ENDPOINT", raising=False)
        with pytest.raises(LLMError, match="(?i)endpoint"):
            LLMConfig.from_env(provider="azure", api_key="k", model="chat")

    def test_azure_model_falls_back_to_deployment(self, monkeypatch):
        monkeypatch.setenv("LOGLENS_AZURE_ENDPOINT", "https://res.openai.azure.com")
        monkeypatch.setenv("LOGLENS_AZURE_DEPLOYMENT", "chat")
        monkeypatch.delenv("LOGLENS_LLM_MODEL", raising=False)
        cfg = LLMConfig.from_env(provider="azure", api_key="k")
        assert cfg.azure_deployment == "chat"
        assert cfg.model == "chat"


class TestLLMClient:
    def test_endpoints(self):
        assert "api.openai.com" in LLMClient(_cfg("openai"))._endpoint()
        assert "api.groq.com" in LLMClient(_cfg("groq"))._endpoint()
        az = LLMClient(_cfg("azure"))._endpoint()
        assert "res.openai.azure.com" in az and "/deployments/chat/" in az

    def test_headers(self):
        assert LLMClient(_cfg("openai"))._headers()["Authorization"] == "Bearer test-key"
        assert LLMClient(_cfg("azure"))._headers()["api-key"] == "test-key"

    @mock.patch("urllib.request.urlopen")
    def test_chat_returns_content_and_usage(self, m_open):
        m_open.return_value = _fake_response("hello world")
        client = LLMClient(_cfg())
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == "hello world"
        assert client.last_usage.total_tokens == 150

    @mock.patch("urllib.request.urlopen")
    def test_azure_payload_has_no_model(self, m_open):
        m_open.return_value = _fake_response()
        LLMClient(_cfg("azure")).chat([{"role": "user", "content": "hi"}])
        sent = json.loads(m_open.call_args[0][0].data)
        assert "model" not in sent

    @mock.patch("urllib.request.urlopen")
    def test_network_error_retries_then_fails(self, m_open):
        m_open.side_effect = OSError("boom")
        client = LLMClient(_cfg(retries=1))
        client.config.retries = 1
        with mock.patch("time.sleep"):
            with pytest.raises(LLMError, match="failed after retries"):
                client.chat([{"role": "user", "content": "hi"}])
        assert m_open.call_count == 2 




class TestRCA:
    def test_context_includes_anomalies_and_caps(self):
        many = ANOMALIES * 50 
        ctx = build_rca_context(many, source_name="x.log")
        assert "replication lag" in ctx
        assert ctx.count("[CRITICAL]") + ctx.count("[ERROR]") == 40

    def test_empty_anomalies_short_circuits(self):
        res = run_rca([], _cfg())
        assert res.anomalies_sent == 0 and "No anomalies" in res.report

    @mock.patch("urllib.request.urlopen")
    def test_run_rca_end_to_end(self, m_open):
        m_open.return_value = _fake_response("## Incident Summary\nDB failed.")
        res = run_rca(ANOMALIES, _cfg(), scores=[0.9, 0.8], reasons=["rare", "severe"])
        assert "DB failed" in res.report
        assert res.anomalies_sent == 2
        assert res.usage.total_tokens == 150

    @mock.patch("urllib.request.urlopen")
    def test_run_ask_includes_question(self, m_open):
        m_open.return_value = _fake_response("Because the DB lagged.")
        res = run_ask("why did db degrade?", ANOMALIES, _cfg())
        sent = json.loads(m_open.call_args[0][0].data)
        user_msg = sent["messages"][-1]["content"]
        assert "why did db degrade?" in user_msg
        assert "Because the DB lagged." in res.report

    def test_save_report(self, tmp_path):
        res = RCAResult(report="## Summary\nok", provider="openai",
                        model="gpt-4o-mini", anomalies_sent=2,
                        usage=TokenUsage(total_tokens=150))
        path = tmp_path / "rca.md"
        save_report(res, str(path), source_name="x.log")
        text = path.read_text()
        assert "x.log" in text and "## Summary" in text and "150" in text


class TestHTMLReport:
    def test_render_basic(self):
        html_doc = render_html_report(
            source="x.log", total_lines=100, anomalies=ANOMALIES,
            level_counts={"CRITICAL": 1, "ERROR": 1},
        )
        assert "DOCTYPE html" in html_doc
        assert "replication lag" in html_doc
        assert "AI Root-Cause" not in html_doc  

    def test_render_with_rca(self):
        html_doc = render_html_report(
            source="x.log", total_lines=100, anomalies=ANOMALIES,
            level_counts={"ERROR": 2},
            rca_markdown="## Incident Summary\nDB failed.",
            rca_meta={"provider": "azure", "model": "chat", "tokens": 150},
        )
        assert "AI Root-Cause" in html_doc and "DB failed." in html_doc

    def test_html_escaping(self):
        bad = [LogEntry(level="ERROR", service="x", message="<script>alert(1)</script>")]
        html_doc = render_html_report("x.log", 1, bad, {"ERROR": 1})
        assert "<script>alert(1)</script>" not in html_doc