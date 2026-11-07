"""`duckkit.app.ask_window`: the Ask window, a drawer on the right of every page where the user asks about the data.

`common.sidebar` adds the Ask button when `spec.ask` is on, so an app needs no code of its own. A page can tell Claude
what it shows with `ask_context(text)`: its filters and headline numbers, built from the values it draws.

The drawer is `st.dialog(position="right")`. The page behind it is dimmed and can't be clicked, so no click can stop an
answer, and the page's summary stays right while the drawer is open. Closing the drawer doesn't rerun the page
(`on_dismiss="ignore"`), so an answer goes on to its end, and opening the drawer again shows it.

Under each answer: the rows of its last query, a "Queries" expander with the SQL that ran, and what the answer and the
conversation cost. A wrong number looks like a right one, so the SQL is always there to check. Each answer's cost also
goes to stdout as one line (`ask: …`, no question text), so a hosted app's logs show spend over time.

Answers are Markdown with their images and HTML taken out (`clean`): text in the data could lead Claude to write an
image whose URL carries data, and the browser would fetch it.
"""

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from duckkit.app import ask, claude, common
from duckkit.app.claude import (
    CHAT_EFFORT,
    CHAT_MODELS,
    DEFAULT_MODEL,
    MAX_CONVERSATION_COST,
    Chat,
    LLMError,
    Progress,
    Text,
    ToolCall,
)
from duckkit.spec import AppSpec

STATE = "ask-conversation"  # st.session_state keys
CONTEXT = "ask-context"
INCLUDE = "ask-include-screen"
PICKER = "ask-model"
# The app's notes on reading its data ("amounts are in pounds", "refunds are negative"), next to its main.py, so they
# ship with a hosted app. They go in the system prompt. The template seeds the file. Without it, the window still works.
DATA_NOTES_FILE = "data_notes.md"

new_client: Callable = claude.new_client  # tests and browser checks put a FakeAnthropic here


@dataclass
class Turn:
    """One question and its answer, as the drawer shows it."""

    question: str
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    saw_page: bool = False
    cost: Decimal = Decimal(0)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    done: bool = False  # stays False when the run stopped before the answer ended


@dataclass
class Conversation:
    """The drawer's conversation, kept in st.session_state across reruns. `chat` is None when it can't start: `error`
    says why (no key, say)."""

    model: str
    chat: Chat | None = None
    error: str | None = None
    turns: list[Turn] = field(default_factory=list)

    @property
    def cost(self) -> Decimal:
        return self.chat.usage.cost if self.chat else Decimal(0)


# ─── Markdown ───

_IMAGE = re.compile(r"!\[([^\]]*)\]\s*(\([^)]*\)|\[[^\]]*\])")
_REFERENCE = re.compile(r"^ {0,3}\[[^\]]+\]:.*$", re.MULTILINE)  # "[1]: https://…", the target of a reference image
_TAG = re.compile(r"</?[A-Za-z!][^>]*>")
_CODE = re.compile(r"(```.*?(?:```|$)|`[^`\n]*`)", re.DOTALL)  # a fenced block (open to the end while it streams), a span


def clean(text: str) -> str:
    """`text` with its images (inline and by reference) and its HTML tags taken out, so the browser fetches nothing.
    An image keeps its alt text. Streamlit's Markdown doesn't render HTML anyway: this is the second line. Each $ is
    escaped, so prices stay prices. Code stays as it is: Markdown renders nothing inside it, and SQL keeps its `$1`
    and `<`."""
    parts = _CODE.split(text)
    return "".join(part if i % 2 else clean_prose(part) for i, part in enumerate(parts))


def clean_prose(text: str) -> str:
    text = _IMAGE.sub(lambda m: m.group(1), text)
    text = _REFERENCE.sub("", text)
    return dollars(_TAG.sub("", text))


def dollars(text: str) -> str:
    """`text` with each $ escaped: Streamlit's Markdown reads "$4 and $5" as LaTeX."""
    return re.sub(r"(?<!\\)\$", r"\\$", text)


# ─── What the page shows ───

def page_id() -> str:
    """The page this run draws. Streamlit has no public name for it: the run context's page hash is internal, and is the
    same in the drawer's own reruns."""
    from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

    ctx = get_script_run_ctx()
    return ctx.page_script_hash if ctx else ""


def ask_context(text: str) -> None:
    """Tell the Ask window what this page shows: the page, its filters, its headline numbers. Build `text` from the
    values the page draws, and call it on each run. It goes to Claude with a question, while the toggle is on."""
    st.session_state[CONTEXT] = (page_id(), text)


def screen() -> str | None:
    """The summary of the page behind the drawer, or None when that page gave none."""
    page, text = st.session_state.get(CONTEXT) or (None, None)
    return text if page == page_id() else None


# ─── Settings and the conversation ───

def default_model(spec: AppSpec) -> str:
    """`[anthropic] model` in config.toml, when it is one of CHAT_MODELS."""
    model = spec.setting("anthropic", "model", default=DEFAULT_MODEL)
    return model if model in CHAT_MODELS else DEFAULT_MODEL


def effort(spec: AppSpec) -> str:
    """`[anthropic] effort` in config.toml: low, medium, high, xhigh or max."""
    return spec.setting("anthropic", "effort", default=CHAT_EFFORT)


def max_cost(spec: AppSpec) -> Decimal:
    """`[anthropic] max_conversation_cost` in config.toml: past this many $, a conversation stops. LLMError when it isn't
    a number above 0, so the drawer says what to fix."""
    value = spec.setting("anthropic", "max_conversation_cost", default=MAX_CONVERSATION_COST)
    try:
        limit = Decimal(str(value))
    except InvalidOperation:
        limit = None
    if limit is None or not limit.is_finite() or limit <= 0:
        raise LLMError(f"[anthropic] max_conversation_cost in config.toml is {value!r}: write a number of $ above 0")
    return limit


def notes(spec: AppSpec) -> str:
    """The app's notes on reading the data (DATA_NOTES_FILE, next to main.py), or "" without them."""
    try:
        return (spec.main_script().parent / DATA_NOTES_FILE).read_text().strip()
    except FileNotFoundError:
        return ""


def new_conversation(spec: AppSpec, model: str) -> Conversation:
    """A conversation with `model`, on the snapshot the pages read."""
    try:
        chat = Chat(spec, ask.system_prompt(spec, notes(spec)), ask.TOOLS,
                    ask.tool_runner(spec, lambda: common.con(spec)), model=model, effort=effort(spec),
                    max_cost=max_cost(spec), client=new_client(spec))
    except LLMError as e:
        return Conversation(model, error=str(e))
    return Conversation(model, chat)


def conversation(spec: AppSpec) -> Conversation:
    """This session's conversation: a new one at first, and after "New conversation"."""
    if STATE not in st.session_state:
        st.session_state[STATE] = new_conversation(spec, st.session_state.get(PICKER) or default_model(spec))
    return st.session_state[STATE]


def where(spec: AppSpec) -> str:
    """Which data the chat reads, in words."""
    if spec.app_db:
        return f"the published copy ({spec.app_db})"
    if spec.demo_db_path and spec.db_path.resolve() == spec.demo_db_path.resolve():
        return "the demo database: its data is made up"
    return "the local database"


def cost_log(model: str, turn: Turn) -> None:
    """One line per answer on stdout, which a hosted app's logs keep. No question text."""
    print(f"ask: model={model} input_tokens={turn.input_tokens} output_tokens={turn.output_tokens} "
          f"cost=${turn.cost:.4f}", file=sys.stdout, flush=True)


@dataclass(frozen=True)
class Totals:
    """What a conversation has used so far: its cost, and its tokens in (cache reads and writes too) and out."""

    cost: Decimal
    input_tokens: int
    output_tokens: int

    @classmethod
    def of(cls, usage: claude.Usage) -> Totals:
        return cls(usage.cost, usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
                   usage.output_tokens)


def charge(turn: Turn, before: Totals, after: Totals) -> None:
    """Give `turn` what it used between `before` and `after`."""
    turn.cost = after.cost - before.cost
    turn.input_tokens = after.input_tokens - before.input_tokens
    turn.output_tokens = after.output_tokens - before.output_tokens


# ─── Drawing ───

def queries(turn: Turn) -> list[ask.QueryResult]:
    return [call.result.detail for call in turn.calls if isinstance(call.result.detail, ask.QueryResult)]


def rows_line(call: ToolCall) -> str:
    if call.result.is_error:
        return f"Refused or failed: {call.result.content}"
    result = call.result.detail
    rows = len(result.rows)
    count = f"the first {rows} rows" if result.truncated else f"{rows} row{'' if rows == 1 else 's'}"
    return f"Returned {count}."


def frame(result: ask.QueryResult) -> pd.DataFrame:
    return pd.DataFrame(result.rows, columns=result.columns)


def cost_line(turn: Turn, conv: Conversation) -> str:
    tokens = f"{turn.input_tokens:,} in / {turn.output_tokens:,} out"
    return f"This answer ≈ ${turn.cost:.2f} ({tokens}) · conversation ≈ ${conv.cost:.2f} · {CHAT_MODELS[conv.model]}"


def show_answer_parts(spec: AppSpec, turn: Turn, conv: Conversation) -> None:
    """What goes under an answer: its error, the rows of its last query, the Queries expander, the cost."""
    if turn.error:
        st.warning(turn.error, icon=":material/warning:")
    elif not turn.done:
        st.warning("This answer stopped before its end: the page reran. Ask again.", icon=":material/warning:")
    ran = [call for call in turn.calls if call.name == "run_sql"]
    good = [call.result.detail for call in ran if not call.result.is_error]
    if good and good[-1].rows:
        common.table(frame(good[-1]), timezone=spec.timezone, height="auto")
    if ran:
        with st.expander(f"Queries ({len(ran)})", icon=":material/database:"):
            for call in ran:
                st.code(call.input.get("query", ""), language="sql", wrap_lines=True)
                st.caption(rows_line(call))
    if turn.done or turn.cost:
        st.caption(dollars(cost_line(turn, conv)) + ("" if turn.saw_page else " · without the page"))


def show_turn(spec: AppSpec, turn: Turn, conv: Conversation) -> None:
    with st.chat_message("user"):
        st.markdown(clean(turn.question))
    with st.chat_message("assistant"):
        if turn.text:
            st.markdown(clean(turn.text))
        show_answer_parts(spec, turn, conv)


def answer(spec: AppSpec, conv: Conversation, turn: Turn, context: str | None) -> None:
    """Stream the answer to `turn`, drawing it as it comes, and keep it in `turn`."""
    with st.chat_message("user"):
        st.markdown(clean(turn.question))
    with st.chat_message("assistant"):
        text_slot = st.empty()
        rest = st.empty()
        with rest.container():
            working = st.status("Working…", expanded=False)
        before = Totals.of(conv.chat.usage)
        try:
            for event in conv.chat.ask(turn.question, context=context):
                if isinstance(event, Text):
                    turn.text += event.text
                    text_slot.markdown(clean(turn.text))
                elif isinstance(event, Progress):
                    working.update(label=event.text.strip().splitlines()[-1][:120] or "Working…")
                elif isinstance(event, ToolCall):
                    turn.calls.append(event)
                    if turn.text and not turn.text.endswith("\n\n"):
                        turn.text += "\n\n"
                    if event.name == "run_sql":
                        working.write(rows_line(event))
            turn.done = True
        except LLMError as e:
            turn.error = str(e)
        finally:
            charge(turn, before, Totals.of(conv.chat.usage))
            if turn.cost:
                cost_log(conv.model, turn)
        with rest.container():
            show_answer_parts(spec, turn, conv)


def controls(spec: AppSpec, conv: Conversation, caption: str | None) -> Conversation:
    """The top of the drawer: the data line, the model picker and "New conversation". Returns the conversation, a new
    one when the model changed before the first question."""
    # A question sent in this run: the picker and "New conversation" are drawn before it is answered, and lock now.
    started = bool(conv.turns or st.session_state.get("ask-question"))
    st.caption(" · ".join(p for p in (f"Reads {where(spec)}", caption) if p))
    top = st.columns([3, 2], vertical_alignment="center")
    with top[0]:
        model = st.segmented_control("Model", list(CHAT_MODELS), format_func=CHAT_MODELS.get, default=conv.model, key=PICKER,
                                     disabled=started, label_visibility="collapsed",
                                     help="Locked after the first question: a new conversation can change it")
    with top[1]:
        # A callback runs before the rerun, so the rerun draws the new conversation.
        st.button("New conversation", icon=":material/add_comment:", disabled=not started, width="stretch",
                  on_click=lambda: st.session_state.pop(STATE, None))
    if model and model != conv.model and not conv.turns:
        conv = st.session_state[STATE] = new_conversation(spec, model)
    return conv


def page_toggle() -> str | None:
    """The "Include what's on screen" toggle, and what it lets through: the page's summary, or None."""
    include = st.toggle("Include what's on screen", value=True, key=INCLUDE,
                        help="A summary of this page (its filters and numbers) goes with each question")
    summary = screen()
    if not include:
        st.caption("Claude doesn't see the page: only your question goes.")
        return None
    if summary is None:
        st.caption("Claude has no view of this page: it gives no summary. Claude can still query the data.")
    else:
        with st.expander("What Claude sees of the page"):
            st.text(summary)
    return summary


def window(spec: AppSpec, caption: str | None = None) -> None:
    """The drawer's contents: the controls, the toggle, the conversation and the question box. A plain function, so
    tests can draw it without the dialog."""
    conv = controls(spec, conversation(spec), caption)
    summary = page_toggle()
    if conv.error:
        st.info(f"The Ask window can't start: {conv.error}.", icon=":material/key:")
        return
    for turn in conv.turns:
        show_turn(spec, turn, conv)
    live = st.container()
    question = st.chat_input("Ask about the data", key="ask-question")
    if question:
        turn = Turn(question, saw_page=summary is not None)
        conv.turns.append(turn)
        context = f"What the user is looking at:\n{summary}" if summary is not None else None
        with live:
            answer(spec, conv, turn, context)


# on_dismiss="ignore": closing the drawer doesn't rerun the page, so an answer goes on to its end.
@st.dialog("Ask", width="medium", position="right", icon=":material/forum:", on_dismiss="ignore")
def drawer(spec: AppSpec, caption: str | None = None) -> None:
    window(spec, caption)


def ask_button(spec: AppSpec, caption: str | None = None) -> None:
    """The Ask button, at the bottom right of the page, which opens the drawer. `caption` says how fresh the data is."""
    if st.button("Ask", icon=":material/forum:", key="ui-ask-button", type="primary",
                 help="Ask Claude about the data"):
        drawer(spec, caption)
