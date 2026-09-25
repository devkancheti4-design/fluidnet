"""fluidnet's --body for the live test: the core's question goes to a request file; the oracle's answer comes back
through an answer file. fluidnet blocks here until it arrives (30 min at most). usage: bridge.py <bug id>"""
import json, sys, time
from pathlib import Path
D = Path(__file__).resolve().parent; bug = sys.argv[1]
req = sys.stdin.read(); n = 0
while (D / f"req-{bug}-{n}.txt").exists():
    n += 1
(D / f"req-{bug}-{n}.txt").write_text(req)
rep, t0 = D / f"rep-{bug}-{n}.json", time.time()
while not rep.exists() and time.time() - t0 < 1800:
    time.sleep(2)
if not rep.exists():
    print(json.dumps({"result": "", "is_error": True})); sys.exit(0)
time.sleep(0.5)
print(rep.read_text())
