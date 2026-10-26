"""`duckkit.llm`: one structured call to Claude, what the calls cost, and the gate before a paid run.

Needs the `llm` extra (`duckkit[llm]`, the anthropic package). The app keeps its own prompts and schemas: this module
only sends them, with the settings every app wants:
- structured output, so the answer is JSON that matches the app's schema (an enum in the schema keeps the model to
  the app's categories);
- the system prompt cached, so the batches of one run pay for it once;
- the server-side fallback: when a safety classifier declines, the request is retried on Anthropic's fallback model;
- the API errors as one `LLMError`, with a message for the user;
- the tokens of every call in `Claude.usage`, and their cost.

A run that costs money is a hard stop (docs/how-we-work.md): the command estimates its cost and runs only with
`--yes` (`cost_gate`). Tests use `duckkit.testing.FakeAnthropic`: no network and no key.
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal

import typer

from duckkit.spec import AppSpec

DEFAULT_MODEL = "claude-opus-5-5"
EFFORT = "low"  # simple, well-specified judgments: low effort holds the quality at a fraction of the cost
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# $ per million tokens (input, output). A cached input token costs a tenth of an input token.
PRICES = {
    "claude-opus-5-5": (Decimal(4), Decimal(20)),
    "claude-sonnet-5-5": (Decimal(2), Decimal(10)),
    "claude-haiku-5-5": (Decimal(1), Decimal(5)),
}


class LLMError(RuntimeError):
    """A call to Claude failed: the message says why, for the user."""


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> Decimal:
    """The cost in $ of these tokens with `model`. Raises LLMError for a model that PRICES does not know."""
    if model not in PRICES:
        raise LLMError(f"no price for the model {model!r}: add it to duckkit.llm.PRICES")
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + cached_tokens * price_in / 10 + output_tokens * price_out) / 1_000_000


@dataclass
class Usage:
    """The tokens of a run's calls, and what they cost."""

    model: str
    input_tokens: int = 0  # including the tokens written to the cache
    cached_tokens: int = 0  # read from the cache
    output_tokens: int = 0
    calls: int = 0

    def add(self, usage) -> None:
        """Add the `usage` of one API response."""
        self.calls += 1
        self.input_tokens += usage.input_tokens + (usage.cache_creation_input_tokens or 0)
        self.cached_tokens += usage.cache_read_input_tokens or 0
        self.output_tokens += usage.output_tokens

    @property
    def cost(self) -> Decimal:
        return estimate_cost(self.model, self.input_tokens, self.output_tokens, self.cached_tokens)

    def line(self) -> str:
        """One line for the command's output."""
        return (f"API: {self.calls} calls, {self.input_tokens + self.cached_tokens} input / {self.output_tokens}"
                f" output tokens, ≈ ${self.cost:.2f}")


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
            import anthropic

            key = self.spec.anthropic_api_key()
            if not key:
                raise LLMError(f"no Anthropic API key: set {self.spec.where_anthropic_key()}")
            self.client = anthropic.Anthropic(api_key=key)
        self.usage = Usage(self.model)

    def call(self, system: str, user: str, schema: dict, max_tokens: int = 16000) -> dict:
        """Send one request and return its answer, a dict that matches `schema`. Raises LLMError."""
        import anthropic

        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as e:
            raise LLMError(f"the API key was rejected (expired or revoked?): {self.spec.where_anthropic_key()}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("could not reach the Anthropic API") from e
        self.usage.add(response.usage)
        if response.stop_reason == "refusal":
            raise LLMError(f"the request was declined: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off (max_tokens): send a smaller batch")
        text = next(block.text for block in response.content if block.type == "text")
        return json.loads(text)


def cost_gate(spec: AppSpec, what: str, estimate: Decimal, yes: bool, command: str) -> bool:
    """Whether a paid run may start. Without `yes`, print what it would do and cost, and how to run it.

    `what` says what the run covers ("120 rows"); `command` is the command line to run it (`classify`)."""
    if yes:
        return True
    typer.echo(f"This run would send {what} to Claude, for about ${estimate:.2f}. Nothing was sent.")
    typer.echo(f"To run it: uv run {spec.cli} {command} --yes")
    return False
