# SPDX-License-Identifier: AGPL-3.0-or-later
"""Many small nets, one overseer.

A guard's dictionary is 16 slots, 7 of them yours — a hard ceiling, but a ceiling PER PROCESS. So each net
is one `fluidfix guard` process with its own dictionary, N nets carry 7N taught classes, and the overseer
only has to route. Routing is a measurement, not a guess: each net's signals are scanned over the source
files, and nets are tried in order of how much of the repository they recognise. The first net whose guard
repairs wins; every other net's refusal is kept."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "tests", "test", "build", "dist"}


def fluidfix_bin() -> str:
    beside = Path(sys.executable).parent / "fluidfix"
    if beside.exists():
        return str(beside)
    found = shutil.which("fluidfix")
    if not found:
        raise RuntimeError("fluidfix is not installed beside this interpreter or on PATH")
    return found


def signals_of(dictionary: str) -> list:
    """The signals a dictionary registers, captured without touching the live registry."""
    got = []
    ns = {"re": re, "register": lambda k, n, d, s, a: got.append((k, n, s)),
          "teach_property": lambda *a, **k: None, "SpanEdit": object}
    try:
        from fluidfix import propcheck
        ns["propcheck"] = propcheck
    except ImportError:
        ns["propcheck"] = None
    src = Path(dictionary).read_text(encoding="utf-8")
    exec(compile(src, dictionary, "exec"), ns)
    return got


def source_files(root: Path):
    for p in root.rglob("*.py"):
        if not any(part in _SKIP for part in p.relative_to(root).parts):
            yield p


@dataclass
class NetScore:
    dictionary: str
    classes: int
    hits: int
    files: list[str] = field(default_factory=list)


def score(root: str | Path, nets: list[str]) -> list[NetScore]:
    """Order nets by how much of the repository their signals recognise. Highest first."""
    root = Path(root)
    texts = {str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="replace")
             for p in source_files(root)}
    out = []
    for net in nets:
        sigs = signals_of(net)
        hits, files = 0, []
        for rel, text in texts.items():
            n = sum(len(sig.findall(text)) for _k, _n, sig in sigs if sig is not None)
            if n:
                hits += n; files.append(rel)
        out.append(NetScore(net, len(sigs), hits, files))
    return sorted(out, key=lambda s: -s.hits)


@dataclass
class Outcome:
    net: str
    status: str                  # repaired | refused | green | error
    output: str
    exit: int


def run_net(root: str | Path, net: str, commit: bool, python: str | None = None,
            extra: list[str] | None = None) -> Outcome:
    """One net = one fluidfix process with one dictionary."""
    cmd = [fluidfix_bin(), "guard", str(root), "--dictionary", net]
    cmd.append("--commit" if commit else "--dry-run")
    if python:
        cmd += ["--python", python]
    cmd += extra or []
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if "repaired line" in out or "PROPOSED (dry-run)" in out:
        status = "repaired"
    elif "suite green" in out:
        status = "green"
    elif r.returncode == 2 or "REFUSED" in out:
        status = "refused"
    else:
        status = "error"
    return Outcome(net, status, out.strip(), r.returncode)


def watch(root: str | Path, nets: list[str], commit: bool = False, python: str | None = None,
          extra: list[str] | None = None) -> dict:
    """Route once. Returns {"order": [...], "outcomes": [...], "winner": net | None}."""
    order = score(root, nets)
    outcomes, winner = [], None
    for s in order:
        o = run_net(root, s.dictionary, commit, python, extra)
        outcomes.append(o)
        if o.status in ("repaired", "green"):
            winner = s.dictionary
            break
    return {"order": order, "outcomes": outcomes, "winner": winner}
