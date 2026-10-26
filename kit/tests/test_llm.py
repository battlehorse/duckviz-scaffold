"""duckkit.llm against a fake anthropic client: no network and no key."""

from decimal import Decimal

import anthropic
import httpx2
import pytest

from duckkit.llm import Claude, LLMError, cost_gate, estimate_cost
from duckkit.testing import FakeAnthropic, claude_reply

SCHEMA = {"type": "object", "properties": {"label": {"type": "string", "enum": ["a", "b"]}}, "required": ["label"]}


def claude(spec, *replies, **kwargs):
    client = FakeAnthropic(*replies)
    return Claude(spec, client=client, **kwargs), client


def test_a_call_sends_a_structured_cached_request_and_returns_the_answer(spec):
    c, client = claude(spec, claude_reply({"label": "a"}))
    assert c.call("You label rows.", "Row 1", SCHEMA) == {"label": "a"}
    request = client.requests[0]
    assert request["model"] == "claude-opus-5-5" and request["output_config"]["effort"] == "low"
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert request["system"] == [{"type": "text", "text": "You label rows.", "cache_control": {"type": "ephemeral"}}]
    assert request["messages"] == [{"role": "user", "content": "Row 1"}]
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]


def test_usage_adds_up_the_calls_with_their_cache_and_prices_them(spec):
    first = claude_reply({"label": "a"}, input_tokens=100, cache_write=10_000, output_tokens=200)
    second = claude_reply({"label": "b"}, input_tokens=100, cache_read=10_000, output_tokens=200)
    c, _ = claude(spec, first, second)
    c.call("s", "1", SCHEMA)
    c.call("s", "2", SCHEMA)
    # Claude Opus 5.5: 200 × $4 + 10,000 × $5 (a write, 1.25×) + 10,000 × $0.20 (a read) + 400 × $20, per million
    assert c.usage.cost == Decimal("0.0608")
    assert c.usage.line() == "API: 2 calls, 20200 input / 400 output tokens, ≈ $0.06"


@pytest.mark.parametrize("model, cost", [
    ("claude-opus-5-5", Decimal("24.20")),  # 1M in × $4 + 1M out × $20 + 1M cache reads × $0.20
    ("claude-sonnet-5-5", Decimal("12.20")),  # $2 + $10 + $0.20
    ("claude-haiku-5-5", Decimal("0.61")),  # $0.10 + $0.50 + $0.01
])
def test_each_model_has_its_published_prices(model, cost):
    assert estimate_cost(model, 1_000_000, 1_000_000, cache_read_tokens=1_000_000) == cost


def test_the_fallback_is_asked_only_of_the_models_that_have_it(spec):
    opus, opus_client = claude(spec, claude_reply({"label": "a"}))
    haiku, haiku_client = claude(spec, claude_reply({"label": "a"}), model="claude-haiku-5-5")
    opus.call("s", "u", SCHEMA)
    haiku.call("s", "u", SCHEMA)
    assert opus_client.requests[0]["fallbacks"] == "default"
    assert "fallbacks" not in haiku_client.requests[0] and "betas" not in haiku_client.requests[0]


@pytest.mark.parametrize("reply, message", [
    (claude_reply({}, stop_reason="refusal"), "declined"),
    (claude_reply({}, stop_reason="max_tokens"), "cut off"),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), "could not reach"),
])
def test_a_failed_call_raises_one_error_with_a_message(spec, reply, message):
    c, _ = claude(spec, reply)
    with pytest.raises(LLMError, match=message):
        c.call("s", "u", SCHEMA)


def test_an_unknown_model_is_refused_before_any_call(spec):
    with pytest.raises(LLMError, match="no price"):
        Claude(spec, model="claude-unknown", client=FakeAnthropic())


def test_without_a_key_claude_says_where_to_put_it(spec):
    with pytest.raises(LLMError, match=r"\[anthropic\] api_key"):
        Claude(spec)


def test_the_gate_runs_a_paid_command_only_with_yes(spec, capsys):
    assert cost_gate(spec, "12 rows", Decimal("0.0312"), yes=True, command="classify")
    assert capsys.readouterr().out == ""
    assert not cost_gate(spec, "12 rows", Decimal("0.0312"), yes=False, command="classify --limit 12")
    out = capsys.readouterr().out
    assert "12 rows" in out and "$0.03" in out and "Nothing was sent" in out
    assert f"uv run {spec.cli} classify --limit 12 --yes" in out
