"""The chat loop of the Ask window, against a fake client and against the real SDK on a mock transport: no network."""

import json
import subprocess
import sys
from decimal import Decimal

import anthropic
import httpx2
import pytest

from duckkit import llm
from duckkit.app import claude
from duckkit.app.claude import MAX_TOOL_ROUNDS, Chat, LLMError, Progress, Text, ToolCall, ToolResult
from duckkit.testing import FakeAnthropic, chat_reply

TOOLS = [{"name": "run_sql", "description": "Run a query", "strict": True,
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
                           "additionalProperties": False}}]
QUERY = ("run_sql", {"query": "SELECT 1"})


def chat(spec, *replies, run_tool=lambda name, tool_input: ToolResult("1 row"), **kwargs) -> Chat:
    return Chat(spec, "You answer questions.", TOOLS, run_tool, client=FakeAnthropic(*replies), **kwargs)


def test_an_answer_streams_its_text(spec):
    c = chat(spec, chat_reply("Fresh grew most."))
    assert list(c.ask("Which aisle?")) == [Text("Fresh grew most.")]
    assert [m["role"] for m in c.messages] == ["user", "assistant"]


def test_a_tool_call_goes_round_and_ends_in_an_answer(spec):
    seen = []

    def run_tool(name, tool_input):
        seen.append((name, tool_input))
        return ToolResult("1 row", detail=[1])

    c = chat(spec, chat_reply(progress="Checking the months.", tools=(QUERY,)), chat_reply("Done."), run_tool=run_tool)
    events = list(c.ask("Which aisle?"))
    assert events == [Progress("Checking the months."), ToolCall(*QUERY, ToolResult("1 row", detail=[1])), Text("Done.")]
    assert seen == [QUERY]
    assert c.messages[2]["content"] == [{"type": "tool_result", "tool_use_id": "call-0", "content": "1 row",
                                         "is_error": False}]


def test_all_the_results_of_one_turn_go_back_in_one_message(spec):
    c = chat(spec, chat_reply(tools=(QUERY, QUERY)), chat_reply("Done."))
    list(c.ask("Which aisle?"))
    assert len(c.messages[2]["content"]) == 2


def test_a_failed_tool_tells_claude_and_the_answer_goes_on(spec):
    def run_tool(name, tool_input):
        raise ValueError("no such column")

    c = chat(spec, chat_reply(tools=(QUERY,)), chat_reply("Sorry."), run_tool=run_tool)
    events = list(c.ask("Which aisle?"))
    assert events[0].result.is_error and "no such column" in events[0].result.content
    assert c.messages[2]["content"][0]["is_error"] is True


def test_the_system_prompt_and_tools_stay_byte_stable(spec):
    """The prompt cache holds only if nothing before the history changes between requests."""
    c = chat(spec, chat_reply(tools=(QUERY,)), chat_reply("One."), chat_reply("Two."))
    list(c.ask("First", context="Period: all time"))
    list(c.ask("Second", context="Period: last 3 months"))
    first, *others = c.client.requests
    for request in others:
        assert request["system"] == first["system"] and request["tools"] == first["tools"]
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"} and first["cache_control"]


def test_the_context_goes_with_the_question_only(spec):
    c = chat(spec, chat_reply("Done."))
    list(c.ask("Why so high?", context="Page: Dashboard. Period: all time."))
    assert [b["text"] for b in c.messages[0]["content"]] == ["Page: Dashboard. Period: all time.", "Why so high?"]
    assert "Dashboard" not in json.dumps(c.client.requests[0]["system"])


def test_no_context_sends_only_the_question(spec):
    c = chat(spec, chat_reply("Done."))
    list(c.ask("Why so high?"))
    assert [b["text"] for b in c.messages[0]["content"]] == ["Why so high?"]


def test_the_history_only_grows(spec):
    """Thinking blocks are tied to the conversation: an edit of the history is refused or drops them."""
    c = chat(spec, chat_reply(tools=(QUERY,)), chat_reply("One."), chat_reply("Two."))
    list(c.ask("First"))
    list(c.ask("Second"))
    for earlier, later in zip(c.client.requests, c.client.requests[1:], strict=False):
        assert later["messages"][:len(earlier["messages"])] == earlier["messages"]


def test_each_response_goes_back_whole(spec):
    reply = chat_reply("Done.", progress="A note.")
    c = chat(spec, reply, chat_reply("Again."))
    list(c.ask("First"))
    list(c.ask("Second"))
    assert c.client.requests[1]["messages"][1]["content"] is reply.content


def test_the_settings_of_each_request(spec):
    c = chat(spec, chat_reply("Done."), model="claude-sonnet-5-5")
    list(c.ask("First"))
    request = c.client.requests[0]
    assert request["model"] == "claude-sonnet-5-5" and request["output_config"] == {"effort": "medium"}
    assert request["thinking"] == {"type": "adaptive", "display": "updates"}
    assert request["tool_choice"] == {"type": "auto"} and request["fallbacks"] == "default"
    assert set(request["betas"]) == {claude.PROGRESS_NOTES_BETA, claude.FALLBACK_BETA}


def test_a_model_with_no_fallback_asks_for_none(spec):
    c = chat(spec, chat_reply("Done."), model="claude-haiku-5-5")
    list(c.ask("First"))
    assert "fallbacks" not in c.client.requests[0] and c.client.requests[0]["betas"] == [claude.PROGRESS_NOTES_BETA]


def test_the_last_round_allows_no_tool_so_there_is_an_answer(spec):
    replies = [chat_reply(tools=(QUERY,)) for _ in range(MAX_TOOL_ROUNDS)] + [chat_reply("With what I have.")]
    c = chat(spec, *replies)
    assert list(c.ask("First"))[-1] == Text("With what I have.")
    assert [r["tool_choice"]["type"] for r in c.client.requests] == ["auto"] * MAX_TOOL_ROUNDS + ["none"]


def test_a_tool_call_in_the_last_round_is_an_error_not_silence(spec):
    replies = [chat_reply(tools=(QUERY,)) for _ in range(MAX_TOOL_ROUNDS + 1)]
    ran = []

    def run_tool(name, tool_input):
        ran.append(name)
        return ToolResult("1 row")

    c = chat(spec, *replies, run_tool=run_tool)
    with pytest.raises(LLMError, match="no answer after"):
        list(c.ask("First"))
    assert len(ran) == MAX_TOOL_ROUNDS and not c.messages


def test_an_error_keeps_its_message_without_the_anthropic_package(spec, monkeypatch):
    """A fake client needs no package, so the message mustn't turn into "the anthropic package is missing"."""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    c = chat(spec, chat_reply(stop_reason="max_tokens"))
    with pytest.raises(LLMError, match="cut off"):
        list(c.ask("First"))
    bug = chat(spec, ValueError("a bug of the caller"))
    with pytest.raises(ValueError, match="a bug of the caller"):
        list(bug.ask("First"))


def test_usage_adds_up_across_turns_with_cache_reads(spec):
    c = chat(spec, chat_reply(tools=(QUERY,), input_tokens=100, cache_write=1000, output_tokens=50),
             chat_reply("One.", input_tokens=100, cache_read=1000, output_tokens=50),
             chat_reply("Two.", input_tokens=100, cache_read=2000, output_tokens=50))
    list(c.ask("First"))
    list(c.ask("Second"))
    assert (c.usage.calls, c.usage.cache_read_tokens, c.usage.cache_write_tokens) == (3, 3000, 1000)
    expected = sum(claude.estimate_cost(c.model, 100, 50, read, write) for read, write in ((0, 1000), (1000, 0), (2000, 0)))
    assert c.usage.cost == expected


def test_a_spent_conversation_stops_before_it_sends(spec):
    c = chat(spec, chat_reply("Never sent."))
    c.usage.cost = claude.MAX_CONVERSATION_COST
    with pytest.raises(LLMError, match="start a new one"):
        list(c.ask("First"))
    assert not c.client.requests and not c.messages


def test_the_model_lists_come_from_one_table():
    assert set(claude.PRICES) == set(claude.MODELS)
    assert claude.FALLBACK_MODELS == {"claude-opus-5-5", "claude-sonnet-5-5"}
    assert claude.CHAT_MODELS == {"claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5"}
    assert claude.DEFAULT_MODEL in claude.CHAT_MODELS


def test_a_conversation_can_have_its_own_spend_limit(spec):
    c = chat(spec, chat_reply("One."), chat_reply("Never sent."), max_cost=Decimal("0.5"))
    list(c.ask("First"))
    c.usage.cost = Decimal("0.5")
    with pytest.raises(LLMError, match=r"\$0.50: start a new one"):
        list(c.ask("Second"))
    assert len(c.client.requests) == 1


def test_spend_is_checked_between_rounds_too(spec):
    c = chat(spec, chat_reply(tools=(QUERY,), output_tokens=200_000), chat_reply("Never sent."))
    with pytest.raises(LLMError, match="start a new one"):
        list(c.ask("First"))
    assert len(c.client.requests) == 1 and c.usage.cost >= Decimal(2)


@pytest.mark.parametrize(("stop_reason", "message"), [("refusal", "declined"), ("max_tokens", "cut off")])
def test_a_stop_says_why_and_the_conversation_goes_on(spec, stop_reason, message):
    c = chat(spec, chat_reply("One."), chat_reply(stop_reason=stop_reason), chat_reply("Three."))
    list(c.ask("First"))
    with pytest.raises(LLMError, match=message):
        list(c.ask("Second"))
    assert len(c.messages) == 2
    assert list(c.ask("Third")) == [Text("Three.")]
    assert len(c.messages) == 4


def test_an_api_error_says_why_and_the_conversation_goes_on(spec):
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://example.test"))
    c = chat(spec, error, chat_reply("Two."))
    with pytest.raises(LLMError, match="could not reach"):
        list(c.ask("First"))
    assert not c.messages and list(c.ask("Second")) == [Text("Two.")]


def test_a_caller_that_stops_reading_leaves_no_half_turn(spec):
    """A tool call with no result would make the API refuse the next question."""
    c = chat(spec, chat_reply(tools=(QUERY,)), chat_reply("Two."))
    events = c.ask("First")
    assert isinstance(next(events), ToolCall)
    events.close()
    assert not c.messages
    assert list(c.ask("Second")) == [Text("Two.")]


def test_no_key_says_where_to_set_it(spec):
    with pytest.raises(LLMError, match="no Anthropic API key"):
        Chat(spec, "system", TOOLS, lambda name, tool_input: ToolResult(""))


def test_a_model_with_no_price_is_refused(spec):
    with pytest.raises(LLMError, match="no price"):
        chat(spec, model="claude-unknown")


def test_llm_still_exports_what_it_did():
    for name in ("DEFAULT_MODEL", "PRICES", "LONG_PRICES", "LONG_PROMPT", "CACHE_WRITE", "FALLBACK_MODELS", "FALLBACK_BETA",
                 "Usage", "LLMError", "estimate_cost"):
        assert getattr(llm, name) is getattr(claude, name)


def test_loading_it_loads_neither_the_ingestion_nor_anthropic():
    """The browser app may load it, with or without the llm extra."""
    code = "import sys, duckkit.app.claude; print([m for m in ('duckkit.llm', 'typer', 'anthropic') if m in sys.modules])"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip() == "[]"


def sse(*events: dict) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def message(stop_reason: str, *blocks: tuple[dict, list[dict]]) -> bytes:
    """A streamed response as the API sends it: each block with its deltas."""
    usage = {"input_tokens": 100, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 90}
    events = [{"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "content": [],
                                                    "model": "claude-opus-5-5", "stop_reason": None,
                                                    "stop_sequence": None, "usage": usage}}]
    for index, (block, deltas) in enumerate(blocks):
        events.append({"type": "content_block_start", "index": index, "content_block": block})
        events += [{"type": "content_block_delta", "index": index, "delta": delta} for delta in deltas]
        events.append({"type": "content_block_stop", "index": index})
    events += [{"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {**usage, "output_tokens": 20}}, {"type": "message_stop"}]
    return sse(*events)


def test_the_real_sdk_builds_the_request_and_reads_the_stream(spec):
    """The fake can only agree with this code: here the anthropic package itself sends and parses, on a mock transport."""
    tool_turn = message(
        "tool_use",
        ({"type": "thinking", "thinking": "", "signature": ""},
         [{"type": "thinking_delta", "thinking": "Checking."}, {"type": "signature_delta", "signature": "sig"}]),
        ({"type": "tool_use", "id": "toolu_1", "name": "run_sql", "input": {}},
         [{"type": "input_json_delta", "partial_json": '{"query": "SELECT 1"}'}]))
    answer = message("end_turn", ({"type": "text", "text": ""}, [{"type": "text_delta", "text": "Fresh."}]))
    bodies, sent = [tool_turn, answer], []

    def handler(request):
        sent.append((dict(request.headers), json.loads(request.content)))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=bodies.pop(0))

    client = anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    c = Chat(spec, "You answer questions.", TOOLS, lambda name, tool_input: ToolResult("1 row"), client=client)
    events = list(c.ask("Which aisle?"))
    assert events == [Progress("Checking."), ToolCall("run_sql", {"query": "SELECT 1"}, ToolResult("1 row")), Text("Fresh.")]
    headers, first = sent[0]
    assert first["stream"] is True and first["thinking"] == {"type": "adaptive", "display": "updates"}
    assert first["fallbacks"] == "default" and first["output_config"] == {"effort": "medium"}
    assert claude.PROGRESS_NOTES_BETA in headers["anthropic-beta"] and claude.FALLBACK_BETA in headers["anthropic-beta"]
    second = sent[1][1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"][0]["signature"] == "sig", "a thinking block goes back whole"
    assert second[2]["content"][0]["tool_use_id"] == "toolu_1"
    assert c.usage.calls == 2 and c.usage.cache_read_tokens == 180
