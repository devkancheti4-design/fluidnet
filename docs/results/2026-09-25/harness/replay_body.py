"""A replay body: answers the core's requests with the REAL answers an agent gave earlier (0 new tokens), and logs
each request's size — the facts a lean body would read. usage: replay_body.py <bug id>"""
import json, sys
from pathlib import Path
i = sys.argv[1]; req = sys.stdin.read(); A = Path("/private/tmp/claude-501/agentrace")
LEADS = json.load(open(Path(__file__).parent / "hybrid" / "leads_given.json"))
if "Two different fixes" in req:
    t = A / f"pin{i}" / "tests" / "test_pin_choice.py"
    out = "```python\n" + t.read_text() + "```" if t.exists() else "NO-DIFFERENCE: no stored answer"
    kind = "pin"
elif "teach a repair engine" in req:
    out, kind = "", "vocabulary"
else:
    out, kind = LEADS.get(i, ""), "point"
with open(Path(__file__).parent / "hybrid" / "requests.jsonl", "a") as f:
    f.write(json.dumps({"id": i, "kind": kind, "request_chars": len(req), "reply_chars": len(out)}) + "\n")
print(json.dumps({"result": out}))
