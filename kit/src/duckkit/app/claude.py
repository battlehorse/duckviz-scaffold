"""`duckkit.app.claude`: Claude for the browser app and for the ingestion side.

It holds the client, the prices, what calls cost, and the chat loop of the Ask window. `duckkit.llm` builds on it, and
re-exports its names. It lives under `app`, because the browser app may not import `duckkit.llm`. It needs the `llm`
extra (the anthropic package), which it imports only when a call is made, so an app without the extra can load it.

`Chat` is one conversation. `Chat.ask` runs one question to its answer and yields what happens, so a page can show it as
it comes:
- the tools and the system prompt stay the same, byte for byte, so the prompt cache holds;
- the history only grows, with each response whole: thinking blocks belong to one model and one conversation, so a
  conversation keeps its model;
- `tool_choice` is `auto`, since forced tool use returns a 400 on these models. In the last round it is `none`, so a
  long question still ends in an answer;
- effort is set on each request: the models have different defaults.

Tests use `duckkit.testing.FakeAnthropic`: no network and no key.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal

from duckkit.spec import AppSpec

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
UPDATES_BETA = "thinking-display-updates-2026-08-18"  # short notes between tool calls, so a long answer doesn't look stuck

# $ per million tokens: (input, output, cache read). A cache write (5 minutes) costs 1.25 times the input price.
# Claude Haiku 5.5's cache read is the usual tenth of its input price (the pricing page gives no separate figure).
PRICES = {
    "claude-opus-5-5": (Decimal(4), Decimal(20), Decimal("0.20")),
    "claude-sonnet-5-5": (Decimal(2), Decimal(10), Decimal("0.20")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50"), Decimal("0.01")),
}
# The prices of a request whose prompt (input, cache writes and reads) is over LONG_PROMPT tokens, where they differ.
LONG_PROMPT = 100_000
LONG_PRICES = {"claude-haiku-5-5": (Decimal("0.50"), Decimal("2.50"), Decimal("0.05"))}
CACHE_WRITE = Decimal("1.25")
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}  # Claude Haiku 5.5 has no server-side fallback

CHAT_EFFORT = "medium"
CHAT_MAX_TOKENS = 64000
MAX_TOOL_ROUNDS = 8  # requests with tools in one answer: the one after them allows none, and must answer
MAX_CONVERSATION_COST = Decimal(2)  # $: past this, a conversation stops and asks for a new one


class LLMError(RuntimeError):
    """A call to Claude failed: the message says why, for the user."""


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
                  cache_write_tokens: int = 0) -> Decimal:
    """The cost in $ of one request's tokens with `model`. Raises LLMError for a model that PRICES does not know."""
    if model not in PRICES:
        raise LLMError(f"no price for the model {model!r}: add it to duckkit.app.claude.PRICES")
    prompt = input_tokens + cache_read_tokens + cache_write_tokens
    price_in, price_out, price_read = LONG_PRICES.get(model, PRICES[model]) if prompt > LONG_PROMPT else PRICES[model]
    return (input_tokens * price_in + cache_write_tokens * price_in * CACHE_WRITE + cache_read_tokens * price_read
            + output_tokens * price_out) / 1_000_000


@dataclass
class Usage:
    """The tokens of a run's calls, and what they cost."""

    model: str
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cost: Decimal = Decimal(0)  # each call priced by its own prompt size

    def add(self, usage) -> None:
        """Add the `usage` of one API response. After a server-side fallback, it counts only the attempt that
        answered, at this model's prices: the cost of such a call is approximate."""
        self.calls += 1
        self.input_tokens += usage.input_tokens
        self.cache_write_tokens += usage.cache_creation_input_tokens or 0
        self.cache_read_tokens += usage.cache_read_input_tokens or 0
        self.output_tokens += usage.output_tokens
        self.cost += estimate_cost(self.model, usage.input_tokens, usage.output_tokens,
                                   usage.cache_read_input_tokens or 0, usage.cache_creation_input_tokens or 0)

    def line(self) -> str:
        """One line for the command's output."""
        tokens_in = self.input_tokens + self.cache_write_tokens + self.cache_read_tokens
        return f"API: {self.calls} calls, {tokens_in} input / {self.output_tokens} output tokens, ≈ ${self.cost:.2f}"


def anthropic_module():
    """The anthropic package, or an LLMError that says how to install it."""
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("the anthropic package is missing: depend on duckkit[llm] (the llm extra)") from e
    return anthropic


def new_client(spec: AppSpec):
    """An anthropic client with the app's key, or an LLMError that says where to set one."""
    anthropic = anthropic_module()
    key = spec.anthropic_api_key()
    if not key:
        raise LLMError(f"no Anthropic API key: set {spec.where_anthropic_key()}")
    return anthropic.Anthropic(api_key=key)


def api_error(spec: AppSpec, error: Exception) -> LLMError:
    """The LLMError for an exception of the anthropic package. Any other exception comes back as it is, to raise."""
    try:
        anthropic = anthropic_module()
    except LLMError:  # no package, so it isn't one of its errors: a test's fake client, or the caller's own bug
        return error
    if isinstance(error, anthropic.AuthenticationError):
        return LLMError(f"the API key was rejected (expired or revoked?): {spec.where_anthropic_key()}")
    if isinstance(error, anthropic.APIStatusError):
        return LLMError(f"API error {error.status_code}: {error.message}")
    if isinstance(error, anthropic.APIConnectionError):
        return LLMError("could not reach the Anthropic API")
    if isinstance(error, anthropic.APIError):  # an answer the SDK could not read, say
        return LLMError(f"API error: {error}")
    return error


def refusal_message(response) -> str:
    """Why the model declined."""
    details = response.stop_details
    category = getattr(details, "category", None) or "no category"
    explanation = getattr(details, "explanation", None) or "no explanation"
    return f"the request was declined ({category}): {explanation}"


@dataclass
class Text:
    """A piece of the answer."""

    text: str


@dataclass
class Progress:
    """A note from Claude between tool calls."""

    text: str


@dataclass
class ToolResult:
    """What a tool gives back to Claude. `is_error` tells Claude that the call failed, so that it can try again."""

    content: str
    is_error: bool = False
    detail: object = None  # for the page, not for Claude: the rows of a query, say


@dataclass
class ToolCall:
    """A tool that ran, and its result."""

    name: str
    input: dict
    result: ToolResult


@dataclass
class Chat:
    """One conversation with Claude. `run_tool(name, input)` runs a tool and returns a ToolResult."""

    spec: AppSpec
    system: str
    tools: list[dict]
    run_tool: Callable[[str, dict], ToolResult]
    model: str = DEFAULT_MODEL
    effort: str = CHAT_EFFORT
    client: object = None
    messages: list[dict] = field(default_factory=list)
    usage: Usage = field(init=False)

    def __post_init__(self):
        if self.model not in PRICES:
            raise LLMError(f"no price for the model {self.model!r}: add it to duckkit.app.claude.PRICES")
        self.client = self.client or new_client(self.spec)
        self.usage = Usage(self.model)

    def ask(self, question: str, context: str | None = None) -> Iterator[Text | Progress | ToolCall]:
        """Run `question` to its answer. `context` says what the user is looking at. It goes with the question, never in
        the system prompt, so a change of filter doesn't break the cache.

        Raises LLMError. The conversation then goes back to where it was before the question, and can go on. It does the
        same when the caller stops reading: a tool call with no result would make the API refuse the next question."""
        before = len(self.messages)
        answered = False
        try:
            content = [{"type": "text", "text": text} for text in (context, question) if text]
            self.messages.append({"role": "user", "content": content})
            for tool_round in range(MAX_TOOL_ROUNDS + 1):
                self._check_spend()
                response = yield from self._request(allow_tools=tool_round < MAX_TOOL_ROUNDS)
                self.usage.add(response.usage)
                self._check_stop(response)
                self.messages.append({"role": "assistant", "content": response.content})
                calls = [block for block in response.content if block.type == "tool_use"]
                if not calls:
                    answered = True
                    return
                if tool_round == MAX_TOOL_ROUNDS:  # it should not happen, and silence would hide a paid-for failure
                    raise LLMError(f"no answer after {MAX_TOOL_ROUNDS} rounds of queries: ask for less at a time")
                yield from self._run_tools(calls)
        except LLMError:
            raise
        except Exception as e:
            error = api_error(self.spec, e)
            if error is e:
                raise
            raise error from e
        finally:
            if not answered:
                del self.messages[before:]

    def _check_spend(self) -> None:
        if self.usage.cost >= MAX_CONVERSATION_COST:
            raise LLMError(f"this conversation has cost ${self.usage.cost:.2f}: start a new one to go on")

    def _request(self, allow_tools: bool):
        """Stream one request, yield its text and notes, and return the whole response."""
        fallback = {"fallbacks": "default"} if self.model in FALLBACK_MODELS else {}
        betas = [UPDATES_BETA, *([FALLBACK_BETA] if fallback else [])]
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=CHAT_MAX_TOKENS,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            messages=self.messages,
            tools=self.tools,
            tool_choice={"type": "auto" if allow_tools else "none"},
            thinking={"type": "adaptive", "display": "updates"},
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},  # the history too: each round reads what the one before wrote
            betas=betas,
            **fallback,
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield Text(event.delta.text)
                    elif event.delta.type == "thinking_delta" and event.delta.thinking:
                        yield Progress(event.delta.thinking)
            return stream.get_final_message()

    def _check_stop(self, response) -> None:
        if response.stop_reason == "refusal":
            raise LLMError(refusal_message(response))
        if response.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off (max_tokens): ask for less at a time")

    def _run_tools(self, calls: list) -> Iterator[ToolCall]:
        """Run each tool, and send all the results back in one message."""
        results = []
        for call in calls:
            try:
                result = self.run_tool(call.name, call.input)
            except Exception as e:  # noqa: BLE001 — Claude reads the failure and can try another way
                result = ToolResult(f"the tool failed: {e}", is_error=True)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": result.content,
                            "is_error": result.is_error})
            yield ToolCall(call.name, call.input, result)
        self.messages.append({"role": "user", "content": results})
