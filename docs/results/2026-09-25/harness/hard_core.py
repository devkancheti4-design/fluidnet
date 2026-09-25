"""The core on a real multi-line click bug, with ONLY the suit's vocabulary (vocab.py in the copy): fluidfix repair,
file named, patched fluidfix, 30-min budget. Scored against the maintainer's own file. usage: hard_core.py <sha>"""
import json, os, subprocess, sys, time, hashlib
from pathlib import Path
s = sys.argv[1]; A = Path("/private/tmp/claude-501/agentrace"); d = A / f"hard_{s}"; LB = Path(__file__).resolve().parent
meta = json.load(open(LB / "hard_bugs.json"))[s]; f = meta["file"]
vocab = LB / f"hard_vocab_{s}.py"; vocab.write_text((d / "vocab.py").read_text())      # the suit's file, kept outside
(d / "vocab.py").unlink()                                                             # the tree as the bug left it
bug = (d / f).read_text(); sha0 = hashlib.sha256(bug.encode()).hexdigest()
env = dict(os.environ, PYTHONPATH=f"/Users/kanchetidevieswar/neo/fluidfix/src:{d / 'src'}")
cmd = [str(LB / "venv/bin/fluidfix"), "repair", str(d), "--file", f, "--observer", "mechanical", "--json",
       "--suite-timeout", "120", "--budget", "1800", "--dictionary", str(vocab), "--python", str(A / "venv/bin/python")]
t0 = time.time(); log = LB / f"hard_core_{s}.log"
with open(log, "w") as fo:
    p = subprocess.Popen(cmd, cwd=d, env=env, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
    try: p.wait(timeout=2400)
    except subprocess.TimeoutExpired: pass
    try: os.killpg(p.pid, 9)
    except ProcessLookupError: pass
    p.wait()
secs = round(time.time() - t0, 1); txt = log.read_text(); res = {}
try: res = json.loads(txt[txt.find("{"):])
except Exception: pass
now = (d / f).read_text(); fixed = (A / f"hard_{s}.fixed").read_text()
suite = subprocess.run([str(A / "venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "-W", "default"],
                       cwd=d, env={"PYTHONPATH": str(d / "src"), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
rec = {"sha": s, "file": f, "secs": secs, "repaired": bool(res.get("repaired")), "ruling": res.get("ruling"),
       "suite_runs": res.get("suite_runs"), "exact": now.rstrip() == fixed.rstrip(),
       "suite_green": suite.returncode == 0, "suite": (suite.stdout.strip().splitlines() or [""])[-1][:90],
       "untouched_on_refusal": hashlib.sha256(now.encode()).hexdigest() == sha0 if not res.get("repaired") else None,
       "reason": (res.get("reason") or "")[:300]}
if rec["repaired"]:
    import difflib
    rec["diff_vs_maintainer"] = "".join(difflib.unified_diff(fixed.splitlines(True), now.splitlines(True), "maintainer", "core", n=0))[:1500]
subprocess.run(["git", "checkout", "--", f], cwd=d)                                   # leave the bug as found
open(LB / "hard_core.jsonl", "a").write(json.dumps(rec) + "\n"); print(json.dumps(rec, indent=1))
