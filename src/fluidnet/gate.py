# SPDX-License-Identifier: AGPL-3.0-or-later
"""A gate for CODE actions: ALLOW / WARN / BLOCK for a proposed change to a file.

The same shape as a truth-layer gate for an agent's queries — one call before the action, a deterministic
verdict, evidence attached — but the object is a patch, and the judges are the ones that can judge a patch:
the repository's own suite (red before, green after, stable, no collateral, byte-exact rollback) and, where
a taught class applies, its property (algebra over the rewrite, before any test).

    ALLOW   certified by the full suite, and no class property refutes it
    BLOCK   a class property refuted it (with the refuting input), or the suite did — fails, breaks a
            passing test, or goes green only sometimes
    WARN    the suite cannot judge: it was not red before (nothing to certify) or it could not run

Verdicts never leave the patch applied. Apply it yourself once you have ALLOW."""
from __future__ import annotations

import difflib
import sys
from dataclasses import asdict
from pathlib import Path

from .certify import certify

ALLOW, WARN, BLOCK = "ALLOW", "WARN", "BLOCK"


def _changed_lines(original: str, patched: str):
    """(original_line, new_line) for every one-line replacement in the diff; multi-line hunks are skipped —
    a class property speaks about one rewrite."""
    a, b = original.split("\n"), patched.split("\n")
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
        if tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1:
            out.append((i1 + 1, a[i1], b[j1]))
    return out


def property_verdicts(original: str, patched: str, dictionary: str | None):
    """Ask every taught class whose signal matches a changed line. Returns a list of findings."""
    if not dictionary:
        return []
    from fluidfix.acts import KINDS, load_dictionary
    from fluidfix.props import PROPERTIES, check
    load_dictionary(dictionary)
    found = []
    for lineno, old, new in _changed_lines(original, patched):
        for kind, entry in sorted(KINDS.items()):
            sig = entry[2]
            if kind not in PROPERTIES or sig is None or not sig.search(old):
                continue
            verdict, why, n = check(kind, old, new)
            found.append({"line": lineno, "kind": kind, "class": entry[0], "verdict": verdict,
                          "why": why, "inputs": n})
    return found


def gate(root: str | Path, rel_file: str, patched: str, dictionary: str | None = None,
         python: str = sys.executable, confirm: int = 2) -> dict:
    root = Path(root)
    original = (root / rel_file).read_text(encoding="utf-8")
    props = property_verdicts(original, patched, dictionary)
    refuted = [p for p in props if p["verdict"] == "REFUTED"]
    if refuted:
        r = refuted[0]
        return {"verdict": BLOCK, "file": rel_file, "suite_runs": 0,
                "reason": f"class property refuted it before any suite run — {r['class']}: {r['why']}",
                "property": props, "certificate": None}
    c = certify(root, rel_file, patched, python=python, confirm=confirm)
    if c.verdict == "CERTIFIED":
        verdict, reason = ALLOW, c.why
    elif c.verdict in ("NOT-RED", "HARNESS"):
        verdict, reason = WARN, c.why
    else:
        verdict, reason = BLOCK, f"{c.verdict}: {c.why}"
    return {"verdict": verdict, "file": rel_file, "suite_runs": c.suite_runs, "reason": reason,
            "property": props, "certificate": asdict(c)}


def render(g: dict) -> str:
    head = f"{g['verdict']}: {g['reason']}"
    tail = f"  file {g['file']} · {g['suite_runs']} suite runs"
    for p in g["property"]:
        tail += f"\n  property · line {p['line']} · {p['class']}: {p['verdict']}" + (f" — {p['why']}" if p["why"] else "")
    if g["certificate"] and g["certificate"].get("rolled_back_exact") is not None:
        tail += f"\n  rolled back byte-exact: {g['certificate']['rolled_back_exact']}"
    return head + "\n" + tail
