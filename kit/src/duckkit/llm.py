"""`duckkit.llm`: one structured call to Claude, and the gate before a paid run.

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

What the browser app needs too (the client, the prices, `Usage`, `LLMError`) is in `duckkit.app.claude`: the browser app
may not import this module. It stays importable from here.

A large paid run is a hard stop (docs/work/how-we-work.md): the user says yes in the chat first. `cost_gate` shows the
estimate of every run. It starts a small one at once (at most `SMALL_RUN` rows waiting), and a larger one, or a full
reclassification, only with `--yes`. The app adds the `--yes` command to the `ask` rules of its
`.claude/settings.json` (docs/work/how-we-work.md). Tests use `duckkit.testing.FakeAnthropic`: no network and no key.
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal

import typer

from duckkit.app.claude import (
    CACHE_WRITE,
    DEFAULT_MODEL,
    FALLBACK_BETA,
    FALLBACK_MODELS,
    LONG_PRICES,
    LONG_PROMPT,
    PRICES,
    LLMError,
    Usage,
    anthropic_module,
    api_error,
    estimate_cost,
    new_client,
    refusal_message,
)
from duckkit.spec import AppSpec

__all__ = ["CACHE_WRITE", "DEFAULT_MODEL", "EFFORT", "FALLBACK_BETA", "FALLBACK_MODELS", "LONG_PRICES", "LONG_PROMPT",
           "PRICES", "SMALL_RUN", "Claude", "LLMError", "Usage", "cost_gate", "estimate_cost"]

EFFORT = "low"  # simple, well-specified judgments: low effort holds the quality at a fraction of the cost
SMALL_RUN = 500  # rows waiting: a run with this many or fewer starts without --yes (cost_gate)


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
            raise LLMError(f"no price for the model {self.model!r}: add it to duckkit.app.claude.PRICES")
        self.client = self.client or new_client(self.spec)
        self.usage = Usage(self.model)

    def call(self, system: str, user: str, schema: dict, max_tokens: int = 16000) -> dict:
        """Send one request and return its answer, a dict that matches `schema`. Raises LLMError."""
        anthropic = anthropic_module()
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
        except anthropic.APIError as e:
            raise api_error(self.spec, e) from e
        self.usage.add(response.usage)
        if response.stop_reason == "refusal":
            raise LLMError(refusal_message(response))
        if response.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off (max_tokens): send a smaller batch")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LLMError(f"the answer has no text (stop reason: {response.stop_reason})")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"the answer is not the JSON the schema asks for: {e}") from e


def cost_gate(spec: AppSpec, what: str, rows: int, estimate: Decimal, yes: bool, command: str,
              full: bool = False) -> bool:
    """Whether a paid run may start, after one line with what it sends and costs. A small run starts at once: at most
    `SMALL_RUN` rows waiting, and not a full reclassification. A larger run, or a full reclassification (`full`: every
    decision made by the model is made again, such as an app's `--reclassify`), starts only with `yes`. Without it,
    print the command that runs it, and send nothing. Such a run is a hard stop (docs/work/how-we-work.md): the user says
    yes in the chat first, and the app adds the `--yes` command to the `ask` rules of its `.claude/settings.json`.

    `what` says what the run sends ("120 rows"). `rows` counts every row waiting, not only the rows this run sends,
    so a large run split into small ones (`--limit`) still needs `yes`. For a reclassification, the rows that it
    would decide again count as waiting. `command` is the command line to run it
    (`classify`)."""
    cost = "under $0.01" if estimate < Decimal("0.01") else f"about ${estimate:.2f}"
    if yes or (rows <= SMALL_RUN and not full):
        typer.echo(f"This run: {what}, for {cost}.")  # before the key is checked: it says what, not that it was sent
        return True
    why = "It is a full reclassification" if full else f"More than {SMALL_RUN} are waiting"
    typer.echo(f"This run would send {what} to Claude, for {cost}. {why}, so it needs --yes. Nothing was sent.")
    typer.echo(f"To run it: uv run {spec.cli} {command} --yes")
    return False
