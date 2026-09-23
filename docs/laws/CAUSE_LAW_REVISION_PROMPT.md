# Superoptimizer task — the CAUSE law, revision 1

The CAUSE law was judged on real fixes, held out, as its header says it must be. It says the table is
wrong in one cell, by one principle. This asks for the kernel of the revised table.

---

## What the held-out real bugs said

`examples/locate/real_bugs.py` on click, 26 real fixes judged (2026-09-23, `real_click.json` before the
omission regime existed). In 8 the guilty line was among the law's candidates at all — the other 18 are
faults of omission or vetoed, the OMISSION law's business. In those 8:

- **every guilty line has the same word: `EF_ALL` alone, rank 2.** Real bugs on real click fixes carry no
  traceback frame (they fail an assertion), no assertion literal, no recency (old code), and are also run
  by passing tests (`ep > 0`, shared code). One weak SPECTRUM lane is all the evidence there is.
- what outranked them, **36 of the 46 times a line ranked above a guilty one**, was one shape:
  `IMPORT + LITERAL`, rank 3 — an import-time line that happens to contain a name the assertion mentions,
  `from .core import Command` when the assertion says `Command`. Six more times: `IMPORT + RECENT`.

`IMPORT` exists to keep a line the spectrum cannot see from being vetoed. The table *also* lets it count
as a weak SPECTRUM grade (`SPEC_W = EF_ALL | IMPORT`), so an **unmeasured** lane behaves like weak
**evidence**, and with any other weak bit it beats the real line's one weak lane.

---

## The principle

**An unmeasured lane is silent, not weak.** `IMPORT` says the spectrum could not look; it says nothing
about guilt. It exempts the line from R0 and contributes no grade.

---

## The revised table — one change

| | before | after |
|---|---|---|
| SPECTRUM weak | `EF_ALL or IMPORT` | **`EF_ALL`** |
| SPECTRUM strong | `EF_ALL and EP_NONE` | unchanged |
| R0 exemption (KEEP) | `EF_ALL or IMPORT` | unchanged — `IMPORT` still keeps the line alive |
| TIME, WHY, SYMPTOM lanes | | unchanged |
| priority | `1 + BASE[s] + w`, `BASE = 0, 5, 9, 12, 14` | unchanged |

So R0 and SPEC_W are no longer the same lane negated; the kernel needs KEEP as its own expression
(`EF_ALL | IMPORT`) — the cut the first pass avoided, now required by measurement.

Consequence: an `IMPORT`-only line is rank 1 (kept, nothing counted); `IMPORT + LITERAL` is rank 2 (one weak
SYMPTOM), the same rank as a bare `EF_ALL` line — and Ochiai breaks the tie, which an import line loses
because its score is 0. **16 of the 144 reachable words change rank; every other cell stands.**

---

## Judged before asking — replayed on the logged bits, held out

| click case | current rank of the guilty line | revised |
|---|---|---|
| `0551bf5358` | 11.5 | **4.5** |
| `ac6a2acfdb` | 29.5 | **3.5** |
| `e003331551` | 11.5 | **2.5** |
| the other five | 1, 1, 3.5, 6.5, 6.5 | unchanged |

**3 better, 0 worse, 5 unchanged.** Top-1 unchanged at 2 of 26; the gain is in the top-5 band, where a
human reads. The revised rule lands in 0..15 on all 256 words.

---

## Rules, as before

- **R0** no `EF_ALL` and no `IMPORT` → 0.
- **R1** dense lexicographic rank of (strong, weak).
- **R2** monotone in every evidence bit except `IMPORT` — and now `IMPORT` adds nothing, so adding it
  never lowers a rank either; state that it holds.
- **R3** only the counts matter.

## Anchors — the four stand, one is added

| word | | want |
|---|---|---|
| `x=11` EF_ALL+EP_NONE+BISECT | rich segment.py | 10 |
| `x=12` IMPORT+BISECT | module constant the bad commit changed | **6** (one strong, nothing weak) |
| `x=1` EF_ALL | a shared helper every test runs | 2 |
| `x=34` FRAME+EP_NONE, not EF_ALL | frame on a line only one failing test runs | 0 |
| **`x=68` IMPORT+LITERAL** | `from .core import Command` under an assertion naming Command | **2**, not 3 |

Note `x=12` moves from 7 to 6: IMPORT no longer adds a weak lane to BISECT's strong one. That is the
principle applied consistently, and it is checked by the same rule as the rest.

## How it will be judged

As before: exhaustively against the table on the reachable words, R0–R3 by enumeration on the kernel,
the anchors — and then on the **rich** real fixes, which were never used here, with the harness's logged
bits; and on click again after the omission regime is measured beside it. If rich disagrees, the table
changes by a stated principle and this file gets a revision 2.
