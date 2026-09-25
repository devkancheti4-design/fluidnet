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
