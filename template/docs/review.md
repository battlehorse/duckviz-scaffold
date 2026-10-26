# Review standards

These are the standards for every change to the scaffold (duckviz-scaffold) and to the apps made from it. The
scaffold manages this file: an app adds its own rules in `.claude/project-rules.md`. The author checks a change
against them before opening a PR. The reviewer agent (`.claude/agents/reviewer.md`) checks the PR against them. The
reviewer gets the PR and this file, and nothing of the author's reasoning.

Each finding has a level:

- **Blocking**: the PR does not merge until the author fixes it. A bug, personal data, a spec file the PR touches but
  does not declare, a spec file marked *extends* that is not an extension, a weakened check, missing evidence for a
  check that applies, a file marked *revises* in a PR that holds more than the revision, or code or text that a
  reader cannot follow.
- **Should**: fix it in this PR, or say in the PR why not.
- **Nit**: fix it if it is cheap.

When the author and the reviewer still do not agree on a blocking finding after a few rounds, the author asks the
user.

Each standard below has a bad and a good example. The examples come from real changes, with the names made neutral.

## 1. Language

Write comments, docstrings, docs, CLI messages, skills and PR text in simplified English, after ASD-STE100. The
reader can be a person who reads English as a second language, or an agent. Neither can ask what you meant.

- One idea in each sentence. Keep sentences short, but do not cut words that the meaning needs: clarity comes
  first. `ste-lint.py`'s length findings are a hint, not a rule.
- Use the active voice. Say who does the action.
- Use the verb, not a noun made from it: "check the file", not "perform a check of the file".
- No semicolons. Use a list for three or more steps or conditions.
- No phrasal verbs ("spin up", "set up" as a verb, "carry out"): use one plain verb.
- No marketing words ("seamless", "robust", "powerful"). Give the number that shows the claim.
- Skills, CLI messages and error messages use the strict form of the rules. Docs and PR text use the structural
  rules in full, and the rules on words as a direction.

The `asd-ste100` skill rewrites a text, and its `scripts/ste-lint.py` checks the structural rules.

| Bad | Good |
|---|---|
| "The app owns its own interpretations, except what spend is." | "The contract decides what is spend. The app decides how to show it." |
| "Temperatures, to 0.1." | "Temperatures in °C, in steps of 0.1 °C (the hub logs one decimal)." |
| "It is important to note that this may potentially help to improve the load time." | "This can make the page load faster: 1.8 s, measured, against 4 s before." |

## 2. Canonical terms

**Canonical** means the one place where something is defined. A canonical term is the one name of a concept. A
canonical doc is the one doc that defines a concept or a behaviour. Everything else uses that name, and links to
that doc. See [canonical everything](https://naomi.com/canonical-everything-c85441a84e70?gi=2fc660f004b2).

- **One canonical term for one thing.** Use the same word for the same concept everywhere: in code, docs and the
  UI. Do not rotate synonyms.
- **Define each term once,** in its canonical doc: with a short definition, or a link for an outside tool. Other
  docs link to the definition.
- **Two names for two things:** when two columns or settings look alike, explain both and say how they differ.

| Bad | Good |
|---|---|
| "The CLI is a Typer app." | "The CLI is a [Typer](https://typer.tiangolo.com) app (a library that makes commands from Python functions)." |
| A doc says `precedence` in one table and `sort_order` in the next, for what looks like one column. | "`precedence` decides which rule wins. `sort_order` is only the order on the page." |
| Two test markers, `realdata` and `realhub`, with no word on how they differ. | One marker, `realdata`: a test that reads real, personal data on this machine. |

## 3. Docs

- **Each concept and each behaviour has one canonical doc.** Other docs link to it, and do not copy it: a copy
  drifts.
- **Put text in its canonical doc: the one whose topic it is.** How the app uses the contract goes in `architecture.md`, not
  `contract.md`. What a page shows goes in `dashboard.md`, not in a skill. A rule for Claude goes in CLAUDE.md, not
  in a doc that describes the template.
- **Describe every table, view and column**: what one row is, and what each column means.
- **Write a spec as a spec.** Say how the system works, not what you saw once: "Each day holds 96 slots of 15
  minutes", not "Observed: 96 slots".
- **Give a concrete example** for a rule or an encoding.
- **Use the right shape:** a list for cases, a table for a changelog or a comparison.

| Bad | Good |
|---|---|
| `slots_0_91`, `slots_0_95`, `slots_0_99`, with no explanation. | "`slots_0_91`: 92 slots (the day the clocks go forward). `slots_0_95`: 96 slots. `slots_0_99`: 100 slots (the day they go back)." |
| "A line is exceptional if it is marked so, or derived." | "A line is exceptional in three cases", then a list of the three. An override marks it exceptional. An override marks it not exceptional, so it never is. No override: the rules decide. |

## 4. Readable code

Write code for the person who reads it next. Shorter is not better if it takes longer to read.

- **Names say what a thing holds or does.** No one-letter names outside a short loop or a lambda. No unexplained
  short forms or suffixes.
- **One job for each function and each class.** If the docstring needs "and" to say what it does, split it.
- **Plain control flow.** No deep nesting. No packed tuple assignments, nested comprehensions or conditional
  expressions that the reader must decode. Use a helper with a name, or two plain lines.
- **Comments say why, not what.** They match the code, and change with it. Keep the comment density of the code
  around them.

Bad: a reader must decode the same expression twice, in one line.

```python
for key, into, *rest in verdicts:
    key, into = (new if key == old else key), (new if into == old else into)
```

Good: one helper with a name.

```python
def renamed(key):
    return new if key == old else key

for key, into, *rest in verdicts:
    key, into = renamed(key), renamed(into)
```

Bad: a comprehension inside a generator inside a filter.

```python
options = [d for d in (day + timedelta(days=k) for k in range(-3, 4))
           if first <= d <= last and (not slots or d > slots[-1].date())]
```

Good: name the week, then filter it.

```python
week = [day + timedelta(days=offset) for offset in range(-3, 4)]
after_last_shop = slots[-1].date() if slots else date.min
options = [d for d in week if first <= d <= last and d > after_last_shop]
```

Bad: names that the reader must look up (`lines_f`, `receipts_p`, `s`, `df` used for four different frames in one
module). Good: `lines_in_scope`, `receipts_in_period`, `weekly_spend`.

## 5. Simple solutions

- **Ask "is this needed?"** of every table, column, file, setting and skill. Delete what nothing reads.
- **A fixed value before a setting.** Make a value configurable only when a real user needs a different one.
- **No option or parameter that no app needs** (the options policy, in the scaffold's docs/template.md).
- **Reuse before new code.** Use duckkit, or what the app already has. Do not copy duckkit code into an app.
- **Fix the cause where it lives.** A gap in the scaffold gets fixed in the scaffold, not worked around with a
  deviation in each app.
- **Challenge a solution that is hard to explain.** If the PR text needs a long paragraph to justify a mechanism,
  look for a simpler one first.

| Bad | Good |
|---|---|
| A table stores every weather API reply "for safety". | Do not store them. The API returns any past hour again. |
| `APP_PORT` reads a setting, and docs mention two ports. | The app always serves on its one port. |
| An app opts out of two seeded files, because `copier update` brings them back. | The scaffold stops re-creating seeded files. The opt-outs go. |
| A skill that repeats the rules CLAUDE.md already holds. | Delete the skill. |

## 6. Solutions that do not break

- **No silent `except`.** Catch the narrowest error, and give the reason in a comment
  (`except TransactionException: pass  # no transaction open`).
- **Use the structure, not the text.** Do not match free text where a field, a key or a type exists.
- **Dates and times say their zone.** A naive local time is a choice: say so where the code makes it.
- **Tests are deterministic.** A fixed seed, a fixed clock, no network.
- **Tests check behaviour, not wording.** Assert on the data or the exit code. Assert on a message only for the
  part the user reads as a fact (a count, a name).
- **Tests check what the parameters promise.** When a generator takes a growth rate or weights, a test checks that
  its output keeps to them. A test that only checks "it runs" did not catch real bugs here before.

| Bad | Good |
|---|---|
| `assert "Restored curated decisions" in out` (breaks when the wording changes). | `assert "2 products, 8 skus" in out` (the counts are the fact). |
| A demo test checks only that the data has rows. | A demo test checks that spend grows at the rate asked, and that shops fall on the weekdays asked. |

## 7. Changes in a PR

- **Keep the PR to its purpose.** Put an unrelated fix in its own PR, or name it in the PR text.
- **Explain each change the reader did not ask for,** above all a removal: "The comment changed, the file did
  not." Without it, the reviewer has to ask.
- **Declare each spec file that the PR touches** (docs/spec.md) in its *Spec changes* section, marked *extends* or
  *revises*, each with its reason.
- **Report dependency changes and new tags** in the PR text.
- **Give the evidence that the PR keeps the spec** (docs/how-we-work.md): the tests that pass, the checks in the
  browser, the commands on real data.

## 8. Privacy

- No personal data in any file git commits: tests and docs use synthetic data.
- In the scaffold, no names of the apps made from it, and no real hosts, tokens or readings.
