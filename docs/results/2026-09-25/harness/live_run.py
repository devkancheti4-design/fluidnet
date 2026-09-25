"""Live: fluidnet watch in token-saving mode on a fresh copy, the AI agent as its oracle through oracle/bridge.py.
usage: live_run.py <bug id>"""
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
import bugs
LB = Path(__file__).resolve().parent; M = bugs.load(); i = int(sys.argv[1]); m = M[i]
A = Path("/private/tmp/claude-501/agentrace"); d = A / f"live{i}"; CV = LB.parent / "cvenv" / "bin"
ORIG = subprocess.run(["git", "-C", str(LB / "click"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
if d.exists(): shutil.rmtree(d)
d.mkdir(parents=True)
subprocess.run(f"git -C {LB/'click'} archive {ORIG} | tar -x -C {d}", shell=True, check=True)
(d / m["file"]).write_text(bugs.mut_text(m))
for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "click"]):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *c], cwd=d, check=True)
subprocess.run(["git", "config", "user.email", "t@t"], cwd=d); subprocess.run(["git", "config", "user.name", "t"], cwd=d)
env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|ANTHROPIC|OPENAI", k)}
env["PYTHONPATH"] = str(d / "src"); env["PATH"] = f"{CV}:{env['PATH']}"
cmd = [str(CV / "fluidnet"), "watch", str(d), "--net", str(LB / "nets/A_corpus.py"), "--net", str(LB / "nets/B_sibling.py"),
       "--net", str(LB / "nets/C_real.py"), "--python", str(A / "venv/bin/python"), "-j", "1", "--commit",
       "--body", f"python3 {LB / 'oracle' / 'bridge.py'} {i}", "--mode", "thrift"]
t0 = time.time(); log = LB / f"live_{i}.log"
with open(log, "w") as fo:
    p = subprocess.Popen(cmd, cwd=d, env=env, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
    p.wait()
secs = round(time.time() - t0, 1); text = log.read_text(); now = (d / m["file"]).read_text()
suite = subprocess.run([str(A / "venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no"], cwd=d,
                       env={"PYTHONPATH": str(d / "src"), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
rec = {"id": i, "at": f"{m['file'][10:]}:{m['line']}", "secs": secs, "exact": now.rstrip() == bugs.orig_text(m).rstrip(),
       "changed": now != bugs.mut_text(m), "suite_green": suite.returncode == 0,
       "line_now": now.split("\n")[m["line"] - 1].strip(), "winner": (re.search(r"^winner: (.+?)(?:\s{2}|$)", text, re.M) or [None, None])[1],
       "committed": subprocess.run(["git", "log", "--oneline"], cwd=d, capture_output=True, text=True).stdout.strip().splitlines()[:2],
       "stages": [l.strip() for l in text.splitlines() if re.match(r"^\s{2}\S", l) and re.search(r"\d+\.\ds\s", l)]}
open(LB / "live.jsonl", "a").write(json.dumps(rec) + "\n"); print(json.dumps(rec, indent=1))
