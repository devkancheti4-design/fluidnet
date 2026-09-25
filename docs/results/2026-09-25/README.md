# Results — 2026-09-25: the core, the suit, and ten real bugs

Every number here comes from a logged run whose output is in [`data/`](data). The harness scripts that produced
them are in [`harness/`](harness) — they were run from a scratch layout, so their paths are that layout's; they
document the method, they are not a turnkey benchmark. The taught rules used, including two written by an AI agent,
are in [`nets/`](nets).

**See it:** three pages built from these results — open the copies in [`docs/media`](../../media) in a browser:
[the core (3D)](../../media/fluidnet-core.html) · [the two modes](../../media/fluidnet-modes.html) ·
[with and without buggy](../../media/fluidnet-buggy.html). Live versions are on claude.ai
([core](https://claude.ai/artifact/LRkFgwd47Vm4nLWNhb3ECL) · [modes](https://claude.ai/artifact/ReNRdzejyQ22osnUubgEQW) ·
[buggy](https://claude.ai/artifact/QDPrmyaDzP9P7Rs9hfHu2e)); they open once the owner shares them.

Target: [pallets/click](https://github.com/pallets/click) at 06b2a67, 2,240 tests. The race: ten real single-token
bugs, one per fault kind, planted in click and caught by its own suite, each on a fresh copy with no history. No
file or line was named to anything under test unless a row says so.

## The architecture measured

fluidnet is the **core**: buggy locates, the taught nets generate candidates, a class property refutes before any
test, the suite certifies, and a fix ships only if it is the **only** passing program at its lines across all the
nets. An AI agent is the **suit**: it never decides and never writes a fix — it hands the core facts (a pointer,
a deciding test, vocabulary) when the core asks.

## The race, build by build (fluidnet with buggy, no model)

| build | byte-exact | correct | wrong | median time (exact) |
|---|---|---|---|---|
| released (fluidfix 0.16.0, fluidnet 42be787) | 4 / 10 | 5 / 10 | 0 | 435 s |
| + nets cheapest-first per file | 8 / 10 | 9 / 10 | 0 | — |
| **final**: + bounded searches, buggy redeployed as a hive, certified fixes must be unique | **8 / 10** | 8 / 10 + 2 refused as ambiguous | **0** | **367 s** |

The two refusals are real ambiguities: at `_textwrap.py:168` both `pass` and `+=` pass all 2,240 tests; at
`core.py:1877` both `and` and a sibling rewrite (`self.context_settings`) do. `pass` had been *certified* on an
earlier build — it drops the first-line indent of indented paragraphs — which is why a certified fix must now also
be the only one at its line.

## Against an AI agent alone

The same ten bugs, one agent at a time, on neutral copies, no network, no other copy of click, scored the same way.

| | agent alone | fluidnet alone (final) |
|---|---|---|
| byte-exact | **10 / 10** | 8 / 10, 2 refused |
| median time | **51 s** | 367 s |
| tokens | 506,431 | **0** |
| checked unique | no | **yes** |

The agent resolved both ambiguous bugs by reading the code. Nothing checked that it was right.

## The two modes (core + suit)

| | **speed** (`--mode speed`) | **token-saving** (`--mode thrift`) |
|---|---|---|
| how the agent is used | points at every bug; the core searches there | only when the core is stuck |
| correct | 9 / 10 byte-exact, 1 refused, 0 wrong | 10 / 10 (9 byte-exact), 0 wrong |
| median time | **178 s** | 367 s |
| agent calls · tokens | 12 · 574,175 | **2 · 97,753** |

- Speed: buggy never had to run. On `core.py:1877` the first net to run wrote the *wrong* fix and certification
  passed it; the uniqueness law found the other net's `and`, the agent supplied one test, and the core chose.
  Its one refusal (`_termui_impl.py:579`) is two programs that behave identically — `.get("LESS", "")` and a None
  guard; the core has no lane yet for accepting equivalence.
- Token-saving, on the fly ([`data/thrift3457.log`](data/thrift3457.log)): fluidnet located, found the ambiguity,
  asked the body for a test by itself, verified it separates the two fixes, and committed the fix **and** the new
  test — 284 s. That run replayed an agent's real answer (0 new tokens).
- Token counts are what the agent runtime reported, ~47,000 per call of fixed overhead. A lean request carries only
  the facts — a median ~450 tokens (estimated from request size); a real lean call awaits the Claude Code CLI on the
  measuring machine, which answered "Credit balance is too low".

## Live: the AI agent as an oracle, fluidnet as the core

fluidnet ran live (`watch --body … --mode thrift`); when two different fixes both passed the full suite it asked
the agent — used only as an **oracle**, with no tools — for one fact, blocked until the answer came, measured it,
and decided. The agent's answer reached fluidnet through a file bridge ([`harness/bridge.py`](harness/bridge.py)),
because the Claude Code CLI on the measuring machine had no credits; every question and answer is in
[`data/oracle/`](data/oracle), every run in [`data/live_oracle.jsonl`](data/live_oracle.jsonl).

| bug | the oracle supplied | fluidnet's decision | result |
|---|---|---|---|
| `core.py:1877` | one test (8.9 s) | the test passes `and` only | **fixed** — click's behaviour (`'cls'` for `"cls"`), committed with the test |
| `_textwrap.py:168` | two tests (11 s) | they pass `+=` and fail `pass` | **fixed, byte-exact**, committed with the tests |
| `_termui_impl.py:579`, before the law | NO-DIFFERENCE (5.7 s) | no lane to weigh the claim | refused, file untouched |
| `_termui_impl.py:579`, with the EQUIV law | NO-DIFFERENCE and a probe (67 s) | the probe reached every differing line, identical output, stable: x = 188 → SHIP_A, the smaller edit | **fixed, byte-exact** |

0 wrong fixes. The EQUIV law ([`laws/equiv.c`](../../../laws/equiv.c), authored by search from
[`docs/laws/EQUIVALENCE_LAW_PROMPT.md`](../../laws/EQUIVALENCE_LAW_PROMPT.md)) rules on eight measured bits and never
on what the oracle said: every SHIP is backed by one program written twice, a stable test seen to separate the two,
or a stable probe that reached every differing line and printed identical output.

**Tokens.** An empty call to the same agent runtime ("reply OK", no tools) cost 43,763 tokens in 1.8 s — its fixed
overhead. The oracle answers were 45,290 / 45,648 / 44,858 / 51,938 reported, so the data itself was ~1,100–8,200
tokens each. By the same subtraction the ten pointers of the speed mode carried ~44,000 tokens of data in all, not
481,390, and the token-saving mode's two asks ~10,000, not 97,753.

Disclosure: for `_textwrap.py:168` the relay added one line to the oracle's prompt describing `click.wrap_text`;
the other questions were fluidnet's own, verbatim, with "import click".

## Teach once — the novel becomes known

| rule | written by | held-out click bugs of that shape |
|---|---|---|
| swapped names in a call | hand, one example ([`nets/swapped_names_by_hand.py`](nets/swapped_names_by_hand.py)) | **11 / 11** byte-exact, 0 tokens each |
| swapped call arguments | an AI agent, one example, 88,475 tokens ([`nets/swapped_call_arguments_by_agent.py`](nets/swapped_call_arguments_by_agent.py)) | reaches 3 / 11; the core repaired all 4 in reach exact (incl. the one taught from), refused the 3 out of reach it ran, 0 wrong |

The agent learned the literal lesson of its one example (whole arguments trading places); the other eight held-out
bugs swap a name with a keyword name — a broader shape, one more teaching away. The hand rule's author had seen all
twelve bugs; the agent had seen one.

**A real multi-line bug** (click f58ca3e814, Sentinel `copy`/`pickle`): an agent wrote only the rule
([`nets/singleton_reduced_by_value_by_agent.py`](nets/singleton_reduced_by_value_by_agent.py), 106,916 tokens);
the core shipped a fix in 30 s that passes the full suite including the maintainer's own regression tests — one
hook where the maintainer added three, so not byte-identical. Four more real multi-line bugs are recreated and not
yet run.

## Work that is not a bug — `fluidnet sweep`

click's own migration commit 08a0d69 ("use super() consistently"), taught from one line
([`nets/super_call_migration.py`](nets/super_call_migration.py)) and swept over the code before that commit:
**23 sites certified in 4.7 s, 4 suite runs — 22 byte-identical to the maintainers, 1 where they deleted the method
instead, 2 held back because no test runs them, 0 wrong** ([`data/sweep_dry.json`](data/sweep_dry.json)).

## buggy, measured whole

On `_textwrap.py:168` buggy's default run (one worker, 240 s) measured 47 of 1,177 lines and cut the rest — the
bug's file was never reached. Redeployed as a hive (8 workers, 1,019 s) it measured all 1,177: the fault was the
**only** line whose mutant flips every failing test and breaks none, and buggy's one proposed repair — but as
`pass`, because buggy has no mutation for `-=`/`+=` (reported to buggy; confirmed there). fluidnet now redeploys
buggy as a hive sized from buggy's own measured rate whenever its first run leaves lines unmeasured.

## Does the novel become known? (real history)

565 real maintainer fixes (click, arrow, rich, sortedcontainers), replayed in commit order, each shape taught at
first sight: at the level of the exact token edit, 16% of fixes repeat an earlier shape in the same repository, flat
over time; at the level of ten pattern families (None guard, boundary, boolean logic, off-by-one, …), **38% repeat,
rising 31% → 40% → 43%** from a project's early to late history. The families cover 42% of fixes; the rest fit none
of the ten — a limit of the list, not proof they are new.

## What is not claimed

- A lean agent call's real token cost (estimated from request size only).
- An equivalence lane beyond one live case: the EQUIV law shipped `_termui_impl.py:579` on a measured probe; whether probe evidence is enough in general is to be measured on known-different pairs (none may ship).
- For failures that are output mismatches, a no-tools pointer gets no source frames; the core's own coverage lines
  should be added to the request.
- Harder bugs: four real multi-line bugs are recreated and not run; nothing beyond one-token and one multi-line bug
  is measured here.
- `repair --focus` is in fluidfix e09eb24 (not yet released) and `repair --budget` is uncommitted in fluidfix; on
  fluidfix 0.16.0 the uniqueness stage reports NOT CHECKED rather than passing silently.
