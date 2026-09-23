# `fluidnet locate` — where, when, and why a suite went red

Three lanes of evidence, every one mechanical, none predictive. A finding's confidence is the **count of
independent lanes that agree on it**, and a lane with no evidence says so instead of guessing.

```
fluidnet locate .                 # WHERE + WHEN + WHY, prints the ranking, writes .fluidfix/locate.json
fluidnet locate . --no-bisect     # skip WHEN (fast); --good <rev> to name a known-green revision
fluidnet float .                  # a floating icon: grey = green, red = red, click for the root cause
```

| lane | what it measures | evidence it produces |
|---|---|---|
| **WHERE** | the lines the failing test executed; the frames the failure quotes; the literals the assertion mentions; the lines git touched recently; and the **spectrum** — how much more the failing tests run a line than the passing ones (Ochiai) | `frame`, `literal`, `recent`, `executed`, `spectrum s (ef, ep)` |
| **WHEN** | automated `git bisect` in a throwaway worktree, the failing test as the oracle; the first bad commit's hunks intersected with WHERE | `when-commit <sha>` |
| **WHY** | the failing test and a passing test that reaches the same function, traced line by line; the first line where control flow or a local's value differs | `why-divergence` |

Pointing evidence outranks circumstantial — the SIGHT law's grading, reused. Files surface by their best
line, never by how many lines they execute: fluidfix's count-based file ranking once put a real guilty file
7th of 14, and the spectrum lane is the answer to that.

## What it says when it cannot know

- *no passing test calls f() — the WHY lane has no evidence.* One failing test and no sibling: nothing to
  diff against. Write the sibling; that is also the test the fix needs.
- *no green commit within the last 24; pass --good.* The bug is older than the lookback.
- *the failing test cannot run at \<sha\> (it did not exist there).* The test arrived with the fix — WHEN
  cannot use it as an oracle further back.
- *spectrum lane: no per-test coverage.* `pytest-cov` is missing from the interpreter that runs the suite.

## Two traps it already fell into, so you don't

**Stale bytecode across revisions.** `total * 2` and `total + 2` are the same length; two checkouts landed
in the same second; the green commit's `.pyc` was reused at the bad commit, the bad commit passed, and
bisect blamed the commit on top. Every run at a revision now purges `__pycache__` and runs `-B` with
`PYTHONDONTWRITEBYTECODE=1`. The same whole-second trap once fooled fluidfix's C oracle with make 3.81.

**Per-test coverage is silently wrong on Python 3.12+ with coverage 7.16** unless `COVERAGE_CORE=ctrace`:
the default `sysmon` core credits a line only to the *first* test that ran it, so the spectrum lane sees
nothing. The lane sets it. (Found by a peer session; see `research` notes.)

## The eight bits, for a law

Every finding carries `bits`: `FRAME LITERAL RECENT BISECT DIVERGE EF_ALL EP_NONE IMPORT`. Today the
lanes are combined by hand weights. A superoptimizer prompt for the law that should replace them —
`fluidfix/docs/laws/CAUSE_LAW_PROMPT.md` — takes exactly these bits, and because they are logged per
candidate on every run, that law can be judged on held-out real bugs without re-running anything.

## The floating icon

`fluidnet float <root>` keeps `locate.json` fresh — on every source change, and every `--interval` seconds
while red — and shows it as a small always-on-top badge. The badge is standard-library Tk and imports
nothing from fluidnet, so it runs under whichever Python here has Tk (the venv's Homebrew build has
none; python.org's and `/usr/bin/python3` do; `float` finds one). Drag to move, click to expand, right-click
to quit. `--headless` skips the badge and just keeps the JSON fresh for an editor to read.

## Measured

`tests/test_root_cause.py`: a git history of green → the breaking commit → an unrelated commit on top.
WHERE puts the guilty line first with four lanes; WHEN names the breaking commit, not the one on top;
WHY parts at the express branch against the passing sibling; with no sibling the WHY lane says so; the
working tree and HEAD are untouched afterwards.

Real bugs are next: 198 of the 565 mined fixes ship their own test; ground truth is the old side of each
fix's hunks; the metric is the rank of the best ground-truth line and of its file, against the count-based
baseline on the same cases. Not yet run — this page will carry the numbers when it has been.
