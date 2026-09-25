import hashlib, json, os, re, subprocess, time
from pathlib import Path
LB = Path(__file__).resolve().parent; VENV = LB / "venv" / "bin"
SECRET = re.compile(r"API_KEY|ANTHROPIC|OPENAI|GEMINI|MISTRAL|GROQ|TOGETHER")
REMOVED = sorted(k for k in os.environ if SECRET.search(k))
def env_for(wd):
    e = {k: v for k, v in os.environ.items() if not SECRET.search(k)}
    e["PYTHONPATH"] = str(wd / "src"); e["PATH"] = f"{VENV}:{e['PATH']}"
    return e
def sh(cmd, wd, t=900):
    """Its own process group, output to a FILE not a pipe, and the whole group killed afterwards — a bug that
    makes a test spawn a process that never exits must not hold a pipe open or survive as an orphan
    (2026-09-24: two workers hung forever that way and the machine ran out of memory)."""
    import signal, tempfile
    with tempfile.TemporaryFile() as fo:
        p = subprocess.Popen([str(c) for c in cmd], cwd=wd, env=env_for(wd), stdout=fo,
                             stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = p.wait(timeout=t)
        except subprocess.TimeoutExpired:
            rc = 124
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        p.wait()
        fo.seek(0); out = fo.read().decode(errors="replace")
    class R: pass
    r = R(); r.returncode, r.stdout, r.stderr = rc, out, ""
    return r
def git(wd, *a):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=wd, capture_output=True, text=True)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def suite(wd):
    r = sh([VENV / "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "default", "--tb=no"], wd, 60)
    m = re.search(r"(\d+) failed", r.stdout); return r.returncode, int(m.group(1)) if m else 0
