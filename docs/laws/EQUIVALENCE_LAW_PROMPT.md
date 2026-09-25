# Superoptimizer task — the EQUIVALENCE law

Two different fixes both pass the whole test suite, an oracle has answered, and the body is deciding what to do
with the answer with `if`s. Find the law.

---

## The defect

`fluidnet watch` (neo/fluidnet, 2026-09-25) refuses to ship a fix unless it is the only passing program at its
lines. When a second net writes a *different* program that also passes, the pair is AMBIGUOUS, and the core asks
an AI agent — used only as an **oracle** — for one fact. The oracle answers in one of two ways: a pytest test that
states the intended behaviour, or `NO-DIFFERENCE` with a probe it claims shows the two behave the same. The body
then decides by hand:

```python
if code:                                   # the oracle gave a test
    res = resolve(root, rel, pair, test)   # runs the test under each candidate
    if res.ok: ship(pair[res.winner])
elif no_difference(reply):
    refuse("the core has no equivalence lane yet")
```

Measured live on click the same day: at `core.py:1877` the oracle's test passed `and` and failed
`self.context_settings`, and the core shipped `and` — right. At `_termui_impl.py:579` the oracle answered, correctly,
that `os.environ.get("LESS", "")` and `os.environ.get("LESS")` followed by `if less_env is None: less_env = ""` are
the same, and the body refused, because nothing in it can weigh an equivalence claim. Every branch above is a guess:
what if the oracle's test passes both? fails both? flips on a re-run? what if the probe never reaches the lines
that differ?

The rule of this repository: **the law decides and the body only measures.** The oracle supplies data; it never
chooses. The body measures eight facts about the pair and the oracle's answer into an integer. The law turns that
integer into a verdict.

## What must not be done

Do not trust the oracle's words. `NO-DIFFERENCE` alone ships nothing; a test ships only what it was *measured* to
separate. Do not add `if probe_ok and oracle_confident: ship`. The table below follows from stated principles; the
kernel must reproduce it exactly.

---

## The measurement the body will supply

For one ambiguous pair — candidate **A** and candidate **B**, both certified on the full suite — eight bits. Every
one is measured mechanically; none is a judgement.

| bit | name | set when |
|---|---|---|
| 0 | `SAME_AST` | A and B parse to the same syntax tree (`ast.dump` equal) — the same program written differently |
| 1–2 | `KIND` | the oracle's usable answer: `0` none (no reply, unparseable, or its test touched a tracked file), `1` a test, `2` NO-DIFFERENCE with a probe |
| 3 | `E1` | `KIND=1`: the test passes under A. `KIND=2`: the probe ran under both A and B and executed **every** line where they differ (coverage) |
| 4 | `E2` | `KIND=1`: the test passes under B. `KIND=2`: the probe's observable output (stdout, and the exception type if one escapes) is **byte-identical** under A and B |
| 5 | `SMALLER_A` | A's edit changes no more characters than B's (ties to A) |
| 6 | `LAST_ASK` | the oracle has been asked the maximum number of times; the ask budget is spent |
| 7 | `STABLE` | re-running the oracle's test (or probe) under each candidate gave the same result as the first run |

**Situation word:** `x = SAME_AST | KIND<<1 | E1<<3 | E2<<4 | SMALLER_A<<5 | LAST_ASK<<6 | STABLE<<7`

**Unreachable, so the law may return anything for them:**
- `KIND = 3` (not a value the body produces).
- `SAME_AST = 1` with any of `KIND, E1, E2, LAST_ASK, STABLE` set — identical programs are shipped without asking.
- `KIND = 0` with any of `E1, E2, STABLE` set — with no answer, nothing ran.

That leaves **70 reachable values of 256.**

---

## The law to find

```
equiv(x) -> verdict 0..3
   0  REFUSE   ship nothing; the pair stays ambiguous
   1  SHIP_A
   2  SHIP_B
   3  ASK      ask the oracle again (a deciding test, or a probe that covers the lines)
```

### The principles that fix the table

- **Q0 — one program.** `SAME_AST = 1`: ship the smaller edit — A if `SMALLER_A`, else B. Nothing else is consulted.
- **Q1 — no answer is no evidence.** `KIND = 0`: ASK, or REFUSE when `LAST_ASK`.
- **Q2 — a test decides only what it was seen to separate.** `KIND = 1`:
  - not `STABLE`: the verdict flipped on a re-run — no evidence: ASK, or REFUSE when `LAST_ASK`;
  - `STABLE` and exactly one of `E1, E2`: ship the candidate it passes — whatever `LAST_ASK` and `SMALLER_A` say;
  - `STABLE` and both pass: it separates nothing: ASK, or REFUSE when `LAST_ASK`;
  - `STABLE` and both fail: the oracle's own statement of the behaviour is met by neither candidate — **REFUSE**,
    and do not ask again: no answer can make either candidate right.
- **Q3 — an equivalence claim ships only on measured evidence.** `KIND = 2`: ship the smaller edit (as in Q0) only
  when `STABLE`, `E1` (the probe reached every differing line) and `E2` (the outputs were identical) all hold.
  Anything less — the probe missed a differing line, its outputs differ (the claim is refuted by its own probe), or
  it flipped on a re-run — is not evidence: ASK, or REFUSE when `LAST_ASK`.
- **Q4 — the budget is respected.** `LAST_ASK = 1` never yields ASK.
- **Q5 — claims never ship.** Every SHIP is backed by `SAME_AST`, a stable separating test, or a stable, covering,
  identical probe. No verdict depends on what the oracle *said* beyond which kind of evidence it handed over.

### Truth table — all 256 values

Row `r`, column `c` is `x = 16r + c`. `.` is unreachable — the law may return anything there.

```
x=  0..15   3 2 3 . 3 . . . . . 3 . 3 . . .
x= 16..31   . . 3 . 3 . . . . . 3 . 3 . . .
x= 32..47   3 1 3 . 3 . . . . . 3 . 3 . . .
x= 48..63   . . 3 . 3 . . . . . 3 . 3 . . .
x= 64..79   0 . 0 . 0 . . . . . 0 . 0 . . .
x= 80..95   . . 0 . 0 . . . . . 0 . 0 . . .
x= 96..111  0 . 0 . 0 . . . . . 0 . 0 . . .
x=112..127  . . 0 . 0 . . . . . 0 . 0 . . .
x=128..143  . . 0 . 3 . . . . . 1 . 3 . . .
x=144..159  . . 2 . 3 . . . . . 3 . 2 . . .
x=160..175  . . 0 . 3 . . . . . 1 . 3 . . .
x=176..191  . . 2 . 3 . . . . . 3 . 1 . . .
x=192..207  . . 0 . 0 . . . . . 1 . 0 . . .
x=208..223  . . 2 . 0 . . . . . 0 . 2 . . .
x=224..239  . . 0 . 0 . . . . . 1 . 0 . . .
x=240..255  . . 2 . 0 . . . . . 0 . 1 . . .
```

(Reachable verdicts: REFUSE 30, ASK 26, SHIP_A 7, SHIP_B 7.)

Anchors, so the table can be read against reality:

| case | x | equiv |
|---|---|---|
| a twin: `kwargs.get('cls')` vs `kwargs.get("cls")`, A's edit smaller | 33 | **1** SHIP_A |
| click `core.py:1877` live: the oracle's test passes `and` (A) only, stable | 138 | **1** SHIP_A |
| click `_textwrap.py:168`: the test passes `+=` (B) only, stable | 178 | **2** SHIP_B |
| click `_termui_impl.py:579`: probe covers the differing lines, outputs identical, stable; `.get("LESS", "")` (A) is the smaller edit | 188 | **1** SHIP_A |
| a probe that never reached the differing lines | 148 | 3 ASK |
| a stable test that both candidates fail | 130 | 0 REFUSE |
| no usable answer, ask budget spent | 64 | 0 REFUSE |

---

## Constraints

- **Branchless integer arithmetic over `x`.** No conditionals, no lookup table, the same character as the existing
  laws — e.g. the engine's `act = (4 & ntzb(x-7)) + ntzb(x + (x&128))`, SIGHT's lanes of shifts and masks.
- Shifts, masks, adds, subtracts, popcount if you have it, and `ntzb` are available. Fewer operations is better.
- **Total** on 0..255 and **exact** on all 70 reachable values. Return the verdict, or a value whose low 2 bits are it.

## How it will be judged

1. **Exhaustively against the table**, all 70 reachable `x`.
2. **Q0–Q5 re-checked by enumeration** on the kernel itself, not only on the table: in particular Q4 (no ASK when
   `LAST_ASK`) and Q5 (no SHIP without its evidence) over every reachable `x`.
3. `fluidfix selfcheck` must still re-derive every existing law unchanged.

**What the superoptimizer does not decide:** whether a probe that covers the differing lines and prints identical
output is enough evidence of equivalence in practice. That is measured separately — on known-equivalent pairs (the
twins and the `_termui_impl.py:579` pair) and known-different pairs (every AMBIGUOUS pair a deciding test has
separated, run through the probe path as if the oracle had claimed NO-DIFFERENCE): the probe must ship none of the
different pairs. If it ships one, the measurement of `E1`/`E2` gets stricter — never the table. The kernel's job is to
make the ruling exact, branchless and verifiable; the real pairs' job is to say whether the ruling is right.
