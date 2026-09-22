# fluidnet

**You teach it a bug once, and it repairs every future one — with a proof, not a guess.**

fluidnet is not a model. There is no network, no weights, no prompt, no tokens. It is many small
**nets**, each a [fluidfix](https://github.com/devkancheti4-design/fluidfix) guard — six integer laws
that decide, the target's own test suite that judges, a class property that proves — plus what sits
around them: an **overseer** that routes a failing suite to the net whose taught shapes match,
**descent** for more than one fault at a time, and **certification** of a fix nobody here wrote.
fluidfix is one part; this repository is the whole.

It repairs the faults you taught it, proves each fix correct over every input in range, certifies fixes
it didn't write — and never attempts open-ended bugs, by design.

**[Watch it run — 3:52, live, nothing generated](docs/media/fluidnet.mp4)** · [how it works, in full](docs/FLUIDNET.md)

---

## The recursive model

A net never needs to *solve* a bug to *judge* a fix. So the same gates that certify a net's own repair —
red before, green after on the full suite, stable on re-check, nothing else broken, byte-exact rollback —
certify anyone's: a colleague's, a model's, another net's. That is what lets nets check nets, and it is
why the system can be many small cheap parts under one overseer instead of one large trusted one.

```
you teach, once per shape ─────────────┐
                                       v
a failing test ──> overseer routes ──> net 1 · net 2 · net 3 …   (7 taught classes each, one process each)
                                       │
                          inside a net │ localise → six laws → applier → PROPERTY GATE → your suite → certificate
                                       │           refuses for free ─┘        the only acceptor ─┘
a patch you didn't write ──────────────┴──> the same suite gates ──> certified, or refused and rolled back
```

Why many nets: a guard's dictionary is 16 slots, 7 of them yours — a hard ceiling, but *per process*.
N nets carry 7N taught classes; the overseer only routes.

## Setup

```bash
git clone https://github.com/devkancheti4-design/fluidnet
cd fluidnet
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # pulls fluidfix from its git master — PyPI's 0.15.0 predates the property gate
fluidnet doctor           # is this install able to prove, not just guess?
fluidfix selfcheck        # re-derives the six laws on your machine, exhaustively
```

## Test

```bash
pytest -q
```

Twelve tests, each a real run against a real pytest project built in a temp directory — nothing mocked:

| test | what it proves |
|---|---|
| `test_certify` | a correct patch is CERTIFIED with the file restored byte-exact; a patch that fixes the red test but breaks another is refused as COLLATERAL; green code is NOT-RED |
| `test_descend` | three faults from three classes fall in three steps, failing 3 → 2 → 1 → 0; two faults on *one line* are refused at depth 1 and repaired at depth 2; a stalled descent returns the original untouched |
| `test_overseer` | a net's signals are read without touching the live registry; the net that recognises more of the repository is tried first; the first net whose real `fluidfix guard` process repairs wins, dry-run restores byte-exact |
| `test_cli` | `doctor` passes, `teach` prints a class *and* a property |

## How an engineer uses it

**Every time you fix the same shape of bug twice, teach it once — from then on it owns that shape and
hands you a proof with every fix, while you keep the open-ended work.**

1. **Let it watch.** Run `fluidnet watch . --net rules.py` on a red suite (dry-run by default). It repairs
   what it knows, refuses what it doesn't, and touches nothing on refusal.
2. **Teach.** `fluidnet teach` prints the template: a class is a *signal*, a *rewrite*, and a *property* —
   what every rewrite must keep true, checked over a bounded domain before any test runs. Written once,
   beside your code, in a dictionary file. Give a property a control that fails it; a check nothing can
   fail proves nothing, and the gate reports zero-input checks as UNPROVEN, never PROVEN.
3. **Hand over the repeating half.** `fluidnet watch . --net a.py --net b.py --commit`. Each net is its own
   `fluidfix` process. Every fix comes with a certificate or a refusal report naming what killed each
   candidate — including the ones the property refused *before* the suite ran.
4. **Keep the open-ended half.** It never attempts it. When you solve something with a shape, teach it.
   And when a model or a colleague hands you a fix: `fluidnet certify . --file pkg/x.py --patch fixed.py`.

```
fluidnet watch <root> --net a.py [--net b.py …] [--commit]   route once; one fluidfix process per net
fluidnet certify <root> --file <rel> --patch <file>           judge a fix nobody here wrote
fluidnet descend <file> --test 'assert …' [--depth 2]         more than one bug in one file
fluidnet teach                                                the template for a class and its property
fluidnet doctor                                               gate present? pytest-cov? fluidfix on PATH?
```

## The demo

`docs/demo/` rebuilds the repository in the video and runs every scene live: `zsh docs/demo/setup.sh
/tmp/ledgerly && zsh docs/demo/live.sh /tmp/ledgerly`. The turn of it: a suite that only ever asks
`k = 1` accepts `int(k * len(text) - 1)`; a nine-line property refuses it before any suite run; the
placement law's `int(k * (len(text) - 1))` is proven and ships.

## What is measured

| | |
|---|---|
| repairs within a taught shape | 84/84 exact across seven syntactic positions never taught; 0/12 wrong accepts on a negative control |
| generalisation | 240/240 and 30/30 per class on unseen instances; a class taught from `click` ran unchanged on `rich` and `sortedcontainers` |
| class properties | 5/5 controls refuted; the `rich` incident caught with no suite, at zero suite runs |
| certification | 14/14 model-written fixes certified, 29/29 adversarial refused, 307 suite runs, byte-exact rollback every time |
| multi-fault descent | 3 faults, 3 classes never taught together, 11 suite runs |
| real history, knowledge only | the current vocabulary reaches 10 of 565 real fixes — 75% of single-token mechanical fixes, ~2% of everything, because most real one-line fixes are data and docstrings |

## Honest boundaries

- Proofs are over a **bounded** domain, stated in the certificate, not over all inputs.
- A class property lives in a dictionary file; load a dictionary without it and the gate **fails open** —
  `fluidnet doctor` checks the gate exists, and `fluidfix.props.classes_without_properties()` names the
  classes it cannot speak for.
- Generic knowledge covers very little of someone else's history. What it covers is *your* repeating work,
  and the way to know that number is to replay your own history against your vocabulary.
- Open-ended bugs have no path through the system. That is the design.

AGPL-3.0-or-later.
