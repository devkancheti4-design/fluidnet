# fluidnet

**You teach it a bug once, and it repairs every future one — with a proof, not a guess.**

fluidnet is a set of small, deterministic tools for the mechanical part of debugging. There is no model
in any of them — no weights, no prompt, no tokens. Decisions are made by generated integer laws over
measured facts; the only judge of a fix is your own test suite; the only thing that can *prove* one is a
property you wrote. Same input, same answer, every time. Open-ended bugs stay yours, by design.

**[Watch it run — 3:52, every command live](docs/media/fluidnet.mp4)** · [the full account](docs/FLUIDNET.md)

---

## The tools

### The repair guard — `fluidfix guard`
The core. You teach it a fault shape once — a signal, a rewrite, and a property of what the rewrite must
keep true — and from then on it repairs every instance of that shape it meets, in any file, any
repository: the property refuses wrong candidates before a single test runs, the suite accepts or
rejects the rest, and every rejection restores the file byte for byte. Nine shapes ship; seven more are
yours per dictionary, and you can run as many dictionaries as you like (`fluidnet watch`).

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
pytest -q        # 42 tests, each a real pytest project in a temp dir, nothing mocked
```

## What is measured

| | |
|---|---|
| repairs within a taught shape | 84/84 exact across seven syntactic positions never taught; 0/12 wrong accepts on a negative control |
| certification | 14/14 model-written fixes accepted, 29/29 adversarial refused, byte-exact rollback every time |
| the gate on model-written patches | 84 judged, no per-case tuning: correct 14/14 allowed, wrong/flaky/collateral 29/29 blocked, the overfit hole named |
| the locator on real click fixes | guilty file first 9 of 26 (previous file ranking: 3); at line level only 8 of 26 reachable — the other 18 add code, which is what the second verdict is for |
| multi-fault descent | 3 faults, 3 classes never taught together, 11 suite runs |
| real history, knowledge only | a generic vocabulary reaches ~2% of 565 real fixes, 75% of the single-token mechanical ones |

Full numbers, both levels, in [docs/LOCATE.md](docs/LOCATE.md) and [examples/real](examples/real). Read them straight.

AGPL-3.0-or-later.
