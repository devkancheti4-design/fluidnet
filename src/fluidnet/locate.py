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

from .cause import cause as _cause, word as _word
from .omission import omission as _omission, word as _oword, BITS as _OBITS
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
    score: int = 0                      # the old hand-weight sum; kept only so the law can be compared to it
    rank: int = 0                       # THE CAUSE LAW's priority, 0..15, from the bits below; 0 = vetoed
    ochiai: float = 0.0                 # tie-break within a law rank, never a rank on its own
    # the eight measured bits a ranking LAW would take (fluidfix/docs/laws/CAUSE_LAW_PROMPT.md): logged
    # for every candidate so a law can be judged on held-out real bugs without a rerun
    bits: dict = field(default_factory=lambda: {k: 0 for k in
                       ("FRAME", "LITERAL", "RECENT", "BISECT", "DIVERGE", "EF_ALL", "EP_NONE", "IMPORT")})


@dataclass
class Located:
    status: str = "green"                       # green | red | harness
    failing: list = field(default_factory=list)   # the failure this verdict is for (the suite stops at the first)
    failing_all: list = field(default_factory=list)   # every failing test in the whole suite
    where: list = field(default_factory=list)   # Findings, best first
    when: dict | None = None
    why: dict | None = None
    notes: list = field(default_factory=list)
    seconds: float = 0.0
    vetoed: int = 0                     # candidates the law ruled cannot be the cause (R0)
    law_ranked: bool = True             # False when EF_ALL could not be measured, so the law could not rule
    omission: list = field(default_factory=list)   # Findings ranked by the OMISSION law: where missing code belongs
    raised: bool = False                # the failure was an exception, not a false assertion

    def render(self) -> str:
        if self.status == "green":
            return "suite green — nothing to locate"
        if self.status == "harness":
            return "cannot judge: " + "; ".join(self.notes)
        n_all = max(len(self.failing_all), len(self.failing))
        head = f"RED — {n_all} failing"
        if n_all > len(self.failing):
            head += (f" ({', '.join(self.failing_all[:4])}{' …' if n_all > 4 else ''}); this verdict is for the "
                     f"first: {self.failing[0]} — locate again after fixing it, the others may be unrelated")
        else:
            head += f": {', '.join(self.failing[:3])}" + (" …" if len(self.failing) > 3 else "")
        out = [head, "root cause, by lanes of evidence agreeing:"]
        for i, f in enumerate(self.where[:5], 1):
            out.append(f"  {i}. {f.file}:{f.line}   {f.source.strip()[:60]}")
            out.append(f"       cause {f.rank:>2}/15  [{', '.join(f.lanes)}]")
        if self.vetoed:
            out.append(f"  ({self.vetoed} candidate{'s' if self.vetoed != 1 else ''} vetoed by the law: not run by "
                       f"every failing test, not import-time)")
        if not self.law_ranked:
            out.append("  (the law could not rule — EF_ALL is unmeasured without per-test coverage; order is the old sum)")
        if self.omission:
            out.append("if the fix is code that is MISSING — where it belongs, by the omission law:")
            for i, f in enumerate(self.omission[:3], 1):
                out.append(f"  {i}. {f.file}:{f.line}   {f.source.strip()[:60]}")
                out.append(f"       omission {f.rank:>2}/15  [{', '.join(f.lanes)}]")
        if self.when and self.when.get("commit"):
            w = self.when
            out.append(f"when: {w['commit'][:8]} \"{w['subject']}\" introduced the failure "
                       f"(bisect, {w['runs']} test runs)")
        elif self.when and self.when.get("older_than"):
            o = self.when["older_than"]
            out.append(f"when: at least as old as {o['commit'][:8]} ({o['date']}, HEAD~{o['distance']}) — red at every "
                       f"revision the failing test can run at ({self.when['runs']} test runs)")
        elif self.when and self.when.get("candidates"):
            c = self.when["candidates"]
            out.append(f"when: one of {len(c)} commits ({c[0][:8]} … {c[-1][:8]}) — the test cannot run at them "
                       f"(bisect, {self.when['runs']} test runs)")
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


def project_python(root: str) -> str:
    """The interpreter that owns the project's dependencies: its own virtualenv when there is one
    (`.venv` or `venv` beside the code), else the interpreter running fluidnet. Every command that runs a
    project's tests defaults to this — running an enterprise suite with fluidnet's own interpreter is the
    first thing that goes wrong on a real project (mealie, 2026-09-24)."""
    for rel in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe", "venv/Scripts/python.exe"):
        cand = Path(root, rel)
        if cand.exists():
            # NOT resolved: a uv/venv interpreter is a symlink to the base Python, and following it loses
            # the venv's site-packages (mealie's .venv resolved to Homebrew's python3.14 with no pytest)
            return str(cand.absolute())
    return sys.executable


def _src_line(root: str, rel: str, ln: int) -> str:
    try:
        return Path(root, rel).read_text(encoding="utf-8").split("\n")[ln - 1]
    except Exception:
        return ""


def _line_bits(root: str, out: str, rel: str, ln: int, src: str, cache: dict) -> dict:
    """The body's measurement of one line: FRAME, LITERAL, RECENT. Per-file work is cached."""
    if rel not in cache:
        cache[rel] = (_frames_in(out, rel), _recent_lines(root, rel))
    frames, recent = cache[rel]
    bits = {}
    if ln in frames:
        bits["FRAME"] = 1
    if any(t and (t in src) for t in cache["toks"]):
        bits["LITERAL"] = 1
    if ln in recent:
        bits["RECENT"] = 1
    return bits


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
        # ONE run of the whole suite: the failures (-rfE), their long tracebacks (the WHERE bits), and the
        # per-test coverage. It used to be four runs — -x for the first failure, two under coverage for the
        # file ranking, one for the spectrum — which on a 140 s suite (mealie) was a quarter of an hour.
        cmd = [python, "-B", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-W", "default",
               "--tb=long", "-rfE", "--cov-context=test", "--cov-report="] + \
              [f"--cov={d}" for d in _package_dirs(root)] + list(extra_args or [])
        run = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=1800, env=env)
        spectrum.last_output = run.stdout + run.stderr
        spectrum.last_rc = run.returncode
        spectrum.last_failing = _failing_ids(run.stdout)          # every failure in the whole suite
        spectrum.no_cov = run.returncode == 4 and "--cov" in (run.stdout + run.stderr)
        r = subprocess.run([python, "-c", _DUMP, cov, root], capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not r.stdout.strip():
            return {}
        lines = json.loads(r.stdout)
    fail = set(failing); F = max(len(fail), 1); out = {}
    spectrum.last_contexts = {(rel, int(ln)): tests for rel, by in lines.items()
                              if not (rel.startswith(("tests/", "test/")) or rel.endswith("conftest.py"))
                              for ln, tests in by.items()}
    for rel, by in lines.items():
        if rel.startswith(("tests/", "test/")) or rel.endswith("conftest.py"):
            continue
        for ln, tests in by.items():
            ts = set(tests) - {"<import>"}; ef = len(ts & fail); ep = len(ts - fail)
            if ef:
                out[(rel, int(ln))] = (ef / math.sqrt(F * (ef + ep)), ef, ep)
            elif ep:
                out[(rel, int(ln))] = (0.0, 0, ep)                    # PASSONLY: where the failing run should have gone
            elif "<import>" in tests and not ts:
                out[(rel, int(ln))] = (0.0, 0, 0)                     # ran only at import: IMPORT bit
    return out


def spectrum_for(sp: dict, failing: list[str]) -> dict:
    """The spectrum was measured with no failing set (one run for everything); score it for the test(s)
    being judged. `sp` values are (score, ef, ep) with the raw per-line test sets kept on the side."""
    import math
    raw = getattr(spectrum, "last_contexts", None)
    if raw is None:
        return sp
    fail = set(failing); F = len(fail); out = {}
    for (rel, ln), tests in raw.items():
        ts = set(tests) - {"<import>"}; ef = len(ts & fail); ep = len(ts - fail)
        if ef:
            out[(rel, ln)] = (ef / math.sqrt(F * (ef + ep)), ef, ep)
        elif ep:
            out[(rel, ln)] = (0.0, 0, ep)
        elif "<import>" in tests and not ts:
            out[(rel, ln)] = (0.0, 0, 0)
    return out


def _first_failure(out: str, tid: str) -> str:
    """The long-traceback section of one failing test, plus the summary lines: the WHERE bits (frames,
    literals) are measured from the failure being judged, not from every failure in the suite."""
    name = tid.split("::")[-1].split("[")[0]
    heads = [m.start() for m in re.finditer(r"^_{3,} .+ _{3,}$", out, re.M)]
    mine = [h for h in heads if name in out[h:out.find("\n", h)]]
    if not mine:
        return out
    start = mine[0]
    later = [h for h in heads if h > start]
    end = later[0] if later else len(out)
    summary = out[out.rfind("short test summary info"):] if "short test summary info" in out else ""
    return out[start:end] + "\n" + summary


class HarnessError(Exception):
    pass


# ------------------------------------------------------------------ WHEN
def _purge_pyc(tree: Path) -> None:
    for d in tree.rglob("__pycache__"):
        for f in d.glob("*.pyc"):
            f.unlink(missing_ok=True)


_NO_PYC = {"PYTHONDONTWRITEBYTECODE": "1"}


_STEP = r'''
# one bisect step. argv: overlay.json python timeout extra_args_json ids...
# exit 0 green, 1 red, 125 the test cannot run here (a SKIP to git bisect, never a verdict)
import ast, json, os, shutil, subprocess, sys
ov = json.load(open(sys.argv[1])); py, timeout = sys.argv[2], int(sys.argv[3]); extra = json.loads(sys.argv[4]); ids = sys.argv[5:]
tree = os.getcwd()
def purge():
    for d, dirs, _ in os.walk(tree):
        for x in list(dirs):
            if x == "__pycache__": shutil.rmtree(os.path.join(d, x), ignore_errors=True); dirs.remove(x)
def restore():
    subprocess.run(["git", "checkout", "-q", "--", "."], capture_output=True)
    for rel in ov:
        if subprocess.run(["git", "ls-files", "--error-unmatch", rel], capture_output=True).returncode != 0:
            try: os.remove(os.path.join(tree, rel))
            except OSError: pass
def wanted(rel):
    names = set()
    for i in ids:
        f, _, rest = i.partition("::")
        if f == rel and rest: names.add(rest.split("::")[0].split("[")[0])
    return names
def apply(minimal):
    for rel, content in ov.items():
        dst = os.path.join(tree, rel); os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        if not (minimal and os.path.exists(dst)):
            open(dst, "w", encoding="utf-8").write(content); continue
        # the revision keeps ITS OWN file; only the new test functions (and classes) are appended, so a
        # modern import at the top of the test file cannot make an old revision uncollectable
        old = open(dst, encoding="utf-8").read()
        try: mod, oldmod = ast.parse(content), ast.parse(old)
        except SyntaxError: open(dst, "w", encoding="utf-8").write(content); continue
        def names(n):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): return {n.name}
            if isinstance(n, ast.Assign): return {t.id for t in n.targets if isinstance(t, ast.Name)}
            if isinstance(n, (ast.Import, ast.ImportFrom)): return {(a.asname or a.name).split(".")[0] for a in n.names}
            return set()
        have = set().union(*(names(n) for n in oldmod.body)) if oldmod.body else set()
        # the failing tests travel with what they reference, transitively, and nothing else: a whole file's
        # worth of new module-level code would break collection at a revision that lacks one of its names
        # (measured on click: carrying everything shrank the reach from 2014 to 2026)
        by_name = {}
        for node in mod.body:
            for nm in names(node): by_name.setdefault(nm, node)
        want = wanted(rel); need, chosen, queue = set(want), [], list(want)
        while queue:
            nm = queue.pop(); node = by_name.get(nm)
            if node is None or (nm in have and nm not in want) or any(node is c for c in chosen): continue
            chosen.append(node)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id not in need:
                    need.add(sub.id); queue.append(sub.id)
        lines = content.split("\n"); segs = []
        for node in sorted(chosen, key=lambda n: n.lineno):
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            seg = "\n".join(lines[start - 1:node.end_lineno])
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign)):
                seg = "try:\n    " + seg.replace("\n", "\n    ") + "\nexcept Exception:\n    pass"
            segs.append(seg)
        open(dst, "w", encoding="utf-8").write(old.rstrip("\n") + "\n\n\n" + "\n\n\n".join(segs) + "\n")
import re
def run(fallback=False):
    purge()
    pp = [os.path.join(tree, "src")] if os.path.isdir(os.path.join(tree, "src")) else []
    pp += [tree] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join(pp)}
    try:
        r = subprocess.run([py, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-W", "default", *extra, *ids],
                           capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 125
    # the last run's output, for the record beside the overlay (the step is judged by exit code only)
    with open(os.path.join(os.path.dirname(sys.argv[1]), "last_run.txt"), "a") as fh:
        fh.write(f"=== {tree} rc {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-800:]}\n")
    if r.returncode == 0: return 0
    if r.returncode == 1 and "no tests ran" not in r.stdout and "not found" not in r.stdout:
        # with only the test functions carried, an error raised IN THE TEST FILE (a name or attribute the
        # revision does not have) means the test could not be evaluated here; a failure raised in the code
        # under test is still a verdict
        if fallback and re.search(r"^(?:tests?/|.*test_)\S*\.py:\d+: (?:NameError|ImportError|ModuleNotFoundError|AttributeError|TypeError)\b", r.stdout, re.M):
            return 125
        return 1
    return 125
apply(False); rc = run()
if rc == 125 and ov:
    restore(); apply(True); rc = run(fallback=True)
restore(); sys.exit(rc)
'''


def _apply_overlay(tree: Path, overlay: dict | None) -> None:
    """A regression test arrives WITH the fix; to use it as a bisect oracle further back it has to be
    carried into each revision. Only test files travel — never the fix."""
    for rel, content in (overlay or {}).items():
        dst = tree / rel; dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(content, encoding="utf-8")


def _step_at(worktree: Path, python: str, ids: list[str], stage: Path, timeout: int = 120,
             extra_args: list | None = None) -> str:
    """green | red | unknown at the revision checked out in `worktree`, through the same step script git
    bisect runs, so the probe and the bisect cannot disagree about what "cannot run" means."""
    r = subprocess.run([sys.executable, "-B", str(stage / "_step.py"), str(stage / "overlay.json"), python, str(timeout),
                        json.dumps(extra_args or []), *ids], cwd=worktree, capture_output=True, text=True,
                       timeout=timeout * 2 + 30)
    return {0: "green", 1: "red"}.get(r.returncode, "unknown")


def _stage(overlay: dict | None) -> Path:
    stage = Path(tempfile.mkdtemp(prefix="fn-overlay-"))
    (stage / "_step.py").write_text(_STEP, encoding="utf-8")
    (stage / "overlay.json").write_text(json.dumps(overlay or {}), encoding="utf-8")
    return stage


def _run_tests_at(worktree: Path, python: str, ids: list[str], timeout: int = 120, overlay: dict | None = None,
                  extra_args: list | None = None) -> str:
    """green | red | unknown (the test cannot run at this revision).

    Bytecode is purged first and never written. Measured 2026-09-23: `total * 2` and `total + 2` are the
    same length, two checkouts landed in the same second, and the stale .pyc from the green commit made
    the bad commit pass — bisect blamed the commit on top. The same whole-second trap the C oracle fell
    into with make 3.81."""
    _purge_pyc(worktree); _apply_overlay(worktree, overlay)
    r = subprocess.run([python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-W", "default",
                        *(extra_args or []), *ids],
                       cwd=worktree, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **_NO_PYC, "PYTHONPATH": _own_code_first(worktree)})
    # the throwaway tree is restored afterwards: an overlay that rewrites a TRACKED test file would otherwise
    # make git refuse the next checkout (measured on click, whose regression tests live in existing files)
    subprocess.run(["git", "-C", str(worktree), "checkout", "-q", "--", "."], capture_output=True)
    if r.returncode == 0:
        return "green"
    if "no tests ran" in r.stdout or "not found" in r.stdout or r.returncode in (2, 4, 5):
        return "unknown"
    return "red"


def _own_code_first(tree: Path) -> str:
    """PYTHONPATH that puts THIS checkout's code ahead of the project's editable install. Measured on click
    2026-09-24: without it a bisect worktree at HEAD~300 imported HEAD's src/click through the .pth of the
    venv, so every revision ran the same code and bisect could only ever confirm HEAD. Flat layouts were
    spared by pytest's rootdir insertion; src layouts were silently wrong."""
    parts = [str(tree / "src")] if (tree / "src").is_dir() else []
    parts.append(str(tree))
    if os.environ.get("PYTHONPATH"):
        parts.append(os.environ["PYTHONPATH"])
    return os.pathsep.join(parts)


def when(root: str, python: str, ids: list[str], good: str | None = None, lookback: int = 24,
         budget_s: int = 300, overlay: dict | None = None, extra_args: list | None = None) -> tuple[dict | None, str | None]:
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
        stage = _stage(overlay)
        if _step_at(wt, python, ids, stage, extra_args=extra_args) != "red":
            return None, "the failing test is not red at HEAD in a clean worktree (uncommitted change?)"
        runs += 1
        bad = head
        if good is None:
            def at(dist: int) -> str | None:
                r = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", f"{head}~{dist}"],
                                   capture_output=True, text=True)
                return r.stdout.strip() or None

            def verdict(sha: str) -> str:
                nonlocal runs
                subprocess.run(["git", "-C", str(wt), "checkout", "-q", "--detach", sha], capture_output=True)
                runs += 1
                return _step_at(wt, python, ids, stage, extra_args=extra_args)

            # probe HEAD~1, ~2, ~4, ... along the first-parent line until green, or until the test can no
            # longer run; then bisect the reach boundary. Red at every runnable revision is a verdict too.
            lo, hi, dist, unknown_at = 0, None, 1, None
            depth = int(subprocess.run(["git", "-C", root, "rev-list", "--count", "--first-parent", head],
                                       capture_output=True, text=True).stdout.strip() or 1) - 1
            while dist <= lookback:
                if time.time() - t0 > budget_s:
                    return None, f"bisect budget ({budget_s}s) exhausted while searching for a green commit"
                if dist > depth:
                    if lo >= depth:
                        break                               # the root itself has been judged
                    dist = depth                            # the history ends: the root is the last probe
                sha = at(dist)
                if sha is None:
                    break
                v = verdict(sha)
                if v == "green":
                    good, hi = sha, dist; break
                if v == "unknown":
                    unknown_at = dist; break
                lo, bad = dist, sha
                dist *= 2
            if good is None and unknown_at is not None:
                a, b = lo, unknown_at                       # red at ~a, cannot run at ~b: search between
                while b - a > 1:
                    if time.time() - t0 > budget_s:
                        return None, f"bisect budget ({budget_s}s) exhausted while searching for a green commit"
                    m = (a + b) // 2; sha = at(m); v = verdict(sha)
                    if v == "green":
                        good, hi = sha, m; break
                    if v == "red":
                        a, bad = m, sha
                    else:
                        b = m
            if good is None:
                oldest = at(lo) if lo else head
                when_ = subprocess.run(["git", "-C", root, "log", "-1", "--format=%cs", oldest],
                                       capture_output=True, text=True).stdout.strip()
                reach = ("the test cannot run before that" if unknown_at is not None else
                         "the history begins there" if lo >= depth else f"the lookback of {lookback} ends there")
                return ({"commit": None, "older_than": {"commit": oldest, "date": when_, "distance": lo}, "runs": runs},
                        f"red at every revision the failing test can run at, back to {oldest[:8]} ({when_}, "
                        f"HEAD~{lo}); {reach} — the fault is at least that old")
        subprocess.run(["git", "-C", str(wt), "bisect", "start", bad, good], capture_output=True, check=True)
        # exit 1 = the test failed (bad); 0 = passed (good); 125 = the test could not run at this revision even
        # with the minimal overlay — a SKIP to git bisect, never a verdict.
        r = subprocess.run(["git", "-C", str(wt), "bisect", "run", sys.executable, "-B", str(stage / "_step.py"),
                            str(stage / "overlay.json"), python, "120", json.dumps(extra_args or []), *ids],
                           capture_output=True, text=True, timeout=budget_s)
        m = re.search(r"([0-9a-f]{40}) is the first bad commit", r.stdout + r.stderr)
        runs += len(re.findall(r"Bisecting:", r.stdout))
        if not m:
            mm = re.search(r"could be any of:\n((?:[0-9a-f]{40}\n)+)", r.stdout + r.stderr)
            if mm:
                cands = mm.group(1).split()
                return ({"commit": None, "candidates": cands, "good": good, "runs": runs},
                        f"bisect narrowed the first bad commit to {len(cands)} commits the test cannot run at "
                        f"({cands[0][:8]} … {cands[-1][:8]})")
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
_PLUGIN = r'''
# a pytest plugin: settrace around the test call only, so fixtures, parametrization and class tests all trace
import json, os, sys, threading, pytest
root, out_path = os.environ["FN_TRACE_ROOT"], os.environ["FN_TRACE_OUT"]
trace = []
def tr(frame, event, arg):
    f = frame.f_code.co_filename
    if not f.startswith(root) or os.sep + "tests" + os.sep in f or f.endswith("conftest.py") or os.sep + ".venv" + os.sep in f:
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
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    # threads too: an HTTP test client (Starlette, FastAPI) serves the request on a portal thread, and
    # sys.settrace alone saw "no source line" on a real project (mealie, 2026-09-24)
    sys.settrace(tr); threading.settrace(tr)
    try:
        yield
    finally:
        sys.settrace(None); threading.settrace(None)
        json.dump({"trace": trace}, open(out_path, "w"))
'''


def _trace_test(root: str, python: str, tid: str, out_path: Path) -> str:
    with tempfile.TemporaryDirectory() as pd:
        Path(pd, "fn_trace_plugin.py").write_text(_PLUGIN, encoding="utf-8")
        env = {**os.environ, **_NO_PYC, "FN_TRACE_ROOT": str(Path(root).resolve()), "FN_TRACE_OUT": str(out_path),
               "PYTHONPATH": os.pathsep.join([pd] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))}
        r = subprocess.run([python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "fn_trace_plugin",
                            "--no-header", "-W", "default", tid], capture_output=True, text=True, timeout=300,
                           cwd=root, env=env)
        return (r.stdout + r.stderr).strip()[-200:]


def _neighbour_test(root: str, failing: list[str]) -> str | None:
    """The nearest test in the same file that is not failing — the sibling when the assertion names no function."""
    tid = failing[0]; rel, _, path = tid.partition("::"); parts = path.split("[")[0].split("::")
    try:
        tree = ast.parse(Path(root, rel).read_text(encoding="utf-8"))
    except Exception:
        return None
    # top-level tests, or the methods of the failing test's class
    body, prefix = tree.body, ""
    if len(parts) == 2:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == parts[0]), None)
        if cls is None:
            return None
        body, prefix = cls.body, parts[0] + "::"
    name = parts[-1]
    names = [n.name for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]
    if name not in names:
        return None
    i = names.index(name); bad = {f.split("::", 1)[1].split("[")[0] for f in failing if f.startswith(rel + "::")}
    for d in range(1, len(names)):
        for j in (i - d, i + d):
            if 0 <= j < len(names) and prefix + names[j] not in bad:
                return f"{rel}::{prefix}{names[j]}"
    return None


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
    # no named function: the test itself is traced, against its nearest passing neighbour in the same file
    sib = _sibling_test(root, failing, target) if target else _neighbour_test(root, failing)
    target = target or "the test itself"
    traces = {}
    with tempfile.TemporaryDirectory() as td:
        for tag, tid in (("fail", failing[0]),) + ((("pass", sib),) if sib else ()):
            outp = Path(td) / f"{tag}.json"
            tail = _trace_test(root, python, tid, outp)
            if not outp.exists():
                return {"target": target, "sibling": sib, "note": f"could not trace {tid}: {tail[-160:]}"}
            traces[tag] = json.load(open(outp))
    a = traces["fail"]["trace"]
    executed = {}
    for rel, ln, _loc in a:
        executed.setdefault(rel, set()).add(ln)
    executed = {k: sorted(v) for k, v in executed.items()}
    if not a:
        return {"target": target, "sibling": sib, "executed": executed,
                "note": "the failing test executed no source line"}
    # where the failing run's path ENDED in source: for a fault of omission — the fix adds code the old
    # file never ran — this is the only line-level evidence there is, and it needs no sibling
    last = {"file": a[-1][0], "line": a[-1][1]}
    if not sib:
        return {"target": target, "last_executed": last, "executed": executed,
                "note": f"no passing test calls {target}() — the WHY lane has no divergence to show"
                        if target != "the test itself" else "no passing neighbour test — the WHY lane has no divergence to show"}
    b = traces["pass"]["trace"]
    for i, (fa, pb) in enumerate(zip(a, b)):
        if (fa[0], fa[1]) != (pb[0], pb[1]):
            return {"target": target, "sibling": sib, "kind": "control-flow", "last_executed": last, "executed": executed,
                    "diverges_at": {"file": fa[0], "line": fa[1]},
                    "detail": f"the passing run went to {pb[0]}:{pb[1]} here"}
    # same path: the first local whose value differs, past the point where the inputs are read
    for i, (fa, pb) in enumerate(zip(a, b)):
        diff = {k: (fa[2][k], pb[2][k]) for k in fa[2] if k in pb[2] and fa[2][k] != pb[2][k]}
        if diff and i > 0:
            k = next(iter(diff))
            return {"target": target, "sibling": sib, "kind": "same path, values differ from the inputs on",
                    "last_executed": last, "executed": executed, "diverges_at": {"file": fa[0], "line": fa[1]},
                    "detail": f"first differing local {k}: failing {diff[k][0]} vs passing {diff[k][1]}"}
    if len(a) != len(b):
        fa = a[min(len(a), len(b)) - 1] if len(a) > len(b) else b[len(a) - 1]
        return {"target": target, "sibling": sib, "kind": "control-flow", "last_executed": last, "executed": executed,
                "diverges_at": {"file": fa[0], "line": fa[1]},
                "detail": "one run ended here and the other continued"}
    return {"target": target, "sibling": sib, "last_executed": last, "executed": executed,
            "note": "identical paths and locals — the two tests do not distinguish the code"}


# ------------------------------------------------------------------ all three
def locate(root: str, python: str = sys.executable, good: str | None = None, bisect: bool = True,
           trace: bool = True, top_files: int = 3, extra_args: list | None = None,
           progress=None, overlay: dict | None = None, lookback: int = 24, budget_s: int = 300) -> Located:
    """extra_args are passed to every pytest run (e.g. -W default, --deselect id): what an old revision
    needs to collect and to be green apart from the bug under study."""
    t0 = time.time()
    root = str(Path(root).resolve())
    L = Located()
    o = Oracle(root, python=python)
    if extra_args:
        o.extra_args = list(o.extra_args) + list(extra_args)
    tell = progress or (lambda stage, detail="": None)
    tell("suite", "one run of the whole suite, with per-test coverage")
    sp, out = {}, ""
    try:
        sp = spectrum(root, python, [], o.extra_args)
        out = getattr(spectrum, "last_output", "")
        if "No module named pytest" in out:
            raise HarnessError(out)
    except HarnessError:
        L.status = "harness"
        L.notes.append("the interpreter running your suite has no pytest, so no test has been judged.\n"
                       f"  interpreter: {python}\n  fix: point fluidnet at your project's interpreter --\n"
                       "       fluidnet locate . --python /path/to/venv/bin/python\n"
                       "  (or install pytest into the interpreter above)"); return L
    except Exception as e:
        L.notes.append(f"spectrum lane could not run ({type(e).__name__})")
    failing_all = list(getattr(spectrum, "last_failing", []) or [])
    if getattr(spectrum, "no_cov", False) or (not sp and not failing_all and getattr(spectrum, "last_rc", 0) not in (0, 1, 5)):
        # coverage is unavailable here (pytest-cov missing, or the run could not collect): the old path,
        # which runs the suite again without it and says why the law cannot rule
        sp = {}
        tell("suite", "running the suite without coverage")
        try:
            fails, out = o.failing_output()
        except Exception as e:
            L.status = "harness"; L.notes.append(str(e).replace("fluidfix ...", "fluidnet locate .")
                                                 .replace("point fluidfix at", "point fluidnet at")); return L
        if not fails:
            return L
        failing_all = _failing_ids(out)
    if not failing_all:
        return L
    L.status = "red"
    L.failing = failing_all[:1]
    L.failing_all = failing_all
    out = _first_failure(out, L.failing[0])
    if sp:
        # every line the failing test executed enters the pool below, each with its bits measured; the
        # candidate-file packet of the old path is only needed when there is no coverage to measure from
        sp = spectrum_for(sp, L.failing)
    else:
        tell("where", "reading the failure and the lines it executed")
        L.where, notes = where(o, out, top_files)
        L.notes += notes
        tell("candidates", " ".join(dict.fromkeys(f.file for f in L.where)))
    if sp:
        best = max(v[0] for v in sp.values())
        seen = {(f.file, f.line): f for f in L.where}
        cache: dict = {"toks": _assertion_tokens(out)}
        F = len(L.failing)
        for (rel, ln), (score, ef, ep) in sp.items():
            if (rel, ln) in seen:
                seen[(rel, ln)].bits.update({"EF_ALL": int(ef == F and F > 0), "EP_NONE": int(ep == 0 and ef > 0),
                                             "IMPORT": int(ef == 0 and ep == 0)})
            if ef == 0 and ep == 0 and (rel, ln) not in seen:
                # ran only at import: a module-level constant or table the failing test never "executes" but
                # depends on. The law keeps IMPORT lines (R0), so they must be in the pool — the single-run
                # refactor dropped them and the "data, not code" adversarial case went from rank 2.5 to a miss
                src = _src_line(root, rel, ln)
                if src.strip() and not src.strip().startswith(("def ", "class ", "import ", "from ", "#", '"""', "@")):
                    f = Finding(rel, ln, src, ["import-time"], 0)
                    f.bits.update({"EF_ALL": 0, "EP_NONE": 0, "IMPORT": 1})
                    f.bits.update(_line_bits(root, out, rel, ln, src, cache))
                    f.lanes += [b.lower() for b in ("FRAME", "LITERAL", "RECENT") if f.bits.get(b)]; L.where.append(f)
                continue
            if ef == 0:
                continue
            tag = f"spectrum {score:.2f} (ef {ef}, ep {ep})"
            if (rel, ln) in seen:
                seen[(rel, ln)].ochiai = score
                seen[(rel, ln)].lanes.append(tag); seen[(rel, ln)].score += 3 if score >= best - 1e-9 else 1
            elif score >= best - 1e-9 or ef == F:
                src = _src_line(root, rel, ln)
                if src.strip() and not src.strip().startswith(("def ", "class ", "import ", "from ", "#", '"""')):
                    f = Finding(rel, ln, src, ["executed", tag], 3 if score >= best - 1e-9 else 1); f.ochiai = score
                    f.bits.update({"EF_ALL": int(ef == F), "EP_NONE": int(ep == 0)})
                    f.bits.update(_line_bits(root, out, rel, ln, src, cache))
                    f.lanes += [b.lower() for b in ("FRAME", "LITERAL", "RECENT") if f.bits.get(b)]; L.where.append(f)
    else:
        L.notes.append("spectrum lane: no per-test coverage (pytest-cov missing, or nothing measured)")
    if bisect and L.failing:
        if overlay is None:
            # the failing tests' files, as they are now, travel into every revision: a test written today is
            # otherwise no oracle before its own commit
            overlay = {}
            for rel in dict.fromkeys(f.split("::")[0] for f in L.failing):
                try:
                    overlay[rel] = Path(root, rel).read_text(encoding="utf-8")
                except OSError:
                    pass
        tell("when", "bisecting in a throwaway worktree")
        w, note = when(root, python, L.failing, good=good, lookback=lookback, budget_s=budget_s,
                       overlay=overlay, extra_args=extra_args)
        L.when = w
        if note:
            L.notes.append(note)
        if w and w.get("commit"):
            for f in L.where:
                for s, e in w["hunks"].get(f.file, []):
                    if s <= f.line <= e:
                        f.lanes.append(f"when-commit {w['commit'][:7]}"); f.score += 2; f.bits["BISECT"] = 1
    if trace and L.failing:
        tell("why", "tracing the failing test against a passing one")
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
    # THE LAW RULES. The body has measured eight bits per candidate; the rank is cause(word). The old
    # hand-weight sum stays in `score` only so the two can be compared on real bugs. `last-executed` is
    # not one of the eight bits — it is proposed as a ninth for the next kernel — so it breaks ties only.
    for f in L.where:
        f.rank = _cause(_word(f.bits))
    L.law_ranked = bool(sp) and any(f.bits.get("EF_ALL") or f.bits.get("IMPORT") for f in L.where)
    if L.law_ranked:
        live = [f for f in L.where if f.rank > 0]
        L._vetoed_list = [f for f in L.where if f.rank == 0]
        L.vetoed = len(L.where) - len(live)
        live.sort(key=lambda f: (-f.rank, -f.ochiai, -int("last-executed" in f.lanes), f.file, f.line))
        L.where = live
    else:
        L.notes.append("the law could not rule: EF_ALL is unmeasured (no per-test coverage); order is the old sum")
        L.where.sort(key=lambda f: (-f.score, -len(f.lanes), f.file, f.line))
    # ---------------------------------------------------------------- THE OMISSION REGIME, beside the cause
    # Candidates are every code line of the candidate files with any reach evidence; the bits are measured
    # from the failing run's own trace, the reversed spectrum, the failure's kind, and the file's syntax.
    try:
        L.raised = bool(re.search(r"^E\s+(?!AssertionError)\w*(?:Error|Exception|Exit)\b", out, re.M))
        executed = (L.why or {}).get("executed") or {}
        ended = (L.why or {}).get("last_executed") or {}
        div = (L.why or {}).get("diverges_at") or {}
        target = (L.why or {}).get("target")
        passonly = {(rel, ln) for (rel, ln), (sc, ef, ep) in (sp or {}).items() if ef == 0 and ep > 0}
        files = list(dict.fromkeys([f.file for f in L.where] + list(executed) + [ended.get("file")]))
        files = [f for f in files if f and f.endswith(".py")][:top_files + 1]
        om = []
        for rel in files:
            try:
                src = Path(root, rel).read_text(encoding="utf-8")
            except OSError:
                continue
            lines = src.split("\n")
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            heads, target_lines = set(), set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.Try,
                                     ast.ExceptHandler, ast.Return, ast.Raise, ast.With, ast.For, ast.While)):
                    heads.add(node.lineno)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and target and node.name == target:
                    target_lines |= set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            frames = _frames_in(out, rel)
            if frames:                                              # the frame that raised: its enclosing def
                fl = max(frames)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and \
                            node.lineno <= fl <= (node.end_lineno or node.lineno):
                        target_lines |= set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            ex = set(executed.get(rel, []))
            recent = _recent_lines(root, rel)
            for n, text in enumerate(lines, 1):
                t = text.strip()
                if not t or t.startswith("#"):
                    continue
                b = {"ENDED": int(ended.get("file") == rel and ended.get("line") == n),
                     "NEXT": int(n not in ex and (n - 1) in ex),
                     "TARGET": int(n in target_lines), "HEAD": int(n in heads),
                     "PASSONLY": int((rel, n) in passonly), "RAISED": int(L.raised),
                     "DIVERGE": int(div.get("file") == rel and div.get("line") == n),
                     "RECENT": int(n in recent)}
                r = _omission(_oword(b))
                if r > 0:
                    f = Finding(rel, n, text, [k for k in _OBITS if b[k]], 0); f.bits = b; f.rank = r; om.append(f)
        om.sort(key=lambda f: (-f.rank, f.file, f.line))
        L.omission = om[:8]
    except Exception as e:
        L.notes.append(f"omission lane could not run ({type(e).__name__}: {str(e)[:80]})")
    L.seconds = round(time.time() - t0, 2)
    tell("done", f"{L.status}")
    try:
        Path(root, ".fluidfix").mkdir(exist_ok=True)
        Path(root, ".fluidfix", "locate.json").write_text(json.dumps(
            {"status": L.status, "failing": L.failing, "failing_all": L.failing_all, "where": [asdict(f) for f in L.where[:8]],
             "vetoed": L.vetoed, "law_ranked": L.law_ranked, "raised": L.raised,
             "omission": [asdict(f) for f in L.omission[:5]],
             # the WALK: every executed line of the top file in file order, each with the law's rank —
             # the path a pixel bug can crawl, honestly, ending where the law ruled
             "walk": ({"file": L.where[0].file, "winner": L.where[0].line,
                       "lines": sorted(({"line": f.line, "rank": f.rank, "lanes": f.lanes, "bits": f.bits}
                                        for f in L.where + getattr(L, "_vetoed_list", []) if f.file == L.where[0].file),
                                       key=lambda d: d["line"])} if L.where else None),
             "when": L.when, "why": L.why, "notes": L.notes, "seconds": L.seconds,
             "at": time.strftime("%H:%M:%S")}, indent=1))
    except OSError:
        pass
    return L
