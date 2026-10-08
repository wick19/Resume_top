from backend import config
from backend.llm import budget, llm


def setup_function(_fn):
    llm.resolve.cache_clear()


def test_free_stack_models_and_caps():
    assert config.GROQ_MODEL == "qwen/qwen3.8-27b"
    assert config.GEMINI_MODEL == "gemini-3.8-flash"
    assert config.NVIDIA_MODEL == "deepseek-ai/deepseek-v4.1-flash"
    assert config.LLM_DAILY_CAP_GROQ == 80
    assert config.LLM_DAILY_CAP_GEMINI == 120
    assert config.LLM_DAILY_CAP_CEREBRAS == 150
    assert config.LLM_DAILY_CAP_NVIDIA == 80
    assert not hasattr(config, "OPENAI_API_KEY")
    assert not hasattr(config, "LLM_ALLOW_PAID")


def test_groq_uses_qwen_free_model(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    spec = llm.resolve()
    assert spec["name"] == "groq"
    assert spec["model"] == "qwen/qwen3.8-27b"


def test_paid_openai_key_is_ignored(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    llm.resolve.cache_clear()
    assert llm.resolve() is None


def test_kill_switch_stops_before_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DB", tmp_path / "lib.db")
    monkeypatch.setattr(config, "LLM_DAILY_CAP_GROQ", 2)
    monkeypatch.setattr(config, "LLM_CALLS_PER_TAILOR", 5)
    assert budget.allow("groq") is True
    budget.record("groq", 2)
    assert budget.allow("groq") is False
    snap = budget.snapshot("groq")
    assert snap["kill_switch"] is True
    assert snap["remaining_calls"] == 0
    assert snap["remaining_tailors"] == 0
    assert "console.groq.com/keys" in snap["signup"]["groq"]


def test_remaining_tailors_uses_calls_per_job(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DB", tmp_path / "lib.db")
    monkeypatch.setattr(config, "LLM_DAILY_CAP_GROQ", 80)
    monkeypatch.setattr(config, "LLM_CALLS_PER_TAILOR", 5)
    assert budget.remaining_tailors("groq") == 16
    budget.record("groq", 5)
    assert budget.remaining_tailors("groq") == 15


def test_llm_available_false_when_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DB", tmp_path / "lib.db")
    monkeypatch.setattr(config, "LLM_DAILY_CAP_GROQ", 1)
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    budget.record("groq", 1)
    assert llm.llm_available() is False
    st = llm.status()
    assert st["rewrite"] is False
    assert st["quota"]["kill_switch"] is True


def test_failover_to_cerebras_when_gemini_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DB", tmp_path / "lib.db")
    monkeypatch.setattr(config, "LLM_DAILY_CAP_GEMINI", 0)
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gem_fake")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "csk_fake")
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    spec = llm.resolve()
    assert spec["name"] == "cerebras"


def test_chat_refuses_when_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DB", tmp_path / "lib.db")
    monkeypatch.setattr(config, "LLM_DAILY_CAP_GROQ", 0)
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    llm.resolve.cache_clear()
    try:
        llm.chat([{"role": "user", "content": "hi"}])
        raise AssertionError("expected BudgetExceeded")
    except llm.BudgetExceeded:
        pass
