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


def test_a_long_haiku_prompt_costs_its_long_prompt_price():
    # 300K input tokens and 1K output: $0.50 and $2.50 per million over 100K prompt tokens
    assert estimate_cost("claude-haiku-5-5", 300_000, 1000) == Decimal("0.1525")
    assert estimate_cost("claude-haiku-5-5", 90_000, 1000) == Decimal("0.0095")


@pytest.mark.parametrize("model, cost", [
    # 50K input × $4/M + 1M output × $20/M + 50K cache reads × $0.20/M = $0.20 + $20 + $0.01
    ("claude-opus-5-5", Decimal("20.21")),
    ("claude-sonnet-5-5", Decimal("10.11")),  # $0.10 + $10 + $0.01
    ("claude-haiku-5-5", Decimal("0.5055")),  # $0.005 + $0.50 + $0.0005 (a cache read is a tenth of input)
])
def test_each_model_has_its_published_prices(model, cost):
    assert estimate_cost(model, 50_000, 1_000_000, cache_read_tokens=50_000) == cost


def test_the_fallback_is_asked_only_of_the_models_that_have_it(spec):
    opus, opus_client = claude(spec, claude_reply({"label": "a"}))
    haiku, haiku_client = claude(spec, claude_reply({"label": "a"}), model="claude-haiku-5-5")
    opus.call("s", "u", SCHEMA)
    haiku.call("s", "u", SCHEMA)
    assert opus_client.requests[0]["fallbacks"] == "default"
    assert "fallbacks" not in haiku_client.requests[0] and "betas" not in haiku_client.requests[0]


def response(status):
    return httpx2.Response(status, request=httpx2.Request("POST", "https://api.anthropic.com"))


def no_text():
    reply = claude_reply({})
    reply.content = []
    return reply


def not_json():
    reply = claude_reply({})
    reply.content[0].text = "Sure! Here are the labels."
    return reply


@pytest.mark.parametrize("reply, message", [
    (claude_reply({}, stop_reason="refusal"), r"declined \(cyber\): declined"),
    (claude_reply({}, stop_reason="max_tokens"), "cut off"),
    (no_text(), "no text"),
    (not_json(), "not the JSON"),
    (anthropic.AuthenticationError("bad key", response=response(401), body=None), "rejected"),
    (anthropic.InternalServerError("boom", response=response(500), body=None), "API error 500"),
    (anthropic.APIResponseValidationError(response=response(200), body=None), "API error"),
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
    assert not cost_gate(spec, "2 rows", Decimal("0.004"), yes=False, command="classify")
    assert "for under $0.01" in capsys.readouterr().out
    assert not cost_gate(spec, "12 rows", Decimal("0.0312"), yes=False, command="classify --limit 12")
    out = capsys.readouterr().out
    assert "12 rows" in out and "$0.03" in out and "Nothing was sent" in out
    assert f"uv run {spec.cli} classify --limit 12 --yes" in out


def test_the_fake_says_when_a_test_runs_out_of_replies(spec):
    c, _ = claude(spec, claude_reply({"label": "a"}))
    c.call("s", "1", SCHEMA)
    with pytest.raises(AssertionError, match="no reply left for request 2"):
        c.call("s", "2", SCHEMA)
