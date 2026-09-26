from backend import config, llm


def setup_function(_fn):
    llm.resolve.cache_clear()


def test_resolve_offline_with_no_keys(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    assert llm.resolve() is None
    assert llm.llm_available() is False
    assert llm.status()["cost"] == "free-offline"


def test_resolve_prefers_ollama(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: True)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    spec = llm.resolve()
    assert spec["name"] == "ollama"
    assert spec["cost"] == "free-local"


def test_resolve_groq_when_no_ollama(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gem_fake")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    spec = llm.resolve()
    assert spec["name"] == "groq"
    assert spec["model"] == "qwen/qwen3.8-27b"
    assert spec["cost"] == "free-tier"


def test_nvidia_used_only_after_other_free_keys(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi_fake")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-paid")
    monkeypatch.setattr(config, "LLM_ALLOW_PAID", False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    llm.resolve.cache_clear()
    spec = llm.resolve()
    assert spec["name"] == "nvidia"
    assert spec["model"] == "deepseek-ai/deepseek-v4-pro"
    assert spec["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_forced_provider_needs_key(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    llm.resolve.cache_clear()
    assert llm.resolve() is None


def test_using_provider_pins_gemini_over_groq(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gem_fake")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    with llm.using_provider("gemini"):
        spec = llm.resolve()
        assert spec["name"] == "gemini"
        assert spec["model"] == config.GEMINI_MODEL
    assert llm.resolve()["name"] == "groq"


def test_assert_provider_missing_key(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "")
    try:
        llm.assert_provider("cerebras")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not configured" in str(exc)


def test_assert_provider_unknown():
    try:
        llm.assert_provider("madeup")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Unknown" in str(exc)


def test_assert_provider_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DB", tmp_path / "lib.db")
    monkeypatch.setattr(config, "LLM_DAILY_CAP_GROQ", 0)
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake")
    try:
        llm.assert_provider("groq")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "cap" in str(exc).lower()


def test_retry_after_seconds_parses_groq_message():
    assert llm._retry_after_seconds("Please try again in 6.52s.") == 6.92
    assert llm._retry_after_seconds("rate limit") == 8.0


def test_choices_include_auto_and_select(monkeypatch):
    monkeypatch.setattr(llm, "ollama_running", lambda: False)
    ids = {row["id"] for row in llm.choices()}
    assert {"auto", "groq", "gemini", "cerebras", "nvidia", "select"} <= ids
    assert "ollama" not in ids
    assert "cloudflare" not in ids


def test_parse_json_object_repairs_groq_bare_role_id():
    broken = (
        '{"summary":"HR pro.","roles":[{"id":"role.0","bullets":'
        '[{"id":"role.0.b2","text":"Identified talent gaps."}]},'
        '"role.1","bullets":[{"id":"role.1.b1","text":"Managed hiring."}]}],'
        '"projects":[],"skill_groups":[],"audit":{"interview":"Yes",'
        '"reject_reasons":[],"gaps":[],"notes":["ok"]}}'
    )
    data = llm.parse_json_object(broken)
    assert data["roles"][0]["id"] == "role.0"
    assert data["roles"][1]["id"] == "role.1"
    assert data["roles"][1]["bullets"][0]["id"] == "role.1.b1"


def test_salvage_failed_generation_from_openai_body():
    class FakeErr(Exception):
        def __init__(self):
            super().__init__("Error code: 400")
            self.body = {
                "error": {
                    "code": "json_validate_failed",
                    "failed_generation": (
                        '{"summary":"ok","roles":[{"id":"role.0","bullets":'
                        '[{"id":"role.0.b1","text":"Did hiring."}]},'
                        '"role.1","bullets":[{"id":"role.1.b1","text":"Payroll."}]}],'
                        '"projects":[]}'
                    ),
                }
            }

    out = llm._salvage_failed_generation(FakeErr())
    data = llm.parse_json_object(out)
    assert [r["id"] for r in data["roles"]] == ["role.0", "role.1"]


def test_extract_failed_generation_from_repr_string():
    raw = (
        "Error code: 400 - {'error': {'message': \"Failed to generate JSON.\", "
        "'code': 'json_validate_failed', 'failed_generation': "
        '\'{"summary":"ok","roles":[{"id":"role.0","bullets":'
        '[{"id":"role.0.b1","text":"Hiring."}]}],"projects":[]}\'}}'
    )
    blob = llm.extract_failed_generation(Exception(raw))
    data = llm.parse_json_object(blob)
    assert data["summary"] == "ok"
