# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sweep — do what you taught, everywhere, with nothing red to start from.

`watch` and `repair` begin from a failing test: the red suite is the spec and the net makes it green. A
migration, a house convention, a deprecation — work you teach once and want done at every site — has no
failing test. The judge stays the same; one rule changes:

    PROPERTY     the class's own property PROVES each rewrite     a site without a proof is never written
    EXERCISED    the suite runs the rewritten line                a line no test runs is not judged by it
    GREEN-GREEN  the full suite is green before and after         behaviour kept, not bugs fixed
    STABLE       the green repeats on re-check                    the engine law's HIDDEN lane
    ROLLBACK     a dry run leaves every file byte-identical       sha256 before and after

A rewrite must be a function: one line in, one line out. A class that proposes several candidates for a
line is choosing, and a green suite cannot choose between candidates that all keep it green — that site is
AMBIGUOUS and left alone. Sites that turn the suite red are found by halving and refused one by one; the
rest ship. Nothing here is a model: the rules are yours, the proof is your property, the judge your suite."""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

APPLIED, REFUTED, UNPROVEN, AMBIGUOUS, UNEXERCISED, BROKE, TAKEN = (
    "APPLIED", "PROPERTY-REFUTED", "PROPERTY-UNPROVEN", "AMBIGUOUS", "UNEXERCISED", "BROKE-TESTS",
    "LINE-TAKEN")


@dataclass
class Site:
    file: str
    line: int
    net: str
    kind: int
    cls: str
    before: str
    after: str = ""
    verdict: str = ""
    why: str = ""


@dataclass
class Sweep:
    status: str = ""                 # CERTIFIED | NOTHING | RED-BEFORE | NO-PROPERTY | FLAKY | HARNESS
    why: str = ""
    sites: list = field(default_factory=list)
    suite_runs: int = 0
    seconds: float = 0.0
    committed: bool = False
    rolled_back_exact: bool = True
    diff: str = ""
    deselected: list = field(default_factory=list)

    @property
    def applied(self):
        return [s for s in self.sites if s.verdict == APPLIED]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _kinds_registered_by(dictionary: str):
    """Load a dictionary into the live registry and say which kinds it wrote. The property registry is
    per process: a net that re-registers a kind WITHOUT teaching its property must not inherit the property
    an earlier net taught for that slot — that property is about a different class — so it is dropped."""
    from fluidfix.acts import KINDS, load_dictionary
    from fluidfix import props
    before = {k: v for k, v in KINDS.items()}
    taught_before = dict(props.PROPERTIES)
    load_dictionary(dictionary)
    kinds = [k for k in KINDS if before.get(k) is not KINDS[k]]
    for k in kinds:
        if k in props.PROPERTIES and props.PROPERTIES[k] is taught_before.get(k):
            del props.PROPERTIES[k]
    return kinds


def _statement_start(tree, line: int) -> int:
    """The first line of the innermost statement holding `line` — coverage reports statements there."""
    best = None
    for n in ast.walk(tree):
        if isinstance(n, ast.stmt) and n.lineno <= line <= (n.end_lineno or n.lineno):
            if best is None or n.lineno >= best.lineno:
                best = n
    return best.lineno if best is not None else line


def propose(root: Path, nets: list[str], files: list[str]) -> list[Site]:
    """Every site any net's signal lights, with its one rewrite and the property's verdict on it."""
    from fluidfix.acts import KINDS, ACTS, Observation, act_for, candidates
    from fluidfix import props
    sites, taken = [], set()
    for net in nets:
        kinds = _kinds_registered_by(net)
        missing = props.classes_without_properties(kinds)
        if missing:
            raise ValueError(f"{net}: no property taught for kind(s) {missing} — a sweep writes only what a "
                             f"property proves; put teach_property() beside register()")
        for rel in files:
            lines = (root / rel).read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines, 1):
                for k in kinds:
                    name, _desc, sig = KINDS[k]
                    if not sig.search(line):
                        continue
                    o = Observation(lineno=i, kinds=[k], file=rel, root=str(root), all_lines=lines)
                    outs = []
                    for c in candidates(line, act_for(k), o):
                        if isinstance(c, str) and c != line and c not in outs:
                            outs.append(c)
                    if not outs:
                        continue
                    s = Site(rel, i, net, k, name, line)
                    if (rel, i) in taken:
                        s.verdict, s.why = TAKEN, "another class already rewrites this line"
                    elif len(outs) > 1:
                        s.verdict, s.why = AMBIGUOUS, f"{len(outs)} rewrites proposed; a sweep needs exactly one"
                    else:
                        s.after = outs[0]
                        v, why, _n = props.check(k, line, s.after)
                        if v == props.REFUTED:
                            s.verdict, s.why = REFUTED, why
                        elif v != props.PROVEN:
                            s.verdict, s.why = UNPROVEN, why
                        else:
                            taken.add((rel, i))
                    sites.append(s)
    return sites


def _executed(o, root: Path) -> tuple[int, dict, str]:
    """One full suite run under coverage: (exit code, {file: executed lines}, output)."""
    fd, report = tempfile.mkstemp(suffix=".json"); os.close(fd)
    try:
        o.clear_pyc()
        rc, out = o.run(["--tb=no", "--cov=.", f"--cov-report=json:{report}", "--cov-fail-under=0"])
        try:
            data = json.loads(Path(report).read_text() or "{}").get("files", {})
        except (OSError, ValueError):
            data = {}
    finally:
        try:
            os.remove(report)
        except OSError:
            pass
    ran = {}
    for f, d in data.items():
        rel = os.path.relpath(os.path.join(str(root), f), str(root)) if not os.path.isabs(f) else os.path.relpath(f, str(root))
        ran[rel.replace("\\", "/")] = set(d.get("executed_lines", []))
    return rc, ran, out


def _write(root: Path, originals: dict, sites: list[Site]) -> None:
    """Put exactly these sites' rewrites into the tree (every other line as it was)."""
    by_file = {}
    for s in sites:
        by_file.setdefault(s.file, []).append(s)
    for rel, text in originals.items():
        lines = text.split("\n")
        for s in by_file.get(rel, []):
            lines[s.line - 1] = s.after
        (root / rel).write_text("\n".join(lines), encoding="utf-8")


def sweep(root: str | Path, nets: list[str], python: str | None = None, paths: list[str] | None = None,
          commit: bool = False, trust_property: bool = False, confirm: int = 1,
          deselect: list[str] | None = None) -> Sweep:
    from fluidfix.oracle import Oracle
    try:
        from fluidfix.oracle import HarnessError, _check_harness
    except ImportError:
        class HarnessError(Exception): ...
        def _check_harness(*a, **k): ...
    from .overseer import source_files
    root = Path(root).resolve(); t0 = time.time(); r = Sweep()
    if paths:
        files = sorted({str(p.relative_to(root)) for x in paths
                        for p in ([root / x] if (root / x).is_file() else (root / x).rglob("*.py"))})
    else:
        files = sorted(str(p.relative_to(root)) for p in source_files(root))
    try:
        r.sites = propose(root, nets, files)
    except ValueError as e:
        r.status, r.why = "NO-PROPERTY", str(e); return r
    live = [s for s in r.sites if not s.verdict]
    if not live:
        r.status, r.why = "NOTHING", "no site where a taught rewrite is proved"
        r.seconds = round(time.time() - t0, 2); return r
    touched = sorted({s.file for s in live})
    originals = {f: (root / f).read_text(encoding="utf-8") for f in touched}
    shas = {f: _sha(root / f) for f in touched}
    r.deselected = list(deselect or [])
    o = Oracle(str(root), python=python or sys.executable,
               extra_args=[a for d in r.deselected for a in ("--deselect", d)])

    def restore():
        for f, text in originals.items():
            (root / f).write_text(text, encoding="utf-8")
        r.rolled_back_exact = all(_sha(root / f) == shas[f] for f in touched)

    def green(sites) -> bool:
        _write(root, originals, sites)
        o.clear_pyc()
        rc, out = o.run(["--tb=no"])
        r.suite_runs += 1
        restore()
        return rc == 0

    def finish(status, why):
        r.status, r.why, r.seconds = status, why, round(time.time() - t0, 2)
        return r

    try:
        rc, ran, out = _executed(o, root)
        r.suite_runs += 1
        _check_harness(rc, o.extra_args + ["--cov=."], out, o.root, o.python)
    except HarnessError as e:
        return finish("HARNESS", str(e)[:200])
    if rc != 0:
        return finish("RED-BEFORE", "the suite is red before any rewrite — a sweep keeps green green; get green "
                                    "first (or use `fluidnet watch`, which starts from red)")
    for s in live:
        tree = ast.parse(originals[s.file])
        if _statement_start(tree, s.line) not in ran.get(s.file, set()) and not trust_property:
            s.verdict, s.why = UNEXERCISED, "no test runs this line; only the property vouches for it"
    live = [s for s in live if not s.verdict]

    accepted = []

    def halve(group):
        if not group:
            return
        if green(group):
            accepted.extend(group); return
        if len(group) == 1:
            group[0].verdict, group[0].why = BROKE, "the suite turns red with this rewrite"; return
        mid = len(group) // 2
        halve(group[:mid]); halve(group[mid:])

    halve(live)
    if accepted and not green(accepted):                   # halves green alone, red together: one at a time
        kept = []
        for s in accepted:
            if green(kept + [s]):
                kept.append(s)
            else:
                s.verdict, s.why = BROKE, "red together with the sites kept before it"
        accepted = kept
    for i in range(confirm):
        if accepted and not green(accepted):
            for s in accepted:
                s.verdict, s.why = BROKE, f"green once, red on re-check {i + 1}"
            restore()
            return finish("FLAKY", "the suite did not repeat its green; nothing written")
    for s in accepted:
        s.verdict = APPLIED
        s.why = "property proved · suite green before and after, stable" + (
            "" if s.file in ran and _statement_start(ast.parse(originals[s.file]), s.line) in ran[s.file]
            else " · NOT run by any test (--trust-property)")
    _write(root, originals, accepted)
    r.diff = "".join("".join(difflib.unified_diff(
        [l + "\n" for l in originals[f].split("\n")], [l + "\n" for l in (root / f).read_text().split("\n")],
        f"a/{f}", f"b/{f}", n=1)) for f in touched if (root / f).read_text() != originals[f])
    if commit and accepted:
        changed = sorted({s.file for s in accepted})
        classes = sorted({s.cls for s in accepted})
        subprocess.run(["git", "add", "--", *changed], cwd=root, capture_output=True)
        msg = (f"fluidnet sweep: {', '.join(classes)} at {len(accepted)} site(s)\n\n"
               f"Each rewrite proved by its class property and run by the suite; the full suite green "
               f"before and after, stable on re-check. {r.suite_runs} suite runs, no model.")
        c = subprocess.run(["git", "commit", "-q", "-m", msg, "--", *changed], cwd=root, capture_output=True)
        r.committed = c.returncode == 0
    else:
        restore()
    return finish("CERTIFIED" if accepted else "NOTHING",
                  f"{len(accepted)} site(s) certified" if accepted else "no site survived the judge")


def render(r: Sweep) -> str:
    out = []
    w = max((len(f"{s.file}:{s.line}") for s in r.sites), default=10)
    order = [APPLIED, BROKE, UNEXERCISED, REFUTED, UNPROVEN, AMBIGUOUS, TAKEN]
    for s in sorted(r.sites, key=lambda s: (order.index(s.verdict) if s.verdict in order else 9, s.file, s.line)):
        out.append(f"  {s.verdict:17} {f'{s.file}:{s.line}':{w}}  {s.cls}")
        if s.verdict == APPLIED:
            out.append(f"  {'':17} {'':{w}}  - {s.before.strip()}\n  {'':17} {'':{w}}  + {s.after.strip()}")
        elif s.why:
            out.append(f"  {'':17} {'':{w}}  {s.why}")
    counts = {}
    for s in r.sites:
        counts[s.verdict] = counts.get(s.verdict, 0) + 1
    out.append("")
    out.append(f"{r.status}: {r.why}")
    out.append("  " + " · ".join(f"{v} {counts[v]}" for v in order if v in counts)
               + f" · {r.suite_runs} suite runs · {r.seconds}s · 0 tokens")
    if r.deselected:
        out.append(f"  deselected by you, before and after alike: {', '.join(r.deselected)}")
    if r.status == "CERTIFIED":
        out.append("  committed" if r.committed else
                   f"  dry run: the tree is as you left it (restored byte-exact: {r.rolled_back_exact}); --commit keeps it")
    return "\n".join(out)


def as_json(r: Sweep) -> str:
    d = asdict(r)
    return json.dumps(d, indent=1)
