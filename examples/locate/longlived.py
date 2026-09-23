#!/usr/bin/env python3
"""The bugs that lived longest — real fixes with the maintainers' own regression test, whose guilty lines
git blame dates years before the fix. buggy gets what a developer would have had the day before the fix:
the code, and the failing test. It never sees the fix.

usage: longlived.py <full-clones-dir> <repo> <fix-sha> <born-sha> [more fix-sha born-sha pairs]"""
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from fluidnet.locate import locate
FLUIDFIX = Path("/Users/kanchetidevieswar/neo/fluidfix")
rows = {r["sha"][:8]: r for r in json.load(open(FLUIDFIX / "research/real-history-2026-09-19/tested_fixes.json"))}

def sh(args, cwd=None, t=1800):
    try: return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=t)
    except subprocess.TimeoutExpired: return subprocess.CompletedProcess(args, 124, "", "timeout")

clones, repo = Path(sys.argv[1]), sys.argv[2]
pairs = list(zip(sys.argv[3::2], sys.argv[4::2]))
work = clones / f"ll_{repo}"; shutil.rmtree(work, ignore_errors=True); shutil.copytree(clones / repo, work)
venv = work / ".venv"; sh([os.path.expanduser("~/.local/bin/python3.11"), "-m", "venv", str(venv)]); py = str(venv / "bin/python")
sh([py, "-m", "pip", "-q", "install", "pytest", "pytest-cov", "coverage", "pytest-mock", "commonmark", "markdown-it-py", "pygments", "typing-extensions", "attrs", "python-dateutil", "pytz", "simplejson", "dateparser"])
print(f"env: {sh([py, '-m', 'pip', '-q', 'install', '-e', '.'], cwd=work).returncode == 0 and 'ok' or 'FAILED'}", flush=True)
BASE = ["-W", "default", "--continue-on-collection-errors"]
for fix, born in pairs:
    r = rows[fix[:8]]; sha, rel = r["sha"], r["file"]; t0 = time.time()
    print(f"\n{'=' * 100}\n{repo} {sha[:10]}  {rel}  —  {r['subject'][:70]}\n{'=' * 100}", flush=True)
    sh(["git", "checkout", "-q", "-f", sha + "^"], cwd=work); sh(["git", "clean", "-qfd", "-e", ".venv"], cwd=work)
    for d in work.rglob("__pycache__"): shutil.rmtree(d, ignore_errors=True)
    g0 = sh([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *BASE, "--tb=no"], cwd=work)
    pre = [l.split(" ")[1] for l in g0.stdout.split("\n") if l.startswith("FAILED") and len(l.split(" ")) > 1]
    desel = [x for t in pre for x in ("--deselect", t)]
    print(f"parent revision: {len(pre)} pre-existing failures set aside", flush=True)
    overlay = {}
    for tf in r["tests"]:
        overlay[tf] = sh(["git", "show", f"{sha}:{tf}"], cwd=work).stdout
        (work / tf).write_text(overlay[tf])
    g1 = sh([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *BASE, "--tb=no", *desel], cwd=work)
    if g1.returncode != 1:
        print(f"the fix's test does not turn the parent red (rc {g1.returncode}) — cannot judge", flush=True); continue
    d = sh(["git", "diff", "-U0", sha + "^", sha, "--", rel], cwd=work).stdout
    truth = set()
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+", d, re.M):
        a, b = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        truth |= {a, a + 1} if b == 0 else set(range(a, a + b))
    nlines = len((work / rel).read_text().split("\n"))
    print(f"file: {nlines} lines · the maintainer changed old lines {sorted(truth)[:8]} · bug born {born[:8]}", flush=True)
    # BLIND: no --good hint. The locator must find a green revision itself or say the fault is older than
    # the test's reach.
    L = locate(str(work), python=py, bisect=True, good=None, overlay=overlay, extra_args=BASE + desel,
               lookback=4000, budget_s=1500)
    def mark(f): return "  <== TRUTH" if (f.file == rel and f.line in truth) else ""
    print(f"\nWHERE — by the cause law (top 8 of {len(L.where)} lines every failing test executed; {L.vetoed} vetoed):")
    for i, f in enumerate(L.where[:8], 1): print(f"  {i:>2}. {f.file[-30:]}:{f.line:<5} cause {f.rank:>2}  {f.source.strip()[:50]:50}{mark(f)}")
    tr = next((i + 1 for i, f in enumerate(L.where) if f.file == rel and f.line in truth), None)
    print(f"  truth line's rank under the cause law: {tr}")
    print(f"WHERE MISSING CODE BELONGS — by the omission law (top 5):")
    for i, f in enumerate(L.omission[:5], 1): print(f"  {i:>2}. {f.file[-30:]}:{f.line:<5} omission {f.rank:>2}  {f.source.strip()[:46]:46}{mark(f)}")
    orr = next((i + 1 for i, f in enumerate(L.omission) if f.file == rel and f.line in truth), None)
    print(f"  truth line's rank under the omission law: {orr}   (raised: {L.raised})")
    if L.when and L.when.get("commit"):
        hit = L.when["commit"] == sh(["git", "rev-parse", born], cwd=work).stdout.strip()
        print(f"WHEN — bisect says {L.when['commit'][:8]} \"{L.when['subject'][:50]}\" ({L.when['runs']} runs)  {'== the birth commit' if hit else '(birth commit was ' + born[:8] + ')'}")
    elif L.when and L.when.get("older_than"):
        o = L.when["older_than"]; bd = sh(["git", "log", "-1", "--format=%cs", born], cwd=work).stdout.strip()
        print(f"WHEN — at least as old as {o['commit'][:8]} ({o['date']}, HEAD~{o['distance']}), {L.when['runs']} runs   (truth: born {born[:8]} on {bd})")
    elif L.when and L.when.get("candidates"):
        c = L.when["candidates"]; print(f"WHEN — one of {len(c)} commits the test cannot run at ({c[0][:8]} … {c[-1][:8]})   (truth: {born[:8]})")
    else:
        print(f"WHEN — no verdict")
    y = L.why or {}
    print(f"WHY — {y.get('note') or ('parts at %s:%s — %s' % (y['diverges_at']['file'], y['diverges_at']['line'], y.get('detail', '')))}" if y else "WHY — none")
    for n in L.notes: print(f"note: {n}")
    print(f"{round(time.time() - t0)}s", flush=True)
print("\nLONGLIVED_DONE", flush=True)
