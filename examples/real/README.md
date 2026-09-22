# Real sub-20-line shapes, taught once, tested twice

Three fault classes for the shapes that dominate real sub-20-line fixes, each from one worked example, each
with a property. Measured 2026-09-22 on 565 real single-file fix commits from click, arrow, rich and
python-sortedcontainers: **92% change 20 lines or fewer**; among the multi-line ones the largest mechanical
shapes are a value guarded before use (15 real instances) and a missing import added (9).

| class | worked example | generated, unseen | real history, the class's own lines | real history, the whole fix |
|---|---|---|---|---|
| `none-flows-on-unguarded` | rich `b7ddacf4` | **12/12** | 3/15 | 0/15 |
| `module-used-never-imported` | click `19655099` | **12/12** | 1/9 | 0/9 |
| `mutating-call-missing-its-return` | model-bug corpus | **8/8** | — (0 real instances) | — |

`generalise.py` runs the generated instances through the same candidates, property gate and judge the CLI
uses. `real_history.py <clones>` runs the 24 held-out real commits (`held_out.json`) against their
parent-commit files — the knowledge question: could it have proposed the maintainer's lines.

## Read the two real-history columns together

**The whole-fix column is 0 and that is the honest number.** Real fixes bundle the mechanical part with
something else: a docstring line, a second change, a default the maintainer knew (`tab_size = 8`) that no
file vouches for. The class does its part — the guard, the import — and the rest was never its job.

**The own-lines column is where it actually reaches:** `if self.keywords is None: self.keywords =
self.KEYWORDS` because the file defines `KEYWORDS`; `import time` because `time.` is used and nothing
imports it. It does not reach `tab_size = 8` because `8` lives in the maintainer's head, and it does not
reach `import builtins` because the usage and the import were added together — before the fix, there was
nothing to see.

That is what "it fixes what it was taught" means on real code: the mechanical fraction of a fix, when the
file contains the evidence for it. Everything else is yours.

## Two applier mistakes found by these tests, both fixed

- A `self.x` assignment whose default is a class attribute was proposed unqualified (`LIMIT`, a NameError)
  instead of `self.LIMIT`. 9/12 → 12/12 generated.
- The signal required a call on the right-hand side, so `self.keywords = keywords` — the commonest source
  of a stray None, a parameter passed through — never anchored. Real own-lines reach went 0 → 3.
