# SPDX-License-Identifier: AGPL-3.0-or-later
"""Certify a fix nobody here wrote — the recursive part.

A net never needs to solve a bug to judge a fix, so the same gates that check its own repairs check
anyone's: a model's, a colleague's, another net's. Measured 2026-09-18: 14/14 model-written fixes
certified, 29/29 adversarial ones refused, byte-exact rollback every time.

    RED-BEFORE     the suite rejects the code as given          nothing to certify otherwise
    GREEN-AFTER    the suite accepts the patched code           the FULL suite, never a subset
    STABLE         the green repeats on N re-runs               the engine law's HIDDEN lane
    NO-COLLATERAL  every test green before is green after       the full suite IS the gate
    ROLLBACK       the tree is byte-identical afterwards        sha256 before and after

Every refusal restores the file byte-for-byte. Certification never leaves the patch applied — apply it
yourself once you have the certificate."""
from __future__ import annotations

import hashlib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from fluidfix.oracle import Oracle
try:
    from fluidfix.oracle import HarnessError, _check_harness
except ImportError:                                    # older fluidfix: no harness diagnosis
    class HarnessError(Exception): ...
    def _check_harness(*a, **k): ...


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def failing_ids(o: Oracle) -> tuple[bool, set[str]]:
    """(suite green?, the test ids that FAILED). The full suite, no fast path."""
    o.clear_pyc()
    rc, out = o.run(["--tb=no"])
    _check_harness(rc, o.extra_args, out, o.root, o.python)
    ids = set()
    for l in out.splitlines():
        if l.startswith(("FAILED ", "ERROR ")):
            # a test id can hold spaces inside its parameter brackets (`test_x[no-wrap mark-sentence < max]`);
            # splitting on whitespace cut it at the first one and merged distinct parameters into one id.
            # pytest separates the id from its message with " - ".
            nodeid = l.split(" ", 1)[1].split(" - ", 1)[0].strip()
            if nodeid:
                ids.add(nodeid.split("::", 1)[-1])
    return rc == 0, ids


@dataclass
class Certificate:
    verdict: str = ""            # CERTIFIED | NOT-RED | FAILS | COLLATERAL | FLAKY | HARNESS
    why: str = ""
    file: str = ""
    suite_runs: int = 0
    rolled_back_exact: bool = True
    seconds: float = 0.0
    red_before: list[str] = field(default_factory=list)
    broke: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "CERTIFIED"

    def render(self) -> str:
        head = f"{self.verdict}: {self.why}"
        tail = (f"  file {self.file} · {self.suite_runs} suite runs · {self.seconds}s · "
                f"rolled back byte-exact: {self.rolled_back_exact}")
        if self.red_before:
            tail += f"\n  red before: {', '.join(self.red_before)}"
        if self.broke:
            tail += f"\n  broke: {', '.join(self.broke)}"
        return head + "\n" + tail


def certify(root: str | Path, rel_file: str, patched: str, python: str = sys.executable,
            confirm: int = 2) -> Certificate:
    """Judge `patched` as the new content of `rel_file` under `root`'s own suite."""
    root = Path(root); t0 = time.time()
    o = Oracle(str(root), python=python)
    f = root / rel_file
    original, before_sha = f.read_text(encoding="utf-8"), sha(f)
    c = Certificate(file=rel_file)

    def done(verdict, why, broke=()):
        f.write_text(original, encoding="utf-8")            # the rollback IS the refusal
        c.verdict, c.why, c.broke = verdict, why, list(broke)
        c.rolled_back_exact = sha(f) == before_sha
        c.seconds = round(time.time() - t0, 2)
        return c

    try:
        green0, red_ids = failing_ids(o)
    except HarnessError as e:
        return done("HARNESS", str(e)[:200])
    c.suite_runs += 1
    c.red_before = sorted(red_ids)
    if green0:
        return done("NOT-RED", "the suite already accepts this code — there is nothing to certify")

    f.write_text(patched if patched.endswith("\n") else patched + "\n", encoding="utf-8")
    ok, why = o.check()
    c.suite_runs += 1
    if not ok:
        _g, now_red = failing_ids(o)
        c.suite_runs += 1
        collateral = sorted(now_red - red_ids)
        if collateral:
            return done("COLLATERAL", f"turned {len(collateral)} passing test(s) red: {', '.join(collateral)}",
                        collateral)
        return done("FAILS", (why or "the suite still rejects it")[:200])
    for i in range(confirm):
        again, why2 = o.check()
        c.suite_runs += 1
        if not again:
            return done("FLAKY", f"green once, red on re-check {i + 1}: {(why2 or '')[:160]}")
    return done("CERTIFIED", "red before, green on the full suite, stable on re-check, nothing else broken")
