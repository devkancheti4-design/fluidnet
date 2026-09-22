#!/usr/bin/env python3
"""The recursive test: patches MODELS wrote, judged by the gate.

usage: replay_gate.py <fluidfix-repo>     (needs its research/model-bugs-2026-09-18 and research/certify-2026-09-18)

Every broken program was written by a small model from prose alone; every `true` patch is a correct
implementation of the same specification by a DIFFERENT model — a whole-function rewrite no line vocabulary
could author. The adversarial classes are generated mechanically from the correct one:
    wrong        another model's failing attempt              → must BLOCK
    flaky        correct, raises on half its calls            → must BLOCK
    collateral   fixes the red test, breaks a green one       → must BLOCK
    true         correct                                      → ALLOW
    outside-*    correct on everything the suite can see      → ALLOW (the suite cannot tell — and says so)
    overfit      a lookup table on the suite's exact inputs   → ALLOW — the documented hole of any suite gate
fluidnet contributes nothing but the judgment. Nothing here is hand-tuned per case."""
import json, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path
F = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(F / "src")); sys.path.insert(0, str(F / "research/certify-2026-09-18"))
import run as R, patches as P, certify as C                      # noqa: E402
from fluidnet.gate import gate                                    # noqa: E402

cases = R.load()
work = Path(tempfile.mkdtemp(prefix="fn-gate-"))
tally = defaultdict(Counter); n = 0
print(f"{'spec':18} {'author':16} {'class':13} {'verdict':7}  runs  reason")
print("-" * 100)
for i, c in enumerate(cases):
    root = work / f"case{i}"
    C.build_repo(root, c["broken"], c["asserts"])
    from fluidfix.oracle import Oracle
    try:
        green, red = C.failing_ids(Oracle(str(root), python=sys.executable))
    except Exception as e:
        print(f"{c['spec'][:18]:18} {c['author'][:16]:16} {'(harness)':13} skipped  {str(e)[:40]}"); continue
    red_idx = {int(t.split("_")[1]) for t in red if t.startswith("test_")}
    supplied = P.make(root, c["broken"], c["correct"], c["asserts"], red_idx, c["other_broken"])
    for cls in ("true", "wrong", "flaky", "collateral", "overfit", "outside-near", "outside-far"):
        if cls not in supplied:
            continue
        g = gate(root, C.MODULE, supplied[cls])
        tally[cls][g["verdict"]] += 1; n += 1
        print(f"{c['spec'][:18]:18} {c['author'][:16]:16} {cls:13} {g['verdict']:7}  {g['suite_runs']:>4}  {g['reason'][:44]}")
print("-" * 100)
print(f"{n} patches judged\n")
print(f"{'class':13} {'ALLOW':>6} {'WARN':>5} {'BLOCK':>6}   expected")
EXPECT = {"true": "ALLOW", "wrong": "BLOCK", "flaky": "BLOCK", "collateral": "BLOCK",
          "overfit": "ALLOW (the hole)", "outside-near": "ALLOW", "outside-far": "ALLOW"}
for cls in EXPECT:
    t = tally[cls]; print(f"{cls:13} {t['ALLOW']:>6} {t['WARN']:>5} {t['BLOCK']:>6}   {EXPECT[cls]}")
json.dump({k: dict(v) for k, v in tally.items()}, open(Path(__file__).with_name("replay_gate.json"), "w"), indent=1)
