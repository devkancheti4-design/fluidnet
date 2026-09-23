# SPDX-License-Identifier: AGPL-3.0-or-later
"""Locate the root cause of a red suite — three lanes of evidence, every one mechanical.

    WHERE   which file, which line: the lines the failing test executed (coverage), the frames the
            failure quotes (traceback), the literals the assertion mentions, the lines git touched
            recently. Pointing evidence outranks circumstantial — the SIGHT law's grading, reused.
    WHEN    which commit introduced it: automated bisect in a throwaway worktree, the failing test as
            the oracle, then the first bad commit's hunks intersected with WHERE.
    WHY     where the failing run first parts from a passing one: the failing test and a passing test
            that reaches the same function are traced line by line; the first line where control flow
            or a local's value differs is the divergence.

Nothing predicts. A finding's confidence is the COUNT of independent lanes that agree on it, and a lane
with no evidence says so instead of guessing. The tree is never touched: bisect runs in a worktree,
tracing runs in a subprocess."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fluidfix.guard import _recent_lines, find_candidate_files
from fluidfix.localize import build_packet
from fluidfix.oracle import Oracle

_FRAME = re.compile(r"([\w./\\-]+\.py)[\":,]+\s*(?:line\s+)?(\d+)")
_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+?)(?: - .*)?$", re.M)
_CALL = re.compile(r"\b([A-Za-z_]\w*)\(")
_LITERAL = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?|\"[^\"]*\"|'[^']*')")


@dataclass
class Finding:
    file: str
    line: int
    source: str
    lanes: list = field(default_factory=list)
    score: int = 0
    # the eight measured bits a ranking LAW would take (fluidfix/docs/laws/CAUSE_LAW_PROMPT.md): logged
    # for every candidate so a law can be judged on held-out real bugs without a rerun
    bits: dict = field(default_factory=lambda: {k: 0 for k in
                       ("FRAME", "LITERAL", "RECENT", "BISECT", "DIVERGE", "EF_ALL", "EP_NONE", "IMPORT")})


@dataclass
class Located:
    status: str = "green"                       # green | red | harness
    failing: list = field(default_factory=list)
    where: list = field(default_factory=list)   # Findings, best first
    when: dict | None = None
    why: dict | None = None
    notes: list = field(default_factory=list)
    seconds: float = 0.0

    def render(self) -> str:
        if self.status == "green":
            return "suite green — nothing to locate"
        if self.status == "harness":
            return "cannot judge: " + "; ".join(self.notes)
        out = [f"RED — {len(self.failing)} failing: {', '.join(self.failing[:3])}" +
               (" …" if len(self.failing) > 3 else ""), "root cause, by lanes of evidence agreeing:"]
        for i, f in enumerate(self.where[:5], 1):
            out.append(f"  {i}. {f.file}:{f.line}   {f.source.strip()[:60]}")
            out.append(f"       [{', '.join(f.lanes)}]  {len(f.lanes)} lane{'s' if len(f.lanes) != 1 else ''}")
        if self.when:
            w = self.when
            out.append(f"when: {w['commit'][:8]} \"{w['subject']}\" introduced the failure "
                       f"(bisect, {w['runs']} test runs)")
        if self.why:
            y = self.why
            if y.get("diverges_at"):
                out.append(f"why:  paths part at {y['diverges_at']['file']}:{y['diverges_at']['line']} "
                           f"against passing {y['sibling']}" + (f" — {y['detail']}" if y.get("detail") else ""))
            else:
                out.append(f"why:  {y.get('note', 'no evidence')}")
        for n in self.notes:
            out.append(f"note: {n}")
        return "\n".join(out)


# ------------------------------------------------------------------ WHERE
def _failing_ids(out: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _FAILED.finditer(out)))


def _frames_in(out: str, rel: str) -> set[int]:
    want = rel.replace("\\", "/")
    hits = set()
    for p, n in _FRAME.findall(out):
        p = p.replace("\\", "/")
        if p == want or p.endswith("/" + want) or want.endswith("/" + p):
            hits.add(int(n))
    return hits


def _assertion_tokens(out: str) -> set[str]:
    toks = set()
    for l in out.splitlines():
        s = l.strip()
        if s.startswith((">", "E ")) and ("assert" in s or "==" in s or "where" in s):
            toks |= {t.strip("\"'") for t in _LITERAL.findall(s)}
            toks |= {m for m in re.findall(r"\b([A-Za-z_]\w*)\(", s)}
    return {t for t in toks if t not in {"assert", "where", "and", "or", "not", "in", "is"}}


def where(oracle: Oracle, out: str, top_files: int = 3) -> tuple[list[Finding], list[str]]:
    ev: dict = {}
    files = find_candidate_files(oracle, out, evidence=ev)[:top_files]
    toks = _assertion_tokens(out)
    findings, notes = [], []
    for rel in files:
        try:
            pk = build_packet(oracle, rel)
        except Exception as e:
            notes.append(f"{rel}: packet failed ({type(e).__name__})"); continue
        if pk is None:
            continue
        frames = _frames_in(out, rel)
        recent = _recent_lines(oracle.root, rel)
        for n in pk.lines:
            src = pk.src_lines[n - 1] if n - 1 < len(pk.src_lines) else ""
            lanes, score = [], 0
            bits = {}
            if n in frames:
                lanes.append("frame"); score += 3; bits["FRAME"] = 1
            if any(t and (t in src) for t in toks):
                lanes.append("literal"); score += 2; bits["LITERAL"] = 1
            if n in recent:
                lanes.append("recent"); score += 1; bits["RECENT"] = 1
            if not src.strip().startswith(("def ", "class ", "import ", "from ", "#", '"""')) and "=" in src or "return" in src or "(" in src:
                lanes.append("executed"); score += 1
            if lanes:
                f = Finding(rel, n, src, lanes, score); f.bits.update(bits); findings.append(f)
    findings.sort(key=lambda f: (-f.score, f.file, f.line))
    return findings, notes


# ------------------------------------------------------------------ WHERE, the spectrum lane
_DUMP = r'''
import json, os, sys
from coverage import CoverageData
d = CoverageData(basename=sys.argv[1]); d.read()
root = os.path.realpath(sys.argv[2]); out = {}
for f in d.measured_files():
    rf = os.path.realpath(f)
    if not rf.startswith(root + os.sep): continue
    ctx = d.contexts_by_lineno(f)
    out[os.path.relpath(rf, root)] = {str(k): sorted({(c.rsplit("|", 1)[0] or "<import>") for c in v}) for k, v in ctx.items()}
print(json.dumps(out))
'''


def _package_dirs(root: str) -> list[str]:
    out = []
    for base in (Path(root), Path(root, "src")):
        if not base.is_dir():
            continue
        for p in sorted(base.iterdir()):
            if p.is_dir() and (p / "__init__.py").exists() and p.name not in ("tests", "test"):
                out.append(str(p.relative_to(root)))
    return out or ["."]


def spectrum(root: str, python: str, failing: list[str], extra_args: list | None = None) -> dict:
    """Ochiai over per-test coverage: {(rel, line): (score, ef, ep)}. Files by their MAX line score, never
    by how many lines they execute — fluidfix's count-based file ranking put a real guilty file 7th of 14
    (research/localisation-2026-09-19). Per-test contexts need COVERAGE_CORE=ctrace on Python 3.12+ with
    coverage 7.16: the default sysmon core credits each line only to the FIRST test that ran it."""
    import math
    with tempfile.TemporaryDirectory() as td:
        cov = str(Path(td) / ".coverage")
        env = {**os.environ, **_NO_PYC, "COVERAGE_FILE": cov, "COVERAGE_CORE": "ctrace"}
        cmd = [python, "-B", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-W", "default",
               "--tb=no", "-rfE", "--cov-context=test", "--cov-report="] + \
              [f"--cov={d}" for d in _package_dirs(root)] + list(extra_args or [])
        subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600, env=env)
        r = subprocess.run([python, "-c", _DUMP, cov, root], capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not r.stdout.strip():
            return {}
        lines = json.loads(r.stdout)
    fail = set(failing); F = len(fail); out = {}
    for rel, by in lines.items():
        if rel.startswith(("tests/", "test/")) or rel.endswith("conftest.py"):
            continue
        for ln, tests in by.items():
            ts = set(tests) - {"<import>"}; ef = len(ts & fail); ep = len(ts - fail)
            if ef:
                out[(rel, int(ln))] = (ef / math.sqrt(F * (ef + ep)), ef, ep)
            elif "<import>" in tests and not ts:
                out[(rel, int(ln))] = (0.0, 0, 0)                     # ran only at import: IMPORT bit
    return out


# ------------------------------------------------------------------ WHEN
def _purge_pyc(tree: Path) -> None:
    for d in tree.rglob("__pycache__"):
        for f in d.glob("*.pyc"):
            f.unlink(missing_ok=True)


_NO_PYC = {"PYTHONDONTWRITEBYTECODE": "1"}


def _run_tests_at(worktree: Path, python: str, ids: list[str], timeout: int = 120) -> str:
    """green | red | unknown (the test cannot run at this revision).

    Bytecode is purged first and never written. Measured 2026-09-23: `total * 2` and `total + 2` are the
    same length, two checkouts landed in the same second, and the stale .pyc from the green commit made
    the bad commit pass — bisect blamed the commit on top. The same whole-second trap the C oracle fell
    into with make 3.81."""
    _purge_pyc(worktree)
    r = subprocess.run([python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-W", "default", *ids],
                       cwd=worktree, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **_NO_PYC})
    if r.returncode == 0:
        return "green"
    if "no tests ran" in r.stdout or "not found" in r.stdout or r.returncode in (2, 4, 5):
        return "unknown"
    return "red"


def when(root: str, python: str, ids: list[str], good: str | None = None, lookback: int = 24,
         budget_s: int = 300) -> tuple[dict | None, str | None]:
    """Automated bisect in a throwaway worktree. Returns (result, note)."""
    t0 = time.time()
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None, "no git history — the WHEN lane has no evidence"
    if subprocess.run(["git", "-C", root, "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        note_dirty = "working tree has uncommitted changes; bisect judged committed history only"
    else:
        note_dirty = None
    wt = Path(tempfile.mkdtemp(prefix="fn-bisect-"))
    subprocess.run(["git", "-C", root, "worktree", "add", "-q", "--detach", str(wt), head], capture_output=True)
    runs = 0
    try:
        if _run_tests_at(wt, python, ids) != "red":
            return None, "the failing test is not red at HEAD in a clean worktree (uncommitted change?)"
        runs += 1
        if good is None:
            log = subprocess.run(["git", "-C", root, "log", f"-{lookback + 1}", "--format=%H"],
                                 capture_output=True, text=True).stdout.split()[1:]
            for sha in log:
                if time.time() - t0 > budget_s:
                    return None, f"bisect budget ({budget_s}s) exhausted while searching for a green commit"
                subprocess.run(["git", "-C", str(wt), "checkout", "-q", "--detach", sha], capture_output=True)
                v = _run_tests_at(wt, python, ids); runs += 1
                if v == "green":
                    good = sha; break
                if v == "unknown":
                    return None, f"the failing test cannot run at {sha[:8]} (it did not exist there); pass --good"
            if good is None:
                return None, f"no green commit within the last {lookback}; pass --good <rev>"
        subprocess.run(["git", "-C", str(wt), "bisect", "start", head, good], capture_output=True, check=True)
        script = (f'find . -name __pycache__ -prune -exec rm -rf {{}} + ; '
                  f'PYTHONDONTWRITEBYTECODE=1 {python} -B -m pytest -q -p no:cacheprovider --no-header -W default {" ".join(ids)}')
        r = subprocess.run(["git", "-C", str(wt), "bisect", "run", "sh", "-c", script],
                           capture_output=True, text=True, timeout=budget_s)
        m = re.search(r"([0-9a-f]{40}) is the first bad commit", r.stdout + r.stderr)
        runs += len(re.findall(r"Bisecting:", r.stdout))
        if not m:
            return None, "bisect did not converge"
        bad = m.group(1)
        subject = subprocess.run(["git", "-C", root, "log", "-1", "--format=%s", bad], capture_output=True, text=True).stdout.strip()
        diff = subprocess.run(["git", "-C", root, "show", "--unified=0", "--format=", bad], capture_output=True, text=True).stdout
        hunks, cur = {}, None
        for l in diff.splitlines():
            if l.startswith("+++ b/"):
                cur = l[6:]
            elif l.startswith("@@") and cur:
                mm = re.search(r"\+(\d+)(?:,(\d+))?", l)
                if mm:
                    s = int(mm.group(1)); c = int(mm.group(2) or 1)
                    hunks.setdefault(cur, []).append((s, max(s, s + c - 1)))
        res = {"commit": bad, "subject": subject, "good": good, "runs": runs, "hunks": hunks}
        return res, note_dirty
    except subprocess.TimeoutExpired:
        return None, f"bisect budget ({budget_s}s) exhausted"
    finally:
        subprocess.run(["git", "-C", str(wt), "bisect", "reset"], capture_output=True)
        subprocess.run(["git", "-C", root, "worktree", "remove", "--force", str(wt)], capture_output=True)


# ------------------------------------------------------------------ WHY
_TRACER = r'''
import json, sys, os, importlib, runpy
root, test_id, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
path, name = test_id.split("::", 1)
mod = importlib.import_module(path[:-3].replace("/", ".").replace("\\", "."))
fn = getattr(mod, name.split("[")[0])
trace = []
def tr(frame, event, arg):
    f = frame.f_code.co_filename
    if not f.startswith(root) or os.sep + "tests" + os.sep in f or f.endswith("conftest.py"):
        return tr
    if event == "line":
        rel = os.path.relpath(f, root)
        loc = {}
        for k, v in frame.f_locals.items():
            if k.startswith("__"): continue
            try: loc[k] = repr(v)[:60]
            except Exception: loc[k] = "?"
        trace.append([rel, frame.f_lineno, loc])
    return tr
sys.settrace(tr)
try:
    fn()
    ok = True
except BaseException:
    ok = False
finally:
    sys.settrace(None)
json.dump({"ok": ok, "trace": trace}, open(out_path, "w"))
'''


def _sibling_test(root: str, failing: list[str], target: str) -> str | None:
    """A passing test that calls the same function the failing assertion called."""
    tests_dir = Path(root)
    for p in sorted(tests_dir.rglob("test_*.py")):
        rel = str(p.relative_to(tests_dir)).replace("\\", "/")
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                tid = f"{rel}::{node.name}"
                if tid in failing:
                    continue
                if any(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == target
                       for n in ast.walk(node)):
                    return tid
    return None


def why(root: str, python: str, out: str, failing: list[str]) -> dict:
    calls = [c for c in _assertion_tokens(out) if re.match(r"^[A-Za-z_]\w*$", c)]
    m = re.search(r"where .* = ([A-Za-z_]\w*)\(", out) or re.search(r"assert ([A-Za-z_]\w*)\(", out)
    target = m.group(1) if m else (calls[0] if calls else None)
    if not target:
        return {"note": "the assertion names no function to trace — the WHY lane has no evidence"}
    sib = _sibling_test(root, failing, target)
    traces = {}
    with tempfile.TemporaryDirectory() as td:
        for tag, tid in (("fail", failing[0]),) + ((("pass", sib),) if sib else ()):
            outp = Path(td) / f"{tag}.json"
            r = subprocess.run([python, "-B", "-c", _TRACER, str(Path(root).resolve()), tid, str(outp)],
                               capture_output=True, text=True, timeout=120, cwd=root, env={**os.environ, **_NO_PYC})
            if not outp.exists():
                return {"target": target, "sibling": sib, "note": f"could not trace {tid}: {r.stderr.strip()[-160:]}"}
            traces[tag] = json.load(open(outp))
    a = traces["fail"]["trace"]
    if not a:
        return {"target": target, "sibling": sib, "note": "the failing test executed no source line"}
    # where the failing run's path ENDED in source: for a fault of omission — the fix adds code the old
    # file never ran — this is the only line-level evidence there is, and it needs no sibling
    last = {"file": a[-1][0], "line": a[-1][1]}
    if not sib:
        return {"target": target, "last_executed": last,
                "note": f"no passing test calls {target}() — the WHY lane has no divergence to show"}
    b = traces["pass"]["trace"]
    for i, (fa, pb) in enumerate(zip(a, b)):
        if (fa[0], fa[1]) != (pb[0], pb[1]):
            return {"target": target, "sibling": sib, "kind": "control-flow", "last_executed": last,
                    "diverges_at": {"file": fa[0], "line": fa[1]},
                    "detail": f"the passing run went to {pb[0]}:{pb[1]} here"}
    # same path: the first local whose value differs, past the point where the inputs are read
    for i, (fa, pb) in enumerate(zip(a, b)):
        diff = {k: (fa[2][k], pb[2][k]) for k in fa[2] if k in pb[2] and fa[2][k] != pb[2][k]}
        if diff and i > 0:
            k = next(iter(diff))
            return {"target": target, "sibling": sib, "kind": "same path, values differ from the inputs on",
                    "last_executed": last, "diverges_at": {"file": fa[0], "line": fa[1]},
                    "detail": f"first differing local {k}: failing {diff[k][0]} vs passing {diff[k][1]}"}
    if len(a) != len(b):
        fa = a[min(len(a), len(b)) - 1] if len(a) > len(b) else b[len(a) - 1]
        return {"target": target, "sibling": sib, "kind": "control-flow", "last_executed": last,
                "diverges_at": {"file": fa[0], "line": fa[1]},
                "detail": "one run ended here and the other continued"}
    return {"target": target, "sibling": sib, "last_executed": last,
            "note": "identical paths and locals — the two tests do not distinguish the code"}


# ------------------------------------------------------------------ all three
def locate(root: str, python: str = sys.executable, good: str | None = None, bisect: bool = True,
           trace: bool = True, top_files: int = 3, extra_args: list | None = None) -> Located:
    """extra_args are passed to every pytest run (e.g. -W default, --deselect id): what an old revision
    needs to collect and to be green apart from the bug under study."""
    t0 = time.time()
    root = str(Path(root).resolve())
    L = Located()
    o = Oracle(root, python=python)
    if extra_args:
        o.extra_args = list(o.extra_args) + list(extra_args)
    try:
        fails, out = o.failing_output()
    except Exception as e:
        L.status = "harness"; L.notes.append(str(e)[:200]); return L
    if not fails:
        return L
    L.status = "red"
    L.failing = _failing_ids(out)
    L.where, notes = where(o, out, top_files)
    L.notes += notes
    try:
        sp = spectrum(root, python, L.failing, o.extra_args)
    except Exception as e:
        sp, _ = {}, L.notes.append(f"spectrum lane could not run ({type(e).__name__})")
    if sp:
        best = max(v[0] for v in sp.values())
        seen = {(f.file, f.line): f for f in L.where}
        F = len(L.failing)
        for (rel, ln), (score, ef, ep) in sp.items():
            if (rel, ln) in seen:
                seen[(rel, ln)].bits.update({"EF_ALL": int(ef == F and F > 0), "EP_NONE": int(ep == 0 and ef > 0),
                                             "IMPORT": int(ef == 0 and ep == 0)})
            if ef == 0:
                continue
            tag = f"spectrum {score:.2f} (ef {ef}, ep {ep})"
            if (rel, ln) in seen:
                seen[(rel, ln)].lanes.append(tag); seen[(rel, ln)].score += 3 if score >= best - 1e-9 else 1
            elif score >= best - 1e-9:
                try:
                    src = Path(root, rel).read_text(encoding="utf-8").split("\n")[ln - 1]
                except Exception:
                    src = ""
                if src.strip() and not src.strip().startswith(("def ", "class ", "import ", "from ", "#")):
                    f = Finding(rel, ln, src, ["executed", tag], 3)
                    f.bits.update({"EF_ALL": int(ef == F), "EP_NONE": int(ep == 0)}); L.where.append(f)
    else:
        L.notes.append("spectrum lane: no per-test coverage (pytest-cov missing, or nothing measured)")
    if bisect and L.failing:
        w, note = when(root, python, L.failing, good=good)
        L.when = w
        if note:
            L.notes.append(note)
        if w:
            for f in L.where:
                for s, e in w["hunks"].get(f.file, []):
                    if s <= f.line <= e:
                        f.lanes.append(f"when-commit {w['commit'][:7]}"); f.score += 2; f.bits["BISECT"] = 1
    if trace and L.failing:
        L.why = why(root, python, out, L.failing)
        le = (L.why or {}).get("last_executed")
        if le:
            hit = next((f for f in L.where if f.file == le["file"] and f.line == le["line"]), None)
            if hit:
                hit.lanes.append("last-executed"); hit.score += 2
            else:
                try:
                    src = Path(root, le["file"]).read_text(encoding="utf-8").split("\n")[le["line"] - 1]
                except Exception:
                    src = ""
                L.where.append(Finding(le["file"], le["line"], src, ["last-executed"], 2))
        d = (L.why or {}).get("diverges_at")
        if d:
            hit = next((f for f in L.where if f.file == d["file"] and f.line == d["line"]), None)
            if hit:
                hit.lanes.append("why-divergence"); hit.score += 2; hit.bits["DIVERGE"] = 1
            else:
                f = Finding(d["file"], d["line"], "", ["why-divergence"], 2); f.bits["DIVERGE"] = 1; L.where.append(f)
    L.where.sort(key=lambda f: (-f.score, -len(f.lanes), f.file, f.line))
    L.seconds = round(time.time() - t0, 2)
    try:
        Path(root, ".fluidfix").mkdir(exist_ok=True)
        Path(root, ".fluidfix", "locate.json").write_text(json.dumps(
            {"status": L.status, "failing": L.failing, "where": [asdict(f) for f in L.where[:8]],
             "when": L.when, "why": L.why, "notes": L.notes, "seconds": L.seconds,
             "at": time.strftime("%H:%M:%S")}, indent=1))
    except OSError:
        pass
    return L
