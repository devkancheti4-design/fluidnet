"""Real multi-line click bugs: the tree at the maintainer's fix commit, with ONLY the source hunk reverted (the
maintainer's regression test kept). Valid only if red as the bug and green with the maintainer's fix."""
import json, subprocess, shutil
from pathlib import Path
REPO = "/private/tmp/claude-501/-Users-kanchetidevieswar-neo/107a7e63-6bc9-4d5b-b4a5-b0d23111954f/scratchpad/repos_full/click"
A = Path("/private/tmp/claude-501/agentrace"); PY = str(A / "venv/bin/python")
SHAS = ["f58ca3e814", "0551bf5358", "701b313160", "c326df95e9", "1a4d8c1bb1", "61f8101f4e", "e003331551", "4aff02676c", "11c286a37d"]
rows = json.load(open("/Users/kanchetidevieswar/neo/fluidfix/research/real-history-2026-09-19/remine.json"))["rows"]
out = {}
def suite(d):
    p = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "-x", "-W", "default"], cwd=d,
                       env={"PYTHONPATH": str(d / "src"), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=900)
    return p.returncode, (p.stdout.strip().splitlines() or [""])[-1][:90]
for s in SHAS:
    r = next(x for x in rows if x["repo"] == "click" and x["sha"].startswith(s)); f = r["file"]
    d = A / f"hard_{s}"
    if d.exists(): shutil.rmtree(d)
    d.mkdir()
    subprocess.run(f"git -C {REPO} archive {s} | tar -x -C {d}", shell=True, check=True)
    fixed = (d / f).read_text()
    patch = subprocess.run(["git", "-C", REPO, "show", s, "--", f], capture_output=True, text=True).stdout
    ap = subprocess.run(["git", "apply", "-R", "-"], cwd=d, input=patch, capture_output=True, text=True)
    if ap.returncode:
        out[s] = {"ok": False, "why": "revert failed: " + ap.stderr[:120]}; print(s, out[s]); continue
    bug = (d / f).read_text()
    rc_bug, sum_bug = suite(d)
    (d / f).write_text(fixed); rc_fix, sum_fix = suite(d); (d / f).write_text(bug)
    for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "click"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *c], cwd=d, check=True)
    (A / f"hard_{s}.fixed").write_text(fixed)          # the maintainer's file, kept OUTSIDE the copy
    out[s] = {"ok": rc_bug != 0 and rc_fix == 0, "file": f, "subject": r["subject"], "bug": sum_bug, "fixed": sum_fix,
              "minus": len([l for l in r["minus"] if l.strip()]), "plus": len([l for l in r["plus"] if l.strip()])}
    print(s, "VALID" if out[s]["ok"] else "invalid", f, "| bug:", sum_bug, "| fixed:", sum_fix, flush=True)
json.dump(out, open("hard_bugs.json", "w"), indent=1)
