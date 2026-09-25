"""The hybrid's core side: fluidnet watch with the body's lead (data only), all three nets, buggy as fallback.
usage: hyb_core.py <id> <body_secs> <body_tokens> <lead> [<lead> ...]   (lead = file:line[,line])"""
import json, os, re, subprocess, sys, time
from pathlib import Path
import bugs
LB = Path(__file__).resolve().parent; M = bugs.load(); A = Path("/private/tmp/claude-501/agentrace")
i = int(sys.argv[1]); bsecs = float(sys.argv[2]); btok = int(sys.argv[3]); leads = sys.argv[4:]
m = M[i]; d = A / f"hyb{i}"; CV = LB.parent / "cvenv" / "bin"
env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|ANTHROPIC|OPENAI", k)}
env["PYTHONPATH"] = str(d / "src"); env["PATH"] = f"{CV}:{env['PATH']}"
cmd = [str(CV / "fluidnet"), "watch", str(d), "--net", str(LB / "nets/A_corpus.py"), "--net", str(LB / "nets/B_sibling.py"),
       "--net", str(LB / "nets/C_real.py"), "--python", str(A / "venv/bin/python"), "-j", "1", "--commit"]
for l in leads: cmd += ["--lead", l]
t0 = time.time(); log = LB / f"hyb_{i}.log"
with open(log, "w") as fo:
    p = subprocess.Popen(cmd, cwd=d, env=env, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
    try: p.wait(timeout=5400)
    except subprocess.TimeoutExpired: pass
    try: os.killpg(p.pid, 9)
    except ProcessLookupError: pass
    p.wait()
csecs = round(time.time() - t0, 1); text = log.read_text(); now = (d / m["file"]).read_text()
suite = subprocess.run([str(A / "venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no"], cwd=d,
                       env={"PYTHONPATH": str(d / "src"), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
rec = {"id": i, "at": f"{m['file'][10:]}:{m['line']}", "lead": leads, "body_secs": bsecs, "body_tokens": btok,
       "core_secs": csecs, "total_secs": round(bsecs + csecs, 1), "ambiguous": "AMBIGUOUS" in text,
       "buggy_ran": "locate (buggy)" in text, "exact": now.rstrip() == bugs.orig_text(m).rstrip(),
       "suite_green": suite.returncode == 0,
       "stages": [l.strip() for l in text.splitlines() if re.match(r"^\s{2}\S", l) and re.search(r"\d+\.\ds\s", l)]}
open(LB / "hyb.jsonl", "a").write(json.dumps(rec) + "\n")
print(json.dumps({k: rec[k] for k in ("id", "at", "lead", "core_secs", "total_secs", "ambiguous", "buggy_ran", "exact", "suite_green")}))
print("\n".join(rec["stages"]))
