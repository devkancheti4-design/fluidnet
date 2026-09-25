"""The clean pass: all ten race bugs through TODAY's product, pinned — fluidfix e09eb24 (localisation, --focus),
fluidnet a560d72 + overseer-cheapest-first.patch sha256 58a74e12… (nets cheapest first per file; buggy first, focus capped to buggy's top lines, every buggy-touched fix certified, fallback,
harness never stops the judge), buggy a0aa44a (mutation lane, spaced test ids). Fresh no-history copies,
sequential, one job on the machine, no hints: no file named, no line named."""
import json, os, re, subprocess, shutil, time
from pathlib import Path
import bugs
LB = Path(__file__).resolve().parent; M = bugs.load()
CV = LB.parent / "cvenv" / "bin"; FN = str(CV / "fluidnet"); PY = str(LB / "venv/bin/python")
ORIG = subprocess.run(["git", "-C", str(LB / "click"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
out = LB / "race_final.jsonl"; out.touch()
done = {json.loads(l)["id"] for l in open(out) if l.strip()}
for i in json.load(open(LB / "race_ids.json")):
    if i in done: continue
    m = M[i]; d = LB / "race" / str(i) / "fn2"
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    subprocess.run(f"git -C {LB/'click'} archive {ORIG} | tar -x -C {d}", shell=True, check=True)
    (d / m["file"]).write_text(bugs.mut_text(m))
    for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "click"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *c], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d); subprocess.run(["git", "config", "user.name", "t"], cwd=d)
    env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|ANTHROPIC|OPENAI", k)}
    env["PYTHONPATH"] = str(d / "src"); env["PATH"] = f"{CV}:{env['PATH']}"
    cmd = [FN, "watch", str(d), "--net", str(LB / "nets/A_corpus.py"), "--net", str(LB / "nets/B_sibling.py"),
           "--net", str(LB / "nets/C_real.py"), "--python", PY, "-j", "1", "--commit"]
    log = LB / "race" / str(i) / "final.log"; t0 = time.time()
    with open(log, "w") as fo:
        p = subprocess.Popen(cmd, cwd=d, env=env, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
        try: p.wait(timeout=5400)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(p.pid, 9)
        except ProcessLookupError: pass
        p.wait()
    secs = round(time.time() - t0, 1); text = log.read_text()
    now = (d / m["file"]).read_text()
    suite = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "default", "--tb=no"],
                           cwd=d, env=env, capture_output=True, text=True, start_new_session=True)
    win = re.search(r"^winner: (.+?)(?:\s{2}|$)", text, re.M)
    orig_line = bugs.orig_text(m).split("\n")[m["line"] - 1].strip(); now_line = now.split("\n")[m["line"] - 1].strip() if len(now.split("\n")) >= m["line"] else ""
    rec = {"id": i, "op": m["op"], "at": f"{m['file'][10:]}:{m['line']}", "secs": secs, "exit": p.returncode,
           "winner": win.group(1).split("/")[-1] if win else None, "exact": now.rstrip() == bugs.orig_text(m).rstrip(),
           "changed": now != bugs.mut_text(m), "line_now": now_line, "line_orig": orig_line,
           "suite": (suite.stdout.strip().splitlines() or [""])[-1], "suite_green": suite.returncode == 0, "tokens": 0,
           "stages": [l.strip() for l in text.splitlines() if re.match(r"^\s{2}\S", l) and re.search(r"\d+\.\ds\s", l)]}
    open(out, "a").write(json.dumps(rec) + "\n")
    print(json.dumps({k: rec[k] for k in ("id", "op", "at", "secs", "winner", "exact", "suite_green")}), flush=True)
