"""`duckkit.llm`: one structured call to Claude, what the calls cost, and the gate before a paid run.

Needs the `llm` extra (`duckkit[llm]`, the anthropic package). The app keeps its own prompts and schemas: this module
only sends them, with the settings every app wants:
- structured output, so the answer is JSON that matches the app's schema (an enum in the schema keeps the model to
  the app's categories);
- the system prompt marked for the cache: the first call writes it, and the calls of the next 5 minutes read it at a
  fraction of the input price (a short system prompt is not cached);
- the server-side fallback, on the models that have it (`FALLBACK_MODELS`): when a safety classifier declines, the
  request is retried on Anthropic's fallback model;
- the API errors as one `LLMError`, with a message for the user;
- the tokens of every call in `Claude.usage`, and their cost.

A large paid run is a hard stop (docs/how-we-work.md): the user says yes in the chat first. `cost_gate` shows the
estimate of every run, starts a small one (at most `SMALL_RUN` rows) at once, and starts a larger one, or one that
redoes decisions, only with `--yes`. The app adds the `--yes` command to the `ask` rules of its
`.claude/settings.json` (docs/how-we-work.md). Tests use `duckkit.testing.FakeAnthropic`: no network and no key.
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal

import typer

from duckkit.spec import AppSpec

DEFAULT_MODEL = "claude-opus-5-5"
EFFORT = "low"  # simple, well-specified judgments: low effort holds the quality at a fraction of the cost
FALLBACK_BETA = "server-side-fallback-2026-07-01"

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
SMALL_RUN = 500  # rows: a run this small starts without --yes (cost_gate)


class LLMError(RuntimeError):
    """A call to Claude failed: the message says why, for the user."""


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
                  cache_write_tokens: int = 0) -> Decimal:
    """The cost in $ of one request's tokens with `model`. Raises LLMError for a model that PRICES does not know."""
    if model not in PRICES:
        raise LLMError(f"no price for the model {model!r}: add it to duckkit.llm.PRICES")
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


@dataclass
class Claude:
    """Claude, for one run of an app's command. `client` is the anthropic client (a fake one in tests)."""

    spec: AppSpec
    model: str = DEFAULT_MODEL
    effort: str = EFFORT
    client: object = None
    usage: Usage = field(init=False)

    def __post_init__(self):
        if self.model not in PRICES:
            raise LLMError(f"no price for the model {self.model!r}: add it to duckkit.llm.PRICES")
        if self.client is None:
            anthropic = _anthropic()
            key = self.spec.anthropic_api_key()
            if not key:
                raise LLMError(f"no Anthropic API key: set {self.spec.where_anthropic_key()}")
            self.client = anthropic.Anthropic(api_key=key)
        self.usage = Usage(self.model)

    def call(self, system: str, user: str, schema: dict, max_tokens: int = 16000) -> dict:
        """Send one request and return its answer, a dict that matches `schema`. Raises LLMError."""
        anthropic = _anthropic()
        fallback = {"betas": [FALLBACK_BETA], "fallbacks": "default"} if self.model in FALLBACK_MODELS else {}
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                **fallback,
            )
        except anthropic.AuthenticationError as e:
            raise LLMError(f"the API key was rejected (expired or revoked?): {self.spec.where_anthropic_key()}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("could not reach the Anthropic API") from e
        except anthropic.APIError as e:  # an answer the SDK could not read, say
            raise LLMError(f"API error: {e}") from e
        self.usage.add(response.usage)
        if response.stop_reason == "refusal":
            details = response.stop_details
            category = getattr(details, "category", None) or "no category"
            explanation = getattr(details, "explanation", None) or "no explanation"
            raise LLMError(f"the request was declined ({category}): {explanation}")
        if response.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off (max_tokens): send a smaller batch")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LLMError(f"the answer has no text (stop reason: {response.stop_reason})")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"the answer is not the JSON the schema asks for: {e}") from e


def _anthropic():
    """The anthropic package, or an LLMError that says how to install it."""
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("the anthropic package is missing: depend on duckkit[llm] (the llm extra)") from e
    return anthropic


def cost_gate(spec: AppSpec, what: str, rows: int, estimate: Decimal, yes: bool, command: str,
              redo: bool = False) -> bool:
    """Whether a paid run may start, after one line with what it sends and costs. A small run (at most `SMALL_RUN`
    rows, and not `redo`) starts at once: the spending limit of the API key caps it. A larger run, or one that redoes
    decisions already made (`redo`, such as an app's `--reclassify`), starts only with `yes`. Without it, print the
    command that runs it, and send nothing. Such a run is a hard stop (docs/how-we-work.md): the user says yes in the
    chat first, and the app adds the `--yes` command to the `ask` rules of its `.claude/settings.json`.

    `what` says what the run covers ("120 rows"), `rows` how many; `command` is the command line to run it
    (`classify`)."""
    cost = "under $0.01" if estimate < Decimal("0.01") else f"about ${estimate:.2f}"
    if yes or (rows <= SMALL_RUN and not redo):
        typer.echo(f"Sending {what} to Claude, for {cost}.")
        return True
    why = "It redoes decisions already made" if redo else f"Over {SMALL_RUN} rows"
    typer.echo(f"This run would send {what} to Claude, for {cost}. {why}, so it needs --yes. Nothing was sent.")
    typer.echo(f"To run it: uv run {spec.cli} {command} --yes")
    return False
