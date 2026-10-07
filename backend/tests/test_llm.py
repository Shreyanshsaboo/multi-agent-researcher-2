import pytest

import app.llm as llm
from app.config import Settings
from app.events import RunChannel

SETTINGS = Settings(groq_api_key="k", models={
    "coordinator": "big", "hn_scout": "small", "web_researcher": "other",
    "article_reader": "small", "writer": "big", "critic": "other",
})


@pytest.fixture(autouse=True)
def fresh_quota_state():
    llm._exhausted_until.clear()
    yield
    llm._exhausted_until.clear()


def test_chain_uses_primary_with_the_other_models_as_fallbacks():
    model, fallbacks = llm.build_model_chain("coordinator", SETTINGS)
    assert model.id == "big"
    assert [m.id for m in fallbacks.on_rate_limit] == ["small", "other"]


def test_exhausted_primary_is_skipped_and_the_switch_is_traced():
    channel = RunChannel("r")
    llm.mark_exhausted("big", 600)
    model, fallbacks = llm.build_model_chain("writer", SETTINGS, channel)
    assert model.id == "small"
    assert [m.id for m in fallbacks.on_rate_limit] == ["big", "other"]
    [event] = channel.events
    assert (event["type"], event["primary"], event["fallback"]) == ("model_fallback", "big", "small")


def test_when_every_model_is_exhausted_the_primary_is_kept():
    for model_id in ("big", "small", "other"):
        llm.mark_exhausted(model_id, 600)
    model, _ = llm.build_model_chain("critic", SETTINGS)
    assert model.id == "other"


def test_ollama_has_no_fallbacks():
    settings = Settings(llm_provider="ollama", ollama_model="llama3.2")
    model, fallbacks = llm.build_model_chain("coordinator", settings)
    assert model.id == "llama3.2" and fallbacks is None
