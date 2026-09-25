"""Score one agent's work on /private/tmp/claude-501/agentrace/bug<id>: exact vs click's original, the full
suite, test files untouched, what else changed. usage: score_agent.py <id> <seconds> <tokens>"""
import json, subprocess, sys
from pathlib import Path
import bugs
M = bugs.load(); i = int(sys.argv[1]); m = M[i]; d = Path(f"/private/tmp/claude-501/agentrace/bug{i}")
diff = subprocess.run(["git", "diff", "--stat"], cwd=d, capture_output=True, text=True).stdout
changed = [l.split("|")[0].strip() for l in diff.splitlines() if "|" in l]
untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=d, capture_output=True, text=True).stdout.split()
now = (d / m["file"]).read_text()
suite = subprocess.run(["../venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no"], cwd=d,
                       env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
rec = {"id": i, "op": m["op"], "at": f"{m['file'][10:]}:{m['line']}", "secs": float(sys.argv[2]), "tokens": sys.argv[3],
       "exact": now.rstrip() == bugs.orig_text(m).rstrip(), "files_changed": changed, "untracked": untracked,
       "tests_touched": [f for f in changed + untracked if f.startswith("tests/")],
       "suite": (suite.stdout.strip().splitlines() or [""])[-1], "suite_green": suite.returncode == 0,
       "line_now": now.split("\n")[m["line"] - 1].strip(), "line_orig": bugs.orig_text(m).split("\n")[m["line"] - 1].strip()}
open("race_agent.jsonl", "a").write(json.dumps(rec) + "\n"); print(json.dumps(rec, indent=1))
