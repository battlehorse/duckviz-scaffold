"""duckkit.llm against a fake anthropic client: no network and no key."""

from decimal import Decimal

import anthropic
import httpx2
import pytest

from duckkit.llm import PRICES, Claude, LLMError, Usage, cost_gate, estimate_cost
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


def test_usage_adds_up_the_calls_and_prices_them(spec):
    c, _ = claude(spec, claude_reply({"label": "a"}), claude_reply({"label": "b"}, input_tokens=500))
    c.call("s", "1", SCHEMA)
    c.call("s", "2", SCHEMA)
    assert (c.usage.calls, c.usage.input_tokens, c.usage.output_tokens) == (2, 1500, 400)
    assert c.usage.cost == estimate_cost("claude-opus-5-5", 1500, 400) == Decimal("0.014")
    assert c.usage.line() == "API: 2 calls, 1500 input / 400 output tokens, ≈ $0.01"


def test_a_cached_token_costs_a_tenth():
    usage = Usage("claude-opus-5-5", input_tokens=0, cached_tokens=1_000_000)
    assert usage.cost == PRICES["claude-opus-5-5"][0] / 10


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
