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
    patched: str = ""            # the repaired file's text, when a repair was found


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


# ------------------------------------------------------------------ buggy finds, the nets fix and certify
#
# Measured 2026-09-24 on real click (a regression at parser.py:437, `<` -> `<=`, 92 failing tests): the blind
# guard searched core.py, decorators.py and formatting.py and refused at its 300 s budget without opening
# parser.py — the knowledge was there, the SEARCH was the bottleneck. buggy's mutation lane put parser.py:437
# first in 279 s and proposed `<= -> <`; `fluidfix repair --file` repairs it exactly in 130 s. So watch asks
# buggy WHERE, and the nets only ever search the files buggy names.

def buggy_bin() -> str | None:
    beside = Path(sys.executable).parent / "buggy"
    return str(beside) if beside.exists() else shutil.which("buggy")


def buggy_has_mutation(bb: str) -> bool:
    """PyPI's buggy-cli 0.1.0 predates the mutation lane — the lane that found the click bug."""
    r = subprocess.run([bb, "locate", "--help"], capture_output=True, text=True)
    return "--no-mutate" in r.stdout


@dataclass
class Leads:
    files: list = field(default_factory=list)      # buggy's files, best evidence first
    lines: dict = field(default_factory=dict)      # file -> the lines buggy flagged in it, any lane
    repairs: list = field(default_factory=list)    # buggy's proposed one-token repairs {file, line, was, now, edit}
    seconds: float = 0.0
    commit: str = ""                               # the commit bisect blamed, if it converged
    status: str = ""                               # buggy's own: red | green | error


def leads_from(d: dict, top_files: int = 3) -> Leads:
    """Order files by the kind of evidence: an EXPERIMENT (the mutation lane) and the INTRODUCING COMMIT are
    direct; coverage (the cause law) and where missing code belongs (the omission law) are circumstantial.
    A lane's rank 0 is a veto and contributes nothing."""
    order = []
    def take(f):
        if f and f not in order:
            order.append(f)
    for m in d.get("mutation") or []:
        if int(m.get("rank", 0) or 0) > 0: take(m["file"])
    for f in ((d.get("when") or {}).get("hunks") or {}):
        take(f)
    for lane in ("where", "omission"):
        for m in d.get(lane) or []:
            if int(m.get("rank", 0) or 0) > 0: take(m["file"])
    # buggy's POINTING is its top findings per lane — the ones its own report shows a person (8, 8, 5), each
    # list already ranked. `buggy locate --json` prints every scored line; taking all of them handed a repair
    # a 600-line "focus" in click's core.py, which searched like the whole file (measured 2026-09-24: 55+
    # minutes, against 165 s on buggy's 11 flagged lines).
    TOP = {"mutation": 8, "where": 8, "omission": 5}
    lines = {}
    for lane, k in TOP.items():
        for m in (d.get(lane) or [])[:k]:
            if int(m.get("rank", 0) or 0) > 0:
                lines.setdefault(m["file"], set()).add(int(m["line"]))
    return Leads(files=order[:top_files], lines={f: sorted(v) for f, v in lines.items()},
                 repairs=list(d.get("repairs") or []),
                 seconds=float(d.get("seconds") or 0), commit=(d.get("when") or {}).get("commit", ""),
                 status=d.get("status", ""))


def buggy_leads(root, python: str | None = None, jobs: int = 1, mutate_seconds: int = 240,
                top_files: int = 3, timeout: int = 1800) -> Leads | None:
    """Run `buggy locate --json` in its own process group. None when buggy is not installed."""
    import json, os, signal, tempfile
    bb = buggy_bin()
    if not bb:
        return None
    cmd = [bb, "locate", str(root), "--json", "-j", str(jobs), "--mutate-seconds", str(mutate_seconds)] + \
          (["--python", python] if python else [])
    with tempfile.TemporaryFile() as fo:
        p = subprocess.Popen(cmd, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(p.pid, signal.SIGKILL)      # nothing a mutant spawned may outlive the run
        except (ProcessLookupError, PermissionError):
            pass
        p.wait(); fo.seek(0); out = fo.read().decode(errors="replace")
    d = None
    i = out.find("{")
    if i >= 0:
        try:
            d = json.loads(out[i:])
        except ValueError:
            d = None
    if d is None and (Path(root) / ".buggy" / "locate.json").exists():
        d = json.loads((Path(root) / ".buggy" / "locate.json").read_text())
    if d is None:
        return Leads(status="error")
    return leads_from(d, top_files)


def apply_repair(root, rep: dict) -> str | None:
    """buggy's proposal as a whole new file, only if the line still reads what buggy saw."""
    f = Path(root) / rep["file"]
    lines = f.read_text(encoding="utf-8").split("\n")
    i = int(rep["line"]) - 1
    if not (0 <= i < len(lines)) or lines[i] != rep["was"]:
        return None
    lines[i] = rep["now"]
    return "\n".join(lines)


def _commit(root, rel: str, message: str) -> None:
    subprocess.run(["git", "add", "--", rel], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", message, "--", rel], cwd=root, capture_output=True)


def fluidfix_has_focus() -> bool:
    """`fluidfix repair --focus` arrived after fluidfix 0.16.0."""
    r = subprocess.run([fluidfix_bin(), "repair", "--help"], capture_output=True, text=True)
    return "--focus" in r.stdout


def repair_file(root, net: str | None, rel: str, commit: bool, python: str | None = None,
                focus: list | None = None) -> Outcome:
    """One net, the file named. `fluidfix repair` writes a repair it ships; unless committing, the bytes are
    put back and the repair is reported as a diff."""
    import difflib, json
    f = Path(root) / rel
    before = f.read_bytes()
    cmd = [fluidfix_bin(), "repair", str(root), "--file", rel, "--json"] + \
          (["--dictionary", net] if net else []) + (["--python", python] if python else []) + \
          (["--focus", ",".join(map(str, focus))] if focus else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    after = f.read_bytes()
    d = {}
    i = out.find("{")
    if i >= 0:
        try:
            d = json.loads(out[i:])
        except ValueError:
            pass
    if r.returncode == 0 and d.get("repaired"):
        diff = "".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                            f"a/{rel}", f"b/{rel}"))
        if commit:
            _commit(root, rel, f"fluidnet: repair {rel}:{d.get('lineno')} ({Path(net).name if net else 'shipped'})")
        else:
            f.write_bytes(before)
        scope = d.get("scope", "file")
        return Outcome(net or "shipped", "repaired",
                       (diff or out.strip()) + (f"\n(scope: {scope} — unique within these lines only)"
                                                if scope != "file" else ""), 0, after.decode())
    if after != before:                                  # a refusal leaves the file as found
        f.write_bytes(before)
    return Outcome(net or "shipped", "refused" if r.returncode == 2 else "error", out.strip()[-600:], r.returncode)


def watch_with_buggy(root, nets: list[str], commit: bool = False, python: str | None = None,
                     jobs: int = 1, mutate_seconds: int = 240, top_files: int = 3, fallback: bool = True) -> dict:
    """buggy locates; fluidnet certifies buggy's proposals, then each net repairs with the file named.
    Falls back to the blind search only when buggy is absent or names no file."""
    import time
    from .certify import certify
    t0 = time.time()
    stages, outcomes = [], []
    leads = buggy_leads(root, python, jobs, mutate_seconds, top_files)
    # buggy's status contract: green (pytest exited 0), red, or harness (the suite could not be judged —
    # nothing collected, a collection or internal error, a killed run). harness means DO NOTHING: it is not
    # green, and a blind search over a suite that cannot be judged would only produce refusals.
    # green is pytest's own exit 0: nothing to do. harness is buggy's word that IT could not judge the suite —
    # and buggy only ever helps, so its verdict never stops fluidnet from judging for itself. Measured
    # 2026-09-24 on click: parametrized test ids with spaces (`[no-wrap mark-sentence < max]`) made buggy
    # read zero failing tests out of a red suite and answer `harness` in 0 s. fluidnet's own guard has its own
    # harness check; a suite that truly cannot be judged still gets nothing attempted there.
    if leads is not None and leads.status == "green":
        return {"order": [], "outcomes": [], "winner": None, "leads": leads, "seconds": round(time.time() - t0, 1),
                "stages": [("locate (buggy)", round(leads.seconds, 1), "suite green — nothing to do")],
                "status": "green"}
    if leads is None or not leads.files:
        why = ("buggy is not installed" if leads is None else
               "buggy could not judge the suite (harness)" if leads.status == "harness" else
               f"buggy named no file ({leads.status or 'no evidence'})")
        r = watch(root, nets, commit, python)
        r.update(stages=[("locate", 0.0, why + " — fluidnet searches alone")], leads=leads, seconds=round(time.time() - t0, 1))
        return r
    stages.append(("locate (buggy)", round(leads.seconds, 1),
                   f"files {', '.join(leads.files)}; {len(leads.repairs)} proposed repair(s)"
                   + (f"; introduced by {leads.commit[:8]}" if leads.commit else "")))
    # 1. the recursive half: a patch fluidnet did not write, judged by fluidnet's gates
    for rep in leads.repairs:
        patched = apply_repair(root, rep)
        if patched is None:
            continue
        c = certify(root, rep["file"], patched, python=python or sys.executable)
        stages.append(("certify buggy's repair", c.seconds, f"{c.verdict}: {rep['file']}:{rep['line']} {rep.get('edit', '')}"))
        if c.ok:
            if commit:
                (Path(root) / rep["file"]).write_text(patched, encoding="utf-8")
                _commit(root, rep["file"], f"fluidnet: certified buggy's repair {rep['file']}:{rep['line']} ({rep.get('edit', '')})")
            o = Outcome("buggy (certified by fluidnet)", "repaired",
                        f"- {rep['was'].strip()}\n+ {rep['now'].strip()}", 0)
            return {"order": [], "outcomes": [o], "winner": o.net, "stages": stages, "leads": leads,
                    "seconds": round(time.time() - t0, 1)}
    # 2. the taught nets, searching only the files buggy named
    # Proving a fix unique means judging every candidate in scope. With the whole file as scope, a broad taught
    # class in a big file is thousands of candidates (a sibling-attribute bug in click's core.py: 35 min, then
    # refused). With buggy's lines as scope the same bug shipped exactly in 165 s. So: buggy's lines first,
    # the certificate stating that scope; the whole file only if nothing in them ships.
    order = score(root, nets)
    focused = fluidfix_has_focus()
    for scope in (("focus", "file") if focused else ("file",)):
        for s in order:
            for rel in leads.files:
                focus = leads.lines.get(rel) if scope == "focus" else None
                if scope == "focus" and not focus:
                    continue
                t1 = time.time()
                # a fix found through buggy's focus is never committed on the loop's word alone
                o = repair_file(root, s.dictionary, rel, commit and scope == "file", python, focus=focus)
                outcomes.append(o)
                stages.append((f"repair {rel} ({Path(s.dictionary).name}, {scope})", round(time.time() - t1, 1), o.status))
                if o.status == "repaired" and scope == "focus":
                    # buggy HELPED find it — so fluidnet certifies it, independently, before buggy's help counts.
                    # Only a CERTIFIED fix goes ahead; otherwise buggy's help is rejected and the whole file is
                    # searched as if buggy had never spoken.
                    c = certify(root, rel, o.patched, python=python or sys.executable)
                    stages.append(("certify the fix buggy's focus found", c.seconds, c.verdict))
                    if not c.ok:
                        o.status = "rejected"
                        continue
                    if commit:
                        (Path(root) / rel).write_text(o.patched, encoding="utf-8")
                        _commit(root, rel, f"fluidnet: repair {rel} (buggy's focus, certified by fluidnet)")
                    o.output += "\ncertified by fluidnet: red before, green on the full suite, stable, nothing else broken"
                if o.status == "repaired":
                    return {"order": order, "outcomes": outcomes, "winner": s.dictionary, "stages": stages,
                            "leads": leads, "seconds": round(time.time() - t0, 1)}
    # buggy's help led nowhere: drop it, and let fluidnet search on its own, as if buggy had never spoken.
    # Measured 2026-09-24 on click: buggy named core.py, formatting.py and testing.py for a bug in
    # _textwrap.py; the nets refused all three and, with no fallback, the answer was a refusal that
    # fluidnet's own search — the file named — reaches exactly in 89 s.
    if fallback:
        t2 = time.time()
        blind = watch(root, nets, commit, python)
        stages.append(("buggy's files exhausted — fluidnet searches alone", round(time.time() - t2, 1),
                       f"winner: {blind['winner']}" if blind["winner"] else "refused"))
        blind.update(stages=stages, leads=leads, seconds=round(time.time() - t0, 1))
        return blind
    return {"order": order, "outcomes": outcomes, "winner": None, "stages": stages, "leads": leads,
            "seconds": round(time.time() - t0, 1)}
