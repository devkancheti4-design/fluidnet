# fluidnet

**You teach it a bug once, and it repairs every future one — with a proof, not a guess.**

Not a model. No weights, no prompt, no tokens. Six integer laws decide, your own test suite judges, a
property you wrote proves. It repairs the fault shapes you taught it, refuses everything else with the
tree untouched, and can certify a fix somebody else wrote.

**[Watch it run — 3:52, every command live](docs/media/fluidnet.mp4)** · [how it works](docs/FLUIDNET.md)

## Install

```bash
git clone https://github.com/devkancheti4-design/fluidnet && cd fluidnet
python3 -m venv .venv && source .venv/bin/activate
pip install -e .           # pulls fluidfix>=0.16.0 from PyPI
fluidnet doctor          # must say: class-property gate: present · pytest-cov: present
fluidfix selfcheck       # must end: SELFCHECK PASS — 6 laws re-derived
```

If `doctor` complains, stop and fix that first. Everything below assumes it passed.

## Use it, in the order you will actually use it

**1. Run it on a red suite, before teaching anything.**
```bash
fluidfix guard . --dry-run        # proposes, shows the diff, restores the tree byte-exact
fluidfix guard . --commit         # same, but commits the repaired file when the suite goes green
```
Nine fault classes ship (`fluidfix kinds`). Exit 0 repaired, 2 refused. On refusal read
`.fluidfix/last_refusal.json` — every candidate it tried and the test that killed it.

**2. The second time you fix the same shape of bug by hand, teach it.**
```bash
fluidnet teach > rules.py         # the template: a signal, a rewrite, and a PROPERTY
```
Edit the three parts. Under 20 lines of Python. Keep `rules.py` in the repository it maintains.
Real, working ones to copy from: [`examples/real/rules.py`](examples/real/rules.py).

**3. Run with what you taught.**
```bash
fluidfix guard . --dictionary rules.py --commit
```
One dictionary holds up to 7 of your classes (kinds 4–7 and 13–15). Need more? A second file, a second
process: `fluidnet watch . --net rules.py --net more.py --commit` tries each in turn.

**4. Someone hands you a fix — a colleague, a model. Certify it before you trust it.**
```bash
fluidnet certify . --file pkg/thing.py --patch their_version.py
```
CERTIFIED means: red before, green on the full suite, stable on re-run, nothing else broken, file restored
byte-exact. Anything else is refused and says why.

**5. Two bugs in one file.** A single pass can't turn a two-fault file green, so it refuses. Use descent:
```bash
fluidnet descend pkg/thing.py --dictionary rules.py --test 'assert f(1) == 2' --test 'assert g() == 0' --write
```

**6. An agent proposes code changes? Gate them.**
```bash
fluidnet gate . --file pkg/thing.py --patch proposed.py --dictionary rules.py    # ALLOW / WARN / BLOCK
pip install 'fluidnet[mcp]' && fluidnet mcp                                       # the same, as MCP tools
```
The verdict vocabulary of a truth layer, for the one action a truth layer cannot judge. Details and the
replay of 84 model-written and adversarial patches: [docs/BRAIN.md](docs/BRAIN.md).

**7. It's red and you don't know where. Locate before you repair.**
```bash
fluidnet locate .        # WHERE (file, line), WHEN (the commit, by bisect), WHY (first divergence from a passing test)
fluidnet float .         # the same as a floating icon that turns red and shows the root cause on click
```
Two generated laws rule, side by side: the CAUSE law for the executed line that is wrong, the OMISSION law
for where code that is *missing* belongs — no hand weights, and a lane with no evidence says so.
[docs/LOCATE.md](docs/LOCATE.md).

**8. A folder of projects? Scan them all, and watch.**
```bash
fluidnet scan ~/code          # every project folder under it; http://127.0.0.1:7777
```
A ladybug walks the file grid on the scan's real events — the suite, the files WHERE opened, the spectrum
pass, the trace — and parks on the line the law ranked first. Nothing moves that did not happen.

## Using it efficiently

- **Teach on the second occurrence, not the first.** One instance is an incident; two is a shape.
- **Narrow signal, small rewrite.** A signal that matches every line buys candidates the suite has to
  reject one by one. `\.get\("(\w+)"\)` beats `\w+\.\w+`.
- **Every property ships with a control that fails it.** A property nothing can fail proves nothing; the
  gate reports a zero-input check as UNPROVEN, never PROVEN.
- **When it hands you a fix, run one input its tests never used.** The proof is over a bounded domain; the
  suite is a finite set of examples. One extra input is cheap and has caught a wrong fix that passed both.
- **Run it per commit, not per keystroke.** It runs your suite once per candidate.
- **Expect it to cover your repeats, not your history.** On 565 real fixes from four open-source projects
  a generic vocabulary reached about 2%; where a fix was one mechanical token it reached 75%. Replay your
  own last year of fixes against your dictionary — that number is the only one that matters to you.

## What you will get wrong setting it up

Every one of these happened this month.

| symptom | cause | fix |
|---|---|---|
| `fluidfix --version` looks right but `doctor` says the property gate is missing | a stale global `fluidfix` earlier on PATH than your venv — same version string, older code | use `.venv/bin/fluidfix`, or `pip install -e .` again inside the venv |
| refusal says *NO-OBSERVATIONS* after 0 suite runs | `pytest-cov` is not installed in the interpreter that runs your suite | `pip install pytest-cov` there; `doctor` checks it |
| "0 tests collected", refusal, nothing tried | your `pyproject` sets `filterwarnings = error` and a warning fires at collection | pass `--python` to a venv where your suite collects, or fix the warning |
| it refuses a bug you know it can fix | the suite was already red before the bug — pre-existing failures make nothing certifiable | get green first, or deselect the broken tests for the run |
| a wrong fix went green and got committed | your test only exercises the case where right and wrong agree (`k = 1`, both give the same answer) | write the property; add a test the fix never used |
| you loaded classes but the gate never refuses anything | properties live in the dictionary file; a file without `teach_property()` leaves the gate **failing open** — every candidate passes | `fluidfix.props.classes_without_properties([4,5,6,7])` after loading; put the property in the same file |
| the right candidate is never tried | candidate cap — a broad signal spends the budget on one attribute's siblings before reaching the next | narrow the signal, or `--max-candidates 64` when suite runs are cheap |
| two bugs, one file, refused | one pass repairs one fault | `fluidnet descend` |
| two runs on one checkout, both wrong | a second run mutated the tree while the first was judging | never run two guards on the same clone |
| a copied venv imports the wrong package | an editable install's `.pth` holds an absolute path | recreate the venv; don't copy it |
| it "repairs" a docstring | the signal matched prose; the suite can't judge prose so anything goes | exclude comment and docstring lines in the signal |
| real bugs from git history barely get fixed | real fixes bundle the mechanical part with other edits; the class does its part and the rest is yours | see [`examples/real`](examples/real) — both numbers are reported |

## Test

```bash
pytest -q        # 41 tests, each a real pytest project in a temp dir, nothing mocked
```

AGPL-3.0-or-later.
