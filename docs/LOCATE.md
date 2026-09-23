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

## Two laws, side by side — never blended

**The CAUSE law** ranks the lines the failing test *executed*: four evidence lanes (TIME, SPECTRUM, WHY,
SYMPTOM) graded strong or weak from eight measured bits, priority = the dense lexicographic rank of
(strong, weak), 0..15, 0 a veto. `src/fluidnet/laws/cause.c`, generated; ported verbatim; its own
`main()` mirrored in `tests/test_cause_law.py`.

**The OMISSION law** answers the question the CAUSE law is blind to — the fix that *adds* code the old
file never ran, a sixth of real fixes. Its eight bits are where the path stopped (`ENDED`, `NEXT`), where
code belongs (`TARGET`, `HEAD`), what a passing run did instead (`PASSONLY`, `DIVERGE`), the failure's
kind (`RAISED`, the regime: without an exception the priority is halved) and `RECENT`. Same rank
principle, so the two are comparable; rank 15 is unreachable by structure. `laws/omission.c`, generated;
`tests/test_omission_law.py`.

`fluidnet locate` prints both verdicts: *root cause, by the cause law* and *if the fix is code that is
MISSING — where it belongs, by the omission law*. A line can be a good answer to one and vetoed by the
other; nothing picks between them by a constant. On the fixture where a None-guard is missing and the
run dies with `AttributeError`, the omission law puts the line where the run ended at 14/15 — EDGE, SCOPE
and CONTRAST all strong — which is exactly where the guard goes.

## The eight bits, for a law

Every cause finding carries `bits`: `FRAME LITERAL RECENT BISECT DIVERGE EF_ALL EP_NONE IMPORT`; every
omission finding carries `ENDED NEXT TARGET HEAD PASSONLY RAISED DIVERGE RECENT`. Both are logged per
candidate on every real-bug run, so either table can be judged on held-out real fixes without re-running
anything. The prompts that produced the laws: `fluidfix/docs/laws/CAUSE_LAW_PROMPT.md` and
`docs/laws/OMISSION_LAW_PROMPT.md`.

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

## Measured on real bugs — click, 26 judged of 31

`examples/locate/real_bugs.py`, 2026-09-23: check out each fix's parent, deselect pre-existing failures,
bring in only the fix's test files, confirm red, locate blind. Ground truth is the old side of the fix's
hunks. WHEN off (a fix has no recorded introducing commit to grade a bisect against).

| | cause law | old hand sum | count-based baseline |
|---|---|---|---|
| guilty **file** ranked 1st | **9** | 11 | 3 |
| guilty file in top 5 | 18 | 18 | 22 |
| guilty **line** ranked 1st | 2 | 2 | — |
| guilty line in top 5 | 2 | 5 | — |
| guilty line in top 10 | 5 | 6 | — |

Read it straight. At file level the spectrum-based rankings put the guilty file first three times as often
as the count-based baseline (the baseline lists more files, so it catches up by the top 5). At line level
**neither ranking reaches**: the guilty line was among the law's candidates in only 8 of 26 cases. The
other 18 are faults of omission — the fix adds code the old file never ran — which is exactly what the
OMISSION law was then written for; it is measured beside the cause law on the rerun in progress.

In the 8 reachable cases every guilty line carried the same word, `EF_ALL` alone, and what outranked it
36 times of 46 was an import-time line containing an assertion literal. That is a table defect with a
stated principle — an unmeasured lane is silent, not weak — and the fix, replayed on the logged bits
before any kernel was asked for, is 3 better, 0 worse, 5 unchanged: `docs/laws/CAUSE_LAW_REVISION_PROMPT.md`.

Rich: the first run died on a suite timeout the harness did not catch (fixed); rerunning. Both numbers
will be here when they land, whatever they are.
