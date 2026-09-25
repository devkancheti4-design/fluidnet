# fluidnet

**You teach it a bug once, and it repairs every future one — with a proof, not a guess.**

fluidnet is a set of small, deterministic tools for the mechanical part of debugging. There is no model
in any of them — no weights, no prompt, no tokens. Decisions are made by generated integer laws over
measured facts; the only judge of a fix is your own test suite; the only thing that can *prove* one is a
property you wrote. Same input, same answer, every time. Open-ended bugs stay yours, by design.

**[Watch it run — 3:52, every command live](docs/media/fluidnet.mp4)** · [the full account](docs/FLUIDNET.md) ·
**[Results 2026-09-25](docs/results/2026-09-25)** — ten real click bugs: fluidnet alone, an AI agent alone, and both together

See it: [the core, in 3D](docs/media/fluidnet-core.html) · [the two modes](docs/media/fluidnet-modes.html) ·
[with and without buggy](docs/media/fluidnet-buggy.html) (open in a browser; live on claude.ai:
[core](https://claude.ai/artifact/LRkFgwd47Vm4nLWNhb3ECL) · [modes](https://claude.ai/artifact/ReNRdzejyQ22osnUubgEQW) ·
[buggy](https://claude.ai/artifact/QDPrmyaDzP9P7Rs9hfHu2e), open once the owner shares them)

---

## The tools

### The repair guard — `fluidfix guard`
The core. You teach it a fault shape once — a signal, a rewrite, and a property of what the rewrite must
keep true — and from then on it repairs every instance of that shape it meets, in any file, any
repository: the property refuses wrong candidates before a single test runs, the suite accepts or
rejects the rest, and every rejection restores the file byte for byte. Nine shapes ship; seven more are
yours per dictionary, and you can run as many dictionaries as you like (`fluidnet watch`).

### buggy finds, the nets fix — `fluidnet watch`
The guard knows *how* to fix a taught shape; on a real repository what it lacks is *where*. Measured on
click, a strictness regression at `parser.py:437` with 92 failing tests: the blind guard searched three
other files and refused at its 300 s budget without opening `parser.py`. [buggy](https://github.com/devkancheti4-design/buggy)'s
mutation lane put that line first in 279 s and proposed `<=` → `<`. So `watch` asks buggy first:

1. **buggy locates** — its files, best evidence first: a proposed repair's file (the mutant that flipped every
   failing test and broke none), then the mutation experiment and the introducing commit, then coverage, then
   where missing code belongs.
2. **fluidnet certifies buggy's proposed repair** — a patch fluidnet did not write, judged by the same
   gates as its own: red before, green on the full suite, stable, nothing else broken, file restored — and
   **the only fix at its line**: the nets search that line, and a *different* program that also passes means the
   suite cannot choose (AMBIGUOUS, nothing ships). Measured on click: `-=` → `pass` passed all 2,240 tests and
   was certified; it drops a paragraph's first-line indent that click's `+=` keeps.
3. **the nets repair on buggy's lines**, cheapest net first per file (fewest of its own signal hits there) — a
   broad net that went first on a whole file ran 49 minutes where the right net needed 45 s.
4. **when buggy's first run left the target unmeasured**, buggy is redeployed as a hive sized from its own
   measured rate (cores and free memory permitting): one worker measured 47 of 1,177 lines; eight measured all.
5. then each of buggy's whole files, each net bounded (`--file-budget`, 600 s), then fluidnet alone, bounded
   the same way. A suite buggy says it cannot judge (`harness`) never stops fluidnet judging for itself.

```bash
pip install "buggy-cli @ git+https://github.com/devkancheti4-design/buggy@main"   # the mutation lane is not in PyPI 0.1.0
fluidnet watch . --net rules.py            # dry-run: the certified repair is reported, the tree untouched
fluidnet watch . --net rules.py --commit   # -j N for more mutation workers (default 1, light on memory)
```

### Taught work with nothing red — `fluidnet sweep`
Not every repeat is a bug. A migration, a house convention, a deprecation: work you teach once and want done
at every site, where no test fails first. `sweep` runs every taught rewrite across the source and writes only
what three judges pass — the class's **property proves** the rewrite, the **suite runs** the line, and the
full suite is **green before and after**, stable on re-check. A rewrite that turns the suite red is found by
halving and refused; a line no test runs is listed, not written (`--trust-property` writes it on the proof
alone); a class that proposes two rewrites for one line is choosing, and is refused.

Measured on click's own history: the maintainers' "use super() consistently" commit (08a0d69, 2020) turned
`Base.method(self, …)` into `super().method(…)`. Taught from **one** of its lines and swept over the code as it
was before that commit: **23 sites certified in 4.7 s, 4 suite runs, no model** — 22 byte-identical to what the
maintainers wrote, 1 where they deleted a redundant method instead, 2 of theirs held back because no test runs
them, 0 wrong edits.

```bash
fluidnet sweep . --net migration.py            # dry-run: every certified rewrite as a diff, the tree untouched
fluidnet sweep . --net migration.py --commit   # keep them, one commit
```

### An AI agent as the suit — `--body`, two modes
fluidnet stays the core: it decides and proves every fix. An AI agent can be its **suit** — it never writes a fix
and never decides; it hands the core facts, as text, and the core does every file operation:

- **a pointer** — `LEAD: src/pkg/x.py:12` — which the core searches first (`--lead` takes one from a person too);
- **a deciding test**, when two fixes pass the whole suite — the core checks it passes exactly one of them
  (`fluidnet resolve`), then certifies that one with the test included and keeps the test;
- **vocabulary**, when no net knows the shape — a rule and its property, saved as a learned net, so every later
  bug of that shape is the core's alone.

| on ten real click bugs | **speed** (`--mode speed`) | **token-saving** (`--mode thrift`) | agent alone |
|---|---|---|---|
| correct | 9/10 byte-exact, 1 refused | 10/10 (9 byte-exact) | 10/10 |
| wrong fixes | 0 | 0 | 0 — but unchecked |
| median time | 178 s | 367 s | 51 s |
| agent tokens | 574,175 | 97,753 | 506,431 |

```bash
fluidnet watch . --net rules.py --body "claude -p --output-format json" --mode speed    # the agent points first
fluidnet watch . --net rules.py --body "claude -p --output-format json"                 # thrift: asked only when stuck
fluidnet watch . --net rules.py --lead src/pkg/x.py:12                                  # a lead from anyone, no body
```

The body is any command that reads the request on stdin and prints the reply. Token counts above are what an agent
runtime reported (~47,000 per call, mostly its own overhead); a request itself carries a median ~450 tokens of
facts. [All numbers, data and harness →](docs/results/2026-09-25)

### The locator — `fluidnet locate`
When the suite goes red and you don't know where. Three questions, answered with evidence: **where**
(the lines the failing test executed, the frames the failure names, the values the assertion mentions,
what git touched recently, and how much more the failing tests run a line than the passing ones),
**when** (which commit broke it — automated bisect in a throwaway worktree, the failing test as judge),
**why** (where the failing run parts from a passing one, traced line by line). Two verdicts, side by
side: the executed line that is *wrong*, and — for the common case where the fix is code that doesn't
exist yet — where the *missing* code belongs. Each candidate carries a rank out of 15 and the evidence
behind it; a lane with nothing to say, says so.

- **buggy, the pixel bug** — `fluidnet buggy <repo>`: a sprite on your screen that twitches while the suite is
  red. Click it and it crawls your file down the executed lines and parks on the answer. Drop it on a
  Finder window to scan that folder; double-click to pick one.
- **A folder of projects** — `fluidnet scan ~/code`: every project scanned in turn, watched live on a
  page where the ladybug moves only on real scan events.
- **In the editor** — [`vscode/`](vscode/): for VS Code, Cursor and Windsurf. The bug in the status bar
  with the last known result the moment a repo opens; the crawl as editor decorations; the verdict on
  hover; the line in the Problems pane; re-locates on every save. Without the extension,
  `fluidnet vscode-init` drops a task whose problem matcher does the same.

### The certifier and the gate — `fluidnet certify` · `fluidnet gate` · `fluidnet mcp`
A fix you didn't write — a colleague's, a model's — judged under your own suite: red before, green
after on the full suite, stable on re-run, nothing else broken, file restored byte-exact. As a gate it
speaks ALLOW / WARN / BLOCK, a class property first and the suite second, so it refuses what a suite
alone would accept. Also served as MCP tools for any agent runtime.

`fluidnet certify … --net rules.py` adds the second law: the nets search the lines the fix touches, and a
different program that also passes makes it AMBIGUOUS. When two fixes pass, `fluidnet resolve . --file F
--candidate a.py --candidate b.py --test tests/test_pin.py` checks that a *new* test passes exactly one of them,
then certifies that one with the test included.

### More than one bug at a time — `fluidnet descend`
A pass/fail suite throws a correct half-fix away. Descent counts how many tests fail, keeps a step when
the number drops and nothing new breaks, and walks to green — or undoes everything and refuses.

### The teaching kit — `fluidnet teach` · `fluidnet doctor`
The template for a class and its property, and a check that this install can prove rather than guess.

---

## Install

```bash
git clone https://github.com/devkancheti4-design/fluidnet && cd fluidnet
python3 -m venv .venv && source .venv/bin/activate
pip install -e .              # pulls fluidfix>=0.16.0 from PyPI; add '.[mcp]' for the MCP server
fluidnet doctor               # must say: class-property gate: present · pytest-cov: present
fluidfix selfcheck            # must end: SELFCHECK PASS — 6 laws re-derived
```

If `doctor` complains, stop and fix that first. The editor extension is the `.vsix` on the
[latest release](https://github.com/devkancheti4-design/fluidnet/releases): `code --install-extension fluidnet-0.2.0.vsix`.

## Use it, in the order you will actually use it

```bash
fluidnet locate .                                  # red and you don't know where: where, when, why
fluidfix guard . --dry-run                         # what the shipped shapes would repair; --commit to keep it
fluidnet teach > rules.py                          # the second time you fix a shape by hand, teach it
fluidfix guard . --dictionary rules.py --commit    # from now on it owns that shape, with proof
fluidnet certify . --file pkg/x.py --patch fix.py  # someone hands you a fix: certify before you trust it
fluidnet certify . --file pkg/x.py --patch fix.py --net rules.py   # ... and check it is the only fix at its lines
fluidnet watch . --net rules.py --body "claude -p --output-format json"   # an agent as the suit, asked only when stuck
fluidnet sweep . --net migration.py              # a taught migration or convention, every site, certified
fluidnet descend pkg/x.py --test 'assert …'        # two bugs in one file
fluidnet buggy .   ·   fluidnet scan ~/code        # buggy, the pixel bug; a folder of projects
```

## Using it efficiently

- **Teach on the second occurrence, not the first.** One instance is an incident; two is a shape.
- **Narrow signal, small rewrite.** A signal that matches every line buys candidates the suite must reject
  one by one.
- **Every property ships with a control that fails it.** A property nothing can fail proves nothing; the
  gate reports a zero-input check as UNPROVEN, never PROVEN.
- **When it hands you a fix, run one input its tests never used.** Proofs are over a bounded domain and a
  suite is a finite set of examples; one extra input is cheap.
- **Expect it to cover your repeats, not your history.** Replay your own last year of fixes against your
  dictionary — that number is the only one that matters to you.

## What you will get wrong setting it up

Every one of these happened while building it.

| symptom | cause | fix |
|---|---|---|
| `--version` looks right but `doctor` says the property gate is missing | a stale global `fluidfix` earlier on PATH than your venv | use the venv's `bin/fluidfix`, or `pip install -e .` again inside it |
| refusal after 0 suite runs, *NO-OBSERVATIONS* | `pytest-cov` missing from the interpreter that runs your suite | install it there; `doctor` checks |
| import errors on a project that is green in your own shell | the suite ran under fluidnet's interpreter, not your project's | a `.venv`/`venv` beside the code is picked up automatically; anything else, pass `--python`; `pytest-cov` must be in *that* venv |
| "0 tests collected" | `filterwarnings = error` in your pyproject fires at collection | fix the warning, or `--python` a venv where the suite collects |
| it refuses a bug you know it can fix | the suite was already red before the bug | get green first, or deselect the broken tests |
| a wrong fix went green and got committed | your test only checks inputs where right and wrong agree | write the property; add a test the fix never used |
| you loaded classes but the gate never refuses | properties live in the dictionary file; without them the gate fails open | put `teach_property()` beside `register()`; `classes_without_properties()` tells you |
| the right candidate is never tried | candidate cap — a broad signal spends the budget elsewhere | narrow the signal, or raise `--max-candidates` |
| two bugs, one file, refused | one pass repairs one fault | `fluidnet descend` |
| the locator's spectrum lane is empty on Python 3.12+ | per-test coverage needs `COVERAGE_CORE=ctrace` | the locator sets it; if you run coverage yourself, set it |
| bisect blames the wrong commit | stale bytecode across revisions when file sizes match | the locator purges it; never trust `.pyc` across checkouts |
| two runs on one checkout, both wrong | a second run mutated the tree while the first was judging | never run two guards on one clone |
| real bugs from git history barely get fixed | real fixes bundle the mechanical part with edits no file vouches for | see [`examples/real`](examples/real) — both numbers are reported |

## Test

```bash
pytest -q        # 95 tests, each a real pytest project in a temp dir, nothing mocked
```

## What is measured

| | |
|---|---|
| repairs within a taught shape | 84/84 exact across seven syntactic positions never taught; 0/12 wrong accepts on a negative control |
| certification | 14/14 model-written fixes accepted, 29/29 adversarial refused, byte-exact rollback every time |
| the gate on model-written patches | 84 judged, no per-case tuning: correct 14/14 allowed, wrong/flaky/collateral 29/29 blocked, the overfit hole named |
| the locator on real click fixes | guilty file first 9 of 26 (previous file ranking: 3); at line level only 8 of 26 reachable — the other 18 add code, which is what the second verdict is for |
| multi-fault descent | 3 faults, 3 classes never taught together, 11 suite runs |
| a real migration, taught from one line | click's super() commit: 23 sites certified, 22 byte-identical to the maintainers, 0 wrong, 4 suite runs |
| ten real click bugs, fluidnet with buggy | released build 4/10 byte-exact; final build 8/10 byte-exact, 2 refused as ambiguous, 0 wrong, median 367 s, no model |
| the same ten, fluidnet + an agent as the suit | speed 9/10 byte-exact, median 178 s · token-saving 10/10 correct with 2 agent calls · 0 wrong in both |
| a new shape taught once | by hand: 11/11 held-out click bugs byte-exact · by an agent from one example: 4/4 in its reach, 0 wrong, reach 3 of 11 |
| a real multi-line bug, rule by an agent | click f58ca3e814: the core shipped a fix in 30 s that passes the maintainer's regression tests (not byte-identical) |
| real history, knowledge only | a generic vocabulary reaches ~2% of 565 real fixes, 75% of the single-token mechanical ones |

Full numbers, both levels, in [docs/LOCATE.md](docs/LOCATE.md) and [examples/real](examples/real). Read them straight.

AGPL-3.0-or-later.
