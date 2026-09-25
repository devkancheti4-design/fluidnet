"""Is buggy's miss on _textwrap.py:168 the LAW or the BUDGET? buggy alone on a fresh copy, mutation lane given
8 workers, 1800 s, 10,000 mutants (the race gave it 1 worker and 240 s, and it measured 47 lines and cut 1,130)."""
import json, os, re, shutil, subprocess, time
from pathlib import Path
import bugs
LB = Path(__file__).resolve().parent; M = bugs.load(); i = 2014; m = M[i]
ORIG = subprocess.run(["git", "-C", str(LB / "click"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
d = LB / "race" / str(i) / "buggy_big"
if d.exists(): shutil.rmtree(d)
d.mkdir(parents=True)
subprocess.run(f"git -C {LB/'click'} archive {ORIG} | tar -x -C {d}", shell=True, check=True)
(d / m["file"]).write_text(bugs.mut_text(m))
for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "click"]):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *c], cwd=d, check=True)
env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|ANTHROPIC|OPENAI", k)}
env["PYTHONPATH"] = str(d / "src")
BB = str(LB.parent / "cvenv" / "bin" / "buggy")
# sized from the first run's own numbers: 47 lines in 242 s on one worker -> ~1,177 lines is ~6,000 worker-s;
# 8 workers x 1,800 s covers it, and the mutant cap (default 300) must not be what cuts it instead
cmd = [BB, "locate", str(d), "--python", str(LB / "venv/bin/python"), "-j", "8", "--mutate-seconds", "1800",
       "--mutants", "10000", "--json"]
t0 = time.time(); log = LB / "race" / str(i) / "buggy_big.log"
with open(log, "w") as fo:
    p = subprocess.Popen(cmd, cwd=d, env=env, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
    try: p.wait(timeout=4200)
    except subprocess.TimeoutExpired: pass
    try: os.killpg(p.pid, 9)
    except ProcessLookupError: pass
    p.wait()
secs = round(time.time() - t0, 1)
L = json.load(open(d / ".buggy" / "locate.json"))
def pos(lane):
    xs = L.get(lane) or []
    for n, x in enumerate(xs, 1):
        if x.get("file", "").endswith("_textwrap.py") and x.get("line") == m["line"]:
            return n, x.get("rank")
    return None
out = {"id": i, "secs": secs, "mutation_cost": L.get("mutation_cost"),
       "fault_in_mutation_lane": pos("mutation"), "fault_in_where_lane": pos("where"),
       "mutation_top": [(x.get("file", "")[10:], x.get("line"), x.get("rank")) for x in (L.get("mutation") or [])[:6]],
       "repairs": [(r.get("file", "")[10:], r.get("line"), r.get("edit")) for r in (L.get("repairs") or [])][:6]}
json.dump(out, open(LB / "buggy_big.json", "w"), indent=1); print(json.dumps(out, indent=1))
