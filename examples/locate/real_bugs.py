#!/usr/bin/env python3
"""The locator on REAL bugs: fixes from git history that ship their own regression test.

usage: real_bugs.py <clones-dir> --repo click [--limit N] [--since 2022] [--python ~/.local/bin/python3.11]

For each fix: check out its parent (the bug present), deselect any test already failing there, bring in
only the fix's TEST files, confirm the suite is red, and locate — with no knowledge of the fix. Ground truth
is the OLD side of the fix's hunks (a pure insertion counts the line before and after). Reported: the
rank of the best ground-truth line and of its file, and — on the same cases — where fluidfix's count-based
file ranking put the file (the baseline that once ranked a real guilty file 7th of 14).

WHEN is off here: a fix commit has no recorded "introducing commit" to grade a bisect against."""
import argparse, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
FLUIDFIX = Path("/Users/kanchetidevieswar/neo/fluidfix")
from fluidnet.locate import locate, _failing_ids          # noqa: E402
from fluidfix.guard import find_candidate_files            # noqa: E402
from fluidfix.oracle import Oracle                         # noqa: E402


def sh(args, cwd=None, env=None, t=1200):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=t)


def truth_lines(work, sha, rel):
    d = sh(["git", "diff", "-U0", sha + "^", sha, "--", rel], cwd=work).stdout
    out = set()
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+", d, re.M):
        a, b = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        out |= {a, a + 1} if b == 0 else set(range(a, a + b))
    return sorted(out)


def mid_rank(findings, pred):
    """1-based rank of the first finding satisfying pred, with ties given the group's mid-rank."""
    if not findings:
        return None
    for i, f in enumerate(findings):
        if pred(f):
            group = [j for j, g in enumerate(findings) if g.score == f.score]
            return round((group[0] + group[-1]) / 2 + 1, 1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clones"); ap.add_argument("--repo", required=True); ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--since", default="2022"); ap.add_argument("--python", default=os.path.expanduser("~/.local/bin/python3.11"))
    ap.add_argument("--only"); a = ap.parse_args()
    rows = [r for r in json.load(open(FLUIDFIX / "research/real-history-2026-09-19/tested_fixes.json"))
            if r["repo"] == a.repo and r["date"][:4] >= a.since]
    if a.only:
        rows = [r for r in rows if any(r["sha"].startswith(w) for w in a.only.split(","))]
    rows.sort(key=lambda r: r["date"], reverse=True)
    print(f"{a.repo}: {len(rows)} fixes from {a.since} that ship their own test", flush=True)
    work = Path(a.clones) / f"loc_{a.repo}"
    shutil.rmtree(work, ignore_errors=True); shutil.copytree(Path(a.clones) / a.repo, work)
    venv = work / ".venv"; sh([a.python, "-m", "venv", str(venv)]); py = str(venv / "bin" / "python")
    sh([py, "-m", "pip", "-q", "install", "pytest", "pytest-cov", "coverage", "commonmark", "markdown-it-py",
        "pygments", "typing-extensions", "attrs"], t=1200)
    inst = sh([py, "-m", "pip", "-q", "install", "-e", "."], cwd=work, t=1200)
    print(f"environment ({a.python}): pip install -e . -> {'ok' if inst.returncode == 0 else 'FAILED'}", flush=True)
    BASE = ["-W", "default"]
    out, t0 = [], time.time()
    outp = HERE / f"real_{a.repo}.json"
    print(f"\n{'#':>3} {'commit':11} {'file':28} {'truth':>7} {'line':>5} {'file':>5} {'base':>5} {'lanes':>5}  outcome", flush=True)
    for i, r in enumerate(rows[: a.limit], 1):
        sha, rel = r["sha"], r["file"]
        rec = {"sha": sha[:10], "file": rel, "date": r["date"][:10], "subject": r["subject"]}
        sh(["git", "checkout", "-q", "-f", sha + "^"], cwd=work); sh(["git", "clean", "-qfd", "-e", ".venv"], cwd=work)
        for d in work.rglob("__pycache__"):
            shutil.rmtree(d, ignore_errors=True)
        col = sh([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *BASE, "--collect-only"], cwd=work, t=600)
        if col.returncode != 0:
            rec["outcome"] = "SKIP-NO-COLLECT"
        else:
            g0 = sh([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *BASE, "--tb=no"], cwd=work, t=900)
            pre = [l.split(" ")[1] for l in g0.stdout.split("\n") if l.startswith("FAILED") and len(l.split(" ")) > 1]
            desel = [x for t_id in pre for x in ("--deselect", t_id)]
            rec["pre_existing_failures"] = len(pre)
            if pre:
                g0 = sh([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *BASE, "--tb=no", *desel], cwd=work, t=900)
            if g0.returncode != 0:
                rec["outcome"] = "SKIP-BASELINE-NOT-GREEN"
            else:
                sh(["git", "checkout", sha, "--"] + r["tests"], cwd=work)
                g1 = sh([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *BASE, "--tb=no", *desel], cwd=work, t=900)
                if g1.returncode == 0:
                    rec["outcome"] = "SKIP-TEST-DOES-NOT-CATCH"
                elif g1.returncode != 1:
                    rec["outcome"] = "SKIP-SUITE-ERROR"
                else:
                    truth = truth_lines(work, sha, rel); rec["truth_lines"] = truth
                    try:
                        L = locate(str(work), python=py, bisect=False, extra_args=BASE + desel)
                    except Exception as e:
                        rec["outcome"] = f"CRASH {type(e).__name__}: {str(e)[:80]}"; out.append(rec)
                        print(f"{i:>3} {sha[:10]:11} {rel[-28:]:28} {'':>7} {'':>5} {'':>5} {'':>5} {'':>5}  {rec['outcome']}", flush=True)
                        outp.write_text(json.dumps({"repo": a.repo, "rows": out}, indent=1)); continue
                    rec["status"] = L.status; rec["failing"] = L.failing
                    W = L.where
                    files_in_order = list(dict.fromkeys(f.file for f in W))
                    rec["line_rank"] = mid_rank(W, lambda f: f.file == rel and f.line in truth)
                    rec["file_rank"] = (files_in_order.index(rel) + 1) if rel in files_in_order else None
                    o = Oracle(str(work), python=py); o.extra_args = list(o.extra_args) + BASE + desel
                    try:
                        _f, fo = o.failing_output(); base_files = find_candidate_files(o, fo, evidence={})
                        rec["baseline_file_rank"] = (base_files.index(rel) + 1) if rel in base_files else None
                        rec["baseline_files"] = len(base_files)
                    except Exception:
                        rec["baseline_file_rank"] = None
                    rec["top"] = [{"file": f.file, "line": f.line, "score": f.score, "lanes": f.lanes, "bits": f.bits,
                                   "truth": f.file == rel and f.line in truth} for f in W[:15]]
                    rec["why"] = L.why; rec["notes"] = L.notes; rec["seconds"] = L.seconds
                    rec["outcome"] = "LOCATED" if rec["line_rank"] is not None else "MISSED"
        out.append(rec)
        best = rec.get("top", [{}])[0] if rec.get("top") else {}
        print(f"{i:>3} {sha[:10]:11} {rel[-28:]:28} {str(rec.get('truth_lines', ''))[:7]:>7} "
              f"{str(rec.get('line_rank', '')):>5} {str(rec.get('file_rank', '')):>5} {str(rec.get('baseline_file_rank', '')):>5} "
              f"{len(best.get('lanes', [])) if best else '':>5}  {rec['outcome']}", flush=True)
        outp.write_text(json.dumps({"repo": a.repo, "rows": out}, indent=1))
    sh(["git", "checkout", "-q", "-f", "HEAD"], cwd=work)
    judged = [o for o in out if o["outcome"] in ("LOCATED", "MISSED")]
    def top(k, key):
        return sum(1 for o in judged if o.get(key) is not None and o[key] <= k)
    print(f"\njudged {len(judged)} of {len(out)}")
    for k in (1, 5, 10):
        print(f"  line rank <= {k:>2}: {top(k, 'line_rank'):>3}   file rank <= {k:>2}: {top(k, 'file_rank'):>3}   "
              f"baseline file rank <= {k:>2}: {top(k, 'baseline_file_rank'):>3}")
    print(f"{round(time.time() - t0, 1)}s  REAL_DONE", flush=True)


if __name__ == "__main__":
    main()
