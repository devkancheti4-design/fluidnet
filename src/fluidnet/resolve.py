# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resolve — when the suite cannot choose, a new test chooses, and fluidnet checks the test.

Two different fixes that both pass the whole suite are AMBIGUOUS: fluidnet refuses to pick, because picking
would be a guess. Measured 2026-09-25 on click: at _textwrap.py:168 `pass` and `+=` both pass all 2,240 tests;
at core.py:1877 `and` and a sibling-attribute rewrite both do. An AI agent reading the code chose right both
times — but nothing checked it. So the judgement is asked for in the one form fluidnet can verify: a TEST.

Whoever decides — a person, an agent — writes one new test file. fluidnet then checks, with no model:

    NEW-ONLY     the test is a new file under tests/; no tracked file (source or test) is touched
    SEPARATES    with each candidate applied in turn, the new test passes with exactly ONE of them
    CERTIFIED    that candidate is certified on the full suite, the new test included
    ROLLBACK     the tree is byte-identical afterwards (sha256); nothing is applied unless you apply it

The decider's judgement enters as a test anyone can read and keep, never as an answer to be trusted."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resolution:
    verdict: str = ""               # RESOLVED | UNDECIDED | NOT-NEW | TOUCHED | FAILS | NO-TEST
    why: str = ""
    winner: int | None = None       # index into the candidates
    passes: list = field(default_factory=list)
    suite_runs: int = 0
    seconds: float = 0.0
    rolled_back_exact: bool = True

    @property
    def ok(self) -> bool:
        return self.verdict == "RESOLVED"


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)


# ------------------------------------------------------------------ what is MEASURED of an oracle's answer
# The EQUIV law (equiv.py) rules on these, never on what the oracle said.

def measure_test(root, rel: str, candidates: list[str], test_rel: str, python: str | None = None) -> dict:
    """The oracle's test under each candidate, twice: {pass: [A, B], stable: both runs agreed for both}."""
    root = Path(root); f = root / rel; original = f.read_text(encoding="utf-8"); py = python or sys.executable
    runs = []
    try:
        for cand in candidates:
            f.write_text(cand if cand.endswith("\n") else cand + "\n", encoding="utf-8")
            got = [subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "--no-header", test_rel],
                                  cwd=root, capture_output=True, text=True).returncode == 0 for _ in range(2)]
            runs.append(got)
    finally:
        f.write_text(original, encoding="utf-8")
    return {"pass": [r[0] for r in runs], "stable": all(r[0] == r[1] for r in runs), "runs": 2 * len(runs)}


def _differing_lines(a: str, b: str) -> tuple[set, set]:
    """Lines of A and of B inside the blocks where they differ. A pure insertion on one side counts the line it
    follows on the other side, so a probe must pass through that point in both."""
    import difflib
    la, lb, da, db = a.splitlines(), b.splitlines(), set(), set()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=la, b=lb, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        da.update(range(i1 + 1, i2 + 1) if i2 > i1 else [max(1, i1)])
        db.update(range(j1 + 1, j2 + 1) if j2 > j1 else [max(1, j1)])
    return da, db


def measure_probe(root, rel: str, candidates: list[str], probe: str, python: str | None = None,
                  timeout: int = 120) -> dict:
    """The oracle's probe under each candidate, twice, under coverage. covers: under each candidate the probe
    executed every executable line where the two differ. equal: stdout and any escaping exception's type were
    byte-identical under both. stable: each candidate's two runs agreed."""
    import json as _json
    import os
    import tempfile
    root = Path(root); f = root / rel; original = f.read_text(encoding="utf-8"); py = python or sys.executable
    diff = _differing_lines(*candidates[:2])
    outs, covered, detail = [], [], []
    # the probe imports the package the way the suite does: the project root and its src/ on the path
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(p) for p in (root / "src", root) if p.is_dir()]
                                        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    with tempfile.TemporaryDirectory() as td:
        pf = Path(td) / "probe.py"; pf.write_text(probe, encoding="utf-8")
        try:
            for n, cand in enumerate(candidates[:2]):
                f.write_text(cand if cand.endswith("\n") else cand + "\n", encoding="utf-8")
                seen, ex = [], None
                for k in range(2):
                    data = Path(td) / f"cov{n}{k}"
                    p = subprocess.run([py, "-m", "coverage", "run", f"--data-file={data}", f"--source={root}", str(pf)],
                                       cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
                    exc = (re.findall(r"^(\w+(?:Error|Exception|Exit)):", p.stderr, re.M) or [""])[-1]
                    seen.append((p.stdout, exc))
                    if k == 0:
                        rep = Path(td) / f"cov{n}.json"
                        subprocess.run([py, "-m", "coverage", "json", f"--data-file={data}", "-o", str(rep)],
                                       cwd=root, capture_output=True, text=True, env=env)
                        ex = set()
                        try:
                            for name, d in _json.loads(rep.read_text()).get("files", {}).items():
                                if os.path.normpath(os.path.join(str(root), name)).endswith(os.path.normpath(rel)):
                                    ex = (set(d.get("executed_lines", [])), set(d.get("missing_lines", [])))
                        except (OSError, ValueError):
                            ex = set()
                outs.append(seen); covered.append(ex)
        finally:
            f.write_text(original, encoding="utf-8")
    covers = True
    for n, (want, got) in enumerate(zip(diff, covered)):
        if not got:
            covers = False; detail.append(f"{'AB'[n]}: no coverage of {rel}"); continue
        executed, missing = got
        need = {l for l in want if l in executed or l in missing}           # executable lines only
        miss = sorted(need - executed)
        if miss:
            covers = False; detail.append(f"{'AB'[n]}: lines {', '.join(map(str, miss))} never ran")
    equal = len(outs) == 2 and outs[0][0] == outs[1][0]
    stable = all(r[0] == r[1] for r in outs)
    if not equal and len(outs) == 2:
        detail.append(f"output differs — A: {outs[0][0][0][:120]!r} {outs[0][0][1]} · B: {outs[1][0][0][:120]!r} {outs[1][0][1]}")
    return {"covers": covers, "equal": equal, "stable": stable, "detail": "; ".join(detail), "runs": 4}


def resolve(root, rel: str, candidates: list[str], test_rel: str, python: str | None = None) -> Resolution:
    """Which of `candidates` (full texts of `rel`) does the new test at `test_rel` choose — and is it certified?"""
    import hashlib
    from .certify import certify
    root = Path(root); t0 = time.time(); r = Resolution()
    f = root / rel
    original = f.read_text(encoding="utf-8")
    before = hashlib.sha256(f.read_bytes()).hexdigest()

    def finish(verdict, why):
        f.write_text(original, encoding="utf-8")
        r.verdict, r.why = verdict, why
        r.rolled_back_exact = hashlib.sha256(f.read_bytes()).hexdigest() == before
        r.seconds = round(time.time() - t0, 1)
        return r

    t = root / test_rel
    if not t.is_file():
        return finish("NO-TEST", f"{test_rel} does not exist")
    if _git(root, "ls-files", "--error-unmatch", "--", test_rel).returncode == 0:
        return finish("NOT-NEW", f"{test_rel} is a tracked file; the deciding test must be new")
    if "tests" not in Path(test_rel).parts and not Path(test_rel).name.startswith("test_"):
        return finish("NOT-NEW", f"{test_rel} is not a test file")
    touched = [l for l in _git(root, "diff", "--name-only").stdout.split() if l]
    if touched:
        return finish("TOUCHED", f"tracked files changed besides the new test: {', '.join(touched)}")
    py = python or sys.executable
    for cand in candidates:
        f.write_text(cand if cand.endswith("\n") else cand + "\n", encoding="utf-8")
        p = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "--no-header", test_rel],
                           cwd=root, capture_output=True, text=True)
        r.suite_runs += 1
        r.passes.append(p.returncode == 0)
        f.write_text(original, encoding="utf-8")
    if sum(r.passes) != 1:
        return finish("UNDECIDED", f"the new test passes with {sum(r.passes)} of {len(candidates)} candidates; "
                                   f"a deciding test passes with exactly one")
    r.winner = r.passes.index(True)
    c = certify(root, rel, candidates[r.winner], python=py)
    r.suite_runs += c.suite_runs
    if not c.ok:
        return finish("FAILS", f"the chosen candidate is not certified with the new test in the suite: "
                               f"{c.verdict}: {c.why}")
    return finish("RESOLVED", f"candidate {r.winner + 1} of {len(candidates)}: the new test passes with it alone, "
                              f"and it is certified on the full suite with that test included")
