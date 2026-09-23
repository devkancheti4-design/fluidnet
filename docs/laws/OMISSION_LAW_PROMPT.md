# Superoptimizer task — the OMISSION law

The CAUSE law ranks lines the failing test *executed*. It is blind to the commonest real bug: the one where
the fix **adds** code the old file never ran. Find the law that ranks *where the missing code belongs*.

---

## The defect, measured

The first three real click fixes the locator was measured on (2026-09-23, `examples/locate/real_click.json`):

| fix | what the maintainer added | what the failing test executed in that file |
|---|---|---|
| `f58ca3e814` `_utils.py` | `__copy__`, `__deepcopy__`, `__reduce_ex__` on an enum | **no source line** — pickle did the work |
| `bec59289d8` `decorators.py` | a resolution path in `version_option` | nothing past the raise |
| `762c97eef7` `core.py` | a branch for an optional metavar | the other arm of the branch |

Under the CAUSE law all three are misses — correctly. No line has EF_ALL because the line does not exist.
Of the 565 real single-file fixes mined from click, arrow, rich and sortedcontainers, **35 are pure
insertions and 57 turn one line into several**: a sixth of real bugs are faults of omission, and the
ranking has nothing to say about any of them.

What the locator *can* still measure for an omission is not where the bug is but where the path stopped
looking: the last line the failing run executed, the branch it fell past, the lines only passing tests
reach, the function the assertion targeted, the exception it died of. Those are the body's measurements.
The law is what turns them into "examine this line first".

---

## What must not be done

Do not add `if the failure raised, then weight ENDED by 3`. The body measures; the law rules — the same
rule that produced the engine, ranking, SIGHT, placement and CAUSE laws. No number in the body is a
weight. If the ranking is wrong on real fixes, the *table* changes by a stated principle and a new kernel
is asked for.

Do not fold this into the CAUSE law. The two regimes are different questions — "which executed line is
wrong" and "where does missing code belong" — and a line can be a good answer to one and a vetoed answer
to the other. Two laws, run side by side; the body shows both verdicts and never picks by a constant.

---

## The measurement the body will supply

For one candidate line, one byte:

| bit | name | measured how |
|---|---|---|
| 0 | `ENDED` | the failing run's **last executed source line** is this line (from the trace) |
| 1 | `NEXT` | this line was **not** executed and the line just before it **was**: the frontier the path stepped past |
| 2 | `TARGET` | the line is inside the function the failing assertion calls, or the frame that raised |
| 3 | `HEAD` | the line is a site missing code goes: a `def`/`class` line, or a branch or guard head (`if`, `elif`, `else`, `try`, `except`, `return`, `raise`) |
| 4 | `PASSONLY` | executed by at least one **passing** test and by **no** failing test — where the failing run should have gone (the spectrum, reversed) |
| 5 | `RAISED` | the failure was an exception, not a false assertion (`AttributeError`, `KeyError`, `NameError`, `TypeError`, …). Measured once per failure; the same bit on every line — it names the regime |
| 6 | `DIVERGE` | as in the CAUSE law: the first line where the failing run parts from a passing one |
| 7 | `RECENT` | as in the CAUSE law: changed within the last N commits |

**Situation word** `x = bit0 | bit1<<1 | … | bit7<<7`, 256 values.

Reachability: `ENDED` and `NEXT` cannot both be set (a line is executed or it is not). `ENDED` and
`PASSONLY` cannot both be set. Everything else may co-occur. State how many words are reachable and the
law may do anything on the rest, provided it still lands in 0..15.

---

## The law to find

```
omission(x) -> 0..15    higher = examine first    0 = no reach evidence at all
```

**The principle**, in the same form as the CAUSE law so the two are comparable: evidence comes in lanes,
each lane graded strong / weak / silent from its bits, and the priority is the dense lexicographic rank
of (strong count, weak count). One strong beats any number of weak because the rank says so.

| lane | strong | weak |
|---|---|---|
| **EDGE** — where the path stopped | `ENDED` | `NEXT` |
| **SCOPE** — where the code belongs | `TARGET` and `HEAD` | `TARGET` or `HEAD` |
| **CONTRAST** — what the passing run did instead | `DIVERGE` | `PASSONLY` |
| **TIME** | — | `RECENT` |

`RAISED` is not a lane. It is the regime bit: it decides whether this law speaks with full force or
quietly. Propose the rule and justify it; the anchors below constrain it. A sensible candidate: with
`RAISED` = 1 the rank is as above; with `RAISED` = 0 the priority is halved (floor), because a false
assertion with no exception is usually a *wrong* line (the CAUSE law's regime), not a missing one.

**R0, the veto:** a line with no EDGE bit, no CONTRAST bit and not `TARGET` is 0. It has no reach evidence;
ranking it would be a guess.

**R1** dense lexicographic rank of (strong, weak) among non-vetoed words.
**R2** monotone in every evidence bit (adding evidence never lowers the rank), `RAISED` excepted.
**R3** only the counts matter: no lane is privileged.

---

## Anchors — real cases, held out from the design

| word | case | want |
|---|---|---|
| `ENDED` + `TARGET` + `HEAD` + `RAISED` | click `bec59289d8`: the `def version_option` line, the run raised inside it | the top rank reachable with 2 strong (EDGE, SCOPE) |
| `TARGET` + `HEAD` + `RAISED`, nothing executed | click `f58ca3e814`: the `class Sentinel(enum.Enum)` line; the test executed **no** source line, so EDGE is silent | ranked, above every vetoed line, below the row above |
| `NEXT` + `HEAD` + `PASSONLY` | rich `720800e6`: the `if tab_size is None:` guard belongs on the line after the assignment the failing run stepped past | ranked with 1 weak EDGE, 1 weak SCOPE, 1 weak CONTRAST |
| `RECENT` only | a line changed last week that nothing else points at | **0** — recency alone is not reach |
| `ENDED` alone, `RAISED` = 0 | a false assertion whose run simply ended at `return` | ranked, but at the halved priority |

---

## How it will be judged

1. **Exhaustively against the table**, every reachable word, plus R0–R3 by enumeration on the kernel.
2. **On real omissions, held out.** The harness `examples/locate/real_bugs.py` logs every candidate line's
   bits on every run. Ground truth for an insertion is its two neighbours on the old side of the hunk.
   The set: the 35 pure insertions and 57 one-to-several fixes among the 565, split in half; the table is
   designed on one half and judged on the other. Report the rank of the best truth line under this law,
   under the CAUSE law, and under the old count-based file ranking, on the same cases.
3. **It must not hurt the other regime.** On fixes that replace an executed line, the CAUSE law's verdict
   stands; this law's verdicts are shown beside it, never blended. Measure that showing both does not
   push the CAUSE law's top-1 down.
4. `fluidfix selfcheck` and `tests/test_cause_law.py` must still pass unchanged.

---

## Why a law rather than a patch

Every omission has the same four questions — where did the path stop, where should code go, what did a
passing run do instead, was it an exception — and today the body answers none of them, so a sixth of
real bugs are simply out of reach. One law over those four lanes serves every omission, and every lane
it reads is already measured or one trace away.
