"""Teach once, test on the held-out: the swapped-names class (nets/E_suit_vocab.py, taught from utils.py:141)
on all 12 swapped-name bugs click's suite catches — the file named, the patched fluidfix, zero tokens."""
import json, os, subprocess, sys, time
sys.path.insert(0, "."); import bugs
from common import LB, git, sha
M = bugs.load(); wd = LB / "w1"; TRUE = git(LB / "click", "rev-parse", "HEAD").stdout.strip()
ids = json.load(open(LB / "swapargs_ids.json")); ids = [9761, 5196, 7694, 9320] + [i for i in ids if i not in (9761, 5196, 7694, 9320)]   # the taught bug, the reachable, then the rest
env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and "ANTHROPIC" not in k}
env["PYTHONPATH"] = f"/Users/kanchetidevieswar/neo/fluidfix/src:{wd / 'src'}"
out = LB / "teach_suit.jsonl"; out.touch()
done = {json.loads(l)["id"] for l in open(out) if l.strip()}
for i in ids:
    if i in done: continue
    m = M[i]; git(wd, "reset", "-q", "--hard", TRUE); git(wd, "clean", "-qfd")
    (wd / m["file"]).write_text(bugs.mut_text(m)); git(wd, "commit", "-qam", "regress"); msha = sha(wd / m["file"])
    cmd = ["nice", "-n", "19", str(LB / "venv/bin/fluidfix"), "repair", ".", "--file", m["file"], "--observer",
           "mechanical", "--json", "--suite-timeout", "60", "--budget", "1800", "--dictionary", str(LB / "nets/E_suit_vocab.py")]
    t0 = time.time(); log = LB / f"teach_suit_{i}.log"
    with open(log, "w") as fo:
        p = subprocess.Popen(cmd, cwd=wd, env=env, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
        try: p.wait(timeout=2400)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(p.pid, 9)
        except ProcessLookupError: pass
        p.wait()
    s = log.read_text(); d = {}
    try: d = json.loads(s[s.find("{"):])
    except Exception: pass
    now = (wd / m["file"]).read_text()
    rec = {"id": i, "role": "train" if i == 9761 else "held-out", "at": f"{m['file'][10:]}:{m['line']}",
           "secs": round(time.time() - t0, 1), "repaired": bool(d.get("repaired")),
           "exact": now.rstrip() == bugs.orig_text(m).rstrip() if d.get("repaired") else None,
           "untouched_on_refusal": (sha(wd / m["file"]) == msha) if not d.get("repaired") else None,
           "ruling": d.get("ruling"), "suite_runs": d.get("suite_runs"), "tokens": d.get("tokens", 0),
           "refused_by_property": d.get("refuted_by_property")}
    if d.get("repaired"):
        r = subprocess.run([str(LB / "venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no"],
                           cwd=wd, env=env, capture_output=True, text=True, timeout=600, start_new_session=True)
        rec["suite_after"] = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    open(out, "a").write(json.dumps(rec) + "\n"); print(json.dumps(rec), flush=True)
git(wd, "reset", "-q", "--hard", TRUE)
