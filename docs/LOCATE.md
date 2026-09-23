# `fluidnet locate` — where, when, and why a suite went red

Three lanes of evidence, every one mechanical, none predictive. A finding's confidence is the **count of
independent lanes that agree on it**, and a lane with no evidence says so instead of guessing.

```
fluidnet locate .                 # WHERE + WHEN + WHY, prints the ranking, writes .fluidfix/locate.json
fluidnet locate . --no-bisect     # skip WHEN (fast); --good <rev> to name a known-green revision
fluidnet buggy .                  # buggy, the pixel bug: grey = green, red = red, click for the root cause
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
- *when: at least as old as \<sha\> (\<date\>, HEAD~N) — red at every revision the failing test can run
  at.* No green revision was found: the fault is at least that old. WHEN probes HEAD~1, ~2, ~4 … along
  the first-parent line, then bisects the boundary where the test stops being runnable, so 4,000 commits
  cost about twenty test runs. Read the bound with one caveat: far back, "red" can also mean the feature
  the test exercises did not exist yet.
- *when: one of N commits the test cannot run at.* Bisect narrowed the first bad commit to revisions where
  the test cannot be evaluated (a skip to git bisect, never a verdict).
- *spectrum lane: no per-test coverage.* `pytest-cov` is missing from the interpreter that runs the suite.

## Four traps it already fell into, so you don't

**Stale bytecode across revisions.** `total * 2` and `total + 2` are the same length; two checkouts landed
in the same second; the green commit's `.pyc` was reused at the bad commit, the bad commit passed, and
bisect blamed the commit on top. Every run at a revision now purges `__pycache__` and runs `-B` with
`PYTHONDONTWRITEBYTECODE=1`. The same whole-second trap once fooled fluidfix's C oracle with make 3.81.

**Per-test coverage is silently wrong on Python 3.12+ with coverage 7.16** unless `COVERAGE_CORE=ctrace`:
the default `sysmon` core credits a line only to the *first* test that ran it, so the spectrum lane sees
nothing. The lane sets it. (Found by a peer session; see `research` notes.)

**A src layout with an editable install tests HEAD at every revision.** Measured on click 2026-09-24: the
bisect worktree at HEAD~300 imported HEAD's `src/click` through the venv's `.pth`, so every revision ran
the same code and bisect could only ever confirm HEAD. Flat layouts were spared by pytest's rootdir
insertion; src layouts were silently wrong. Every run at a revision now puts that checkout's own `src`
and root first on `PYTHONPATH`.

**The test that arrives with the fix is no oracle before its own commit.** The failing tests' files now
travel into every revision by default. When the modern file cannot even be collected at an old revision
(click's `tests/test_basic.py` imports `click._utils`, which did not exist before 2026), the step falls
back to the revision's own file plus only the failing tests and what they reference, transitively, with
imports and assignments guarded; an error raised *in the test file* under that fallback means the test
could not be evaluated there, a skip, while a failure raised in the code under test is still a verdict.
Carrying everything the old file lacked was tried first and shrank the reach on click from 2014 to 2026.

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

## buggy, the pixel bug

`fluidnet buggy <root>` (alias `float`) keeps `locate.json` fresh — on every source change, and every `--interval` seconds
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
**Revision 2 is the law that ships** (`laws/cause.c`; revision 1 kept as `laws/cause_r1.c`): 16 of 144
words moved, all of them import-only, the anchors intact, `IMPORT + LITERAL` at 2 not 3. The real kernel
replayed on the same held-out bits: 3 better, 0 worse, 5 unchanged. Live, the `def` line of a function
that only survives the veto by running at import dropped from 4 to 3 while the guilty line held.

Rich, 2026-09-24, before and after the candidate pool was widened (see the section below). Ranks are in
the order the tool presents — the law's rank, then the spectrum tie-break — with ties given their
mid-rank. (The harness used to group ties by the old hand-weight score, which reported a rank-1 line as
42.5 once the pool grew; `examples/locate/real_rich.json` carries both numbers.)

| | narrow pool, 29 judged | **wide pool, 35 judged** | old hand sum, wide |
|---|---|---|---|
| guilty **file** first | 19 | **21** | 20 |
| guilty file in top 5 | 24 | **33** | 30 |
| guilty **line** first | 3 | **3** | 2 |
| guilty line in top 5 | 6 | **8** | 5 |
| guilty line in top 10 | 8 | **12** | 5 |
| guilty line never a candidate | 18 | **7** | — |

The widening moved eleven guilty lines from "never measured" to "ranked", and the top did not pay for it:
the law's order beats the old hand sum at every depth. The seven still missing are omissions the failing
test never ran. In the pool, the guilty line's word is `EF_ALL` alone in 53 of 76 cases, and what
outranks it is overwhelmingly other `EF_ALL`-only lines ordered by the spectrum: on rich, as on the
long-lived bugs below, the bits rarely separate the guilty line and the spectrum does the ordering.
Clearing `RECENT` in a replay over the logged bits changes one case. The omission law reaches the
guilty line in the top 5 twice of 35.

## Measured on the bugs that lived longest — blind

The question was whether this locates or only looks things up. `examples/locate/bug_ages.py` dated the
guilty lines of 174 real, tested fixes across click, rich, arrow and sortedcontainers by blame: 47 were
under a month old when fixed, 54 under a year, 40 under three years, 28 under eight, and 5 older than
eight years. `examples/locate/longlived.py` took the five oldest, checked out each fix's parent, brought
in only the maintainers' regression test, and ran `locate` with nothing else: no `--good`, no hint of the
file, the fix never seen. Ground truth is the old side of the fix's hunks. 2026-09-24:

| fix | file | born | pool | guilty line's rank | WHEN |
|---|---|---|---|---|---|
| click `762c97ee` double-bracketed choices | core.py, 3,635 lines | 2014-04-24, the initial commit | 941 | **28** — the guilty branch's body at 6 | at least 2014-06-14 (HEAD~1024) |
| click `70c673d3` help-option eagerness | core.py, 3,029 | 2014-05-07 | 832 | **11** | at least 2014-05-06 (HEAD~1024) |
| click `2468b709` readline backspace | termui.py, 892 | 2014-05-29 | 151 | **20** | at least 2020-06-29 (HEAD~512) |
| click `c326df95` close callbacks on exit | core.py, 3,007 | 2014-04-24 | 586 | not a candidate | at least 2014-05-06 |
| arrow `b8a9df75` floats in humanize | locales.py, 5,269 | 2013-05-27 | 82 | **32** | at least 2020-09-19 (HEAD~64) |

*Pool* is every line every failing test executed — the law's R0 keeps nothing else. Read it straight:

- On four of five, a 900-to-5,000-line file becomes a reading list of 11 to 32 lines with the guilty line
  on it. That is what the tool is worth on a bug nobody found for a decade: not the line, the page.
- These lines carry one bit, `EF_ALL`. No frame (the failures are false assertions on rendered output),
  no literal, no recency (the lines are older than the test), no bisect (as old as the repo). Within the
  law's single-bit band the order is the spectrum's, so on the hardest real bugs the locator degrades to
  a strict veto plus spectrum-based fault localisation. It does not pretend otherwise.
- The fifth is a pure omission — the fix adds `self.close()` to `Context.exit` — and the failure is an
  assertion after `runner.invoke` returns, so no lane reaches the function: the cause law cannot (the
  missing line was never run) and the omission law's edge bits point at the runner's teardown, not at the
  exit. A miss, and the kind of miss the omission law's held-out measurement is for.
- WHEN's bound is honest and bounded by the test's reach, and one is a warning: at 2014-05-06 the
  help-option test is red *because the feature did not exist yet*, which is the caveat above.

Fixes that came out of this run, each one a body measurement, no law touched: the src-layout trap; the
failing tests' files travelling by default; the minimal overlay; the age bound as a verdict; the WHY lane
tracing the failing test through pytest (fixtures, parametrization, class tests) against its nearest
passing neighbour when the assertion names no function — on these five it produced a divergence on four;
and the candidate pool widened from the max-Ochiai lines to every `EF_ALL` line, each with its frame,
literal and recency bits measured, because on the first run of `762c97ee` the guilty lines were never
candidates at all. The adversarial battery (`examples/locate/adversarial.py`) held at 6.5/10 through all
of it; its one WEAK case, the 2,000-line file of coverage-identical lines, sits at 218.5 in the presented
order inside a band of 84 lines the law alone cannot tell apart.
