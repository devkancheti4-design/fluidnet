# SPDX-License-Identifier: AGPL-3.0-or-later
"""fluidnet — the overseer, certification, descent, and a doctor for the setup."""
from __future__ import annotations

import argparse
import os
import json
import sys
from pathlib import Path

from . import __version__

TEACH_TEMPLATE = '''# rules.py — one fault class = a SIGNAL, a REWRITE, and a PROPERTY. Written once, beside the code.
# Load with:  fluidfix guard . --dictionary rules.py      (or as one net of `fluidnet watch`)

_SIG = re.compile(r"...")                 # a line that can show the fault

def rewrite(line, o):
    return [ ... ]                        # every candidate; the SUITE picks, byte-exact rollback on rejection

register(4, "my-fault-class", "one sentence: what the fault is", _SIG, rewrite)   # kinds 4..7 are yours

def my_property(orig, cand):
    # what EVERY rewrite of this class must keep true, checked over a bounded domain, before any test.
    # return (ok, why, n_inputs_checked). A check that evaluates 0 inputs is UNPROVEN, never PROVEN.
    return propcheck.agree_over("<intended expr>", "<candidate expr>", grid=(1, 2, 3, 5, 8))

teach_property(4, "one sentence a maintainer can review", my_property)
'''


def cmd_watch(a) -> int:
    from .overseer import watch
    r = watch(a.root, a.net, commit=a.commit, python=a.python)
    print("routing, by how much of the repository each net recognises:")
    for s in r["order"]:
        print(f"  {s.dictionary:40} {s.classes} classes  {s.hits:>5} signal hits  {len(s.files)} files")
    print()
    for o in r["outcomes"]:
        print(f"--- net {o.net}: {o.status} (exit {o.exit})")
        print("\n".join("    " + l for l in o.output.splitlines()[-8:]))
    print()
    if r["winner"]:
        print(f"winner: {r['winner']}")
        return 0
    print("every net refused; the tree is as you left it")
    return 2


def cmd_certify(a) -> int:
    from .certify import certify
    patched = Path(a.patch).read_text(encoding="utf-8")
    c = certify(a.root, a.file, patched, python=a.python or sys.executable, confirm=a.confirm)
    print(json.dumps(c.__dict__, indent=1) if a.json else c.render())
    return 0 if c.ok else 2


def cmd_descend(a) -> int:
    from .descend import descend
    code = Path(a.file).read_text(encoding="utf-8")
    r = descend(code, a.test, dictionary=a.dictionary, depth=a.depth, python=a.python or sys.executable)
    for s in r["steps"]:
        print(f"  kind {s['kind']}  {s['before']}  ->  {s['after']}   failing {s['failing']}")
    if r["refused"]:
        print(f"refused: {r.get('why')} ({r['runs']} runs, {r['blocked_by_property']} refuted by property)")
        return 2
    print(f"repaired in {r['runs']} runs, {r['blocked_by_property']} candidates refuted by property")
    if a.write:
        Path(a.file).write_text(r["code"], encoding="utf-8"); print(f"wrote {a.file}")
    return 0


def cmd_gate(a) -> int:
    from .gate import gate, render, ALLOW, WARN
    g = gate(a.root, a.file, Path(a.patch).read_text(encoding="utf-8"), dictionary=a.dictionary,
             python=a.python or sys.executable, confirm=a.confirm)
    print(json.dumps(g, indent=1) if a.json else render(g))
    return {ALLOW: 0, WARN: 1}.get(g["verdict"], 2)


def cmd_mcp(a) -> int:
    from .mcp_server import main as serve
    return serve()


def cmd_locate(a) -> int:
    from .locate import locate, project_python
    L = locate(a.root, python=a.python or project_python(a.root), good=a.good, bisect=not a.no_bisect,
               trace=not a.no_trace)
    if a.json:
        from dataclasses import asdict
        d = asdict(L); d.pop("_vetoed_list", None); print(json.dumps(d, indent=1))
    elif a.format == "vscode":
        # one line per finding, in the shape a problem matcher reads:  file:line: message
        for f in L.where[:5]:
            print(f"{f.file}:{f.line}: cause {f.rank}/15 — {', '.join(f.lanes)}")
        if L.status != "red":
            print(f"# {L.render()}")
    else:
        print(L.render())
    if a.open and L.status == "red" and L.where:
        import shutil, subprocess as sp
        ed = a.editor or os.environ.get("FLUIDNET_EDITOR") or next((e for e in ("code", "cursor", "windsurf") if shutil.which(e)), None)
        if ed:
            sp.Popen([ed, "-g", f"{Path(a.root, L.where[0].file)}:{L.where[0].line}"])
        else:
            print("(no editor command found to --open with; set FLUIDNET_EDITOR)")
    return {"green": 0, "red": 3}.get(L.status, 1)


def cmd_vscode_init(a) -> int:
    """Drop a task into a repo: run it and the guilty line lands in the Problems pane, no extension needed."""
    d = Path(a.root) / ".vscode"; d.mkdir(exist_ok=True); tf = d / "tasks.json"
    task = {"label": "fluidnet: locate the bug", "type": "shell",
            "command": f"{a.fluidnet} locate . --no-bisect --format vscode",
            "presentation": {"reveal": "always", "panel": "dedicated"},
            "problemMatcher": {"owner": "fluidnet", "fileLocation": ["relative", "${workspaceFolder}"],
                               "severity": "error",
                               "pattern": {"regexp": "^([^:#][^:]*):(\\d+): (.*)$", "file": 1, "line": 2, "message": 3}}}
    if tf.exists():
        try:
            cur = json.loads(tf.read_text())
        except json.JSONDecodeError:
            print(f"{tf} exists and is not valid JSON; add this task by hand:\n{json.dumps(task, indent=2)}"); return 1
        cur.setdefault("tasks", [])
        cur["tasks"] = [t for t in cur["tasks"] if t.get("label") != task["label"]] + [task]
    else:
        cur = {"version": "2.0.0", "tasks": [task]}
    tf.write_text(json.dumps(cur, indent=2) + "\n")
    print(f"wrote {tf}\n  Terminal → Run Task → \"fluidnet: locate the bug\"  — the root cause appears in Problems.")
    return 0


def _tk_python() -> str | None:
    import shutil, subprocess as sp
    cands = [sys.executable, "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
             "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3", "/usr/bin/python3",
             shutil.which("python3") or ""]
    for c in cands:
        if c and sp.run([c, "-c", "import tkinter"], capture_output=True).returncode == 0:
            return c
    return None


def cmd_float(a) -> int:
    """Keep .fluidfix/locate.json fresh — on every source change, and every --interval seconds while red —
    and show it as a floating icon under whichever Python here has Tk."""
    import subprocess as sp, threading, time as _t
    from .locate import locate, project_python
    home = Path.home() / ".fluidnet"; home.mkdir(exist_ok=True)
    target_file, scan_now = home / "target", home / "scan-now"
    root = str(Path(a.root).resolve()); target_file.write_text(root)
    fx = Path(root, ".fluidfix"); fx.mkdir(exist_ok=True)
    badge = None
    if not a.headless:
        py = _tk_python()
        if py:
            badge = sp.Popen([py, str(Path(__file__).with_name("float_icon.py")), root])
            print(f"buggy is up (Tk via {py}) — bottom-right of your screen. click: crawl to the root cause · "
                  "drag onto a Finder window: scan that folder · double-click: pick a folder · Ctrl-C here: quit")
        else:
            print("no Python with Tk found here; running headless — read .fluidfix/locate.json")
    def snapshot():
        out = {}
        for p in Path(root).rglob("*.py"):
            if any(part in (".venv", "venv", ".git", "__pycache__", ".fluidfix") for part in p.relative_to(root).parts):
                continue
            try: out[str(p)] = p.stat().st_mtime_ns
            except OSError: pass
        return out
    last, red = snapshot(), False
    print(f"watching {root} — drop the icon on a Finder window to switch folders; Ctrl-C to stop")
    try:
        while True:
            want = target_file.read_text().strip() if target_file.exists() else root
            forced = scan_now.exists()
            if (want and want != root and Path(want).is_dir()) or forced:
                scan_now.unlink(missing_ok=True)
                if want != root:
                    root = want; fx = Path(root, ".fluidfix"); fx.mkdir(exist_ok=True)
                    print(f"[{_t.strftime('%H:%M:%S')}] now watching {root}")
                last = None                                # force a locate on the new target
            now = snapshot()
            if now != last or (red and a.interval):
                last = now
                (fx / "locating").touch()
                try:
                    L = locate(root, python=a.python or project_python(root), bisect=not a.no_bisect)
                    red = L.status == "red"
                    print(f"[{_t.strftime('%H:%M:%S')}] {L.status}" + (f": {L.where[0].file}:{L.where[0].line} ({len(L.where[0].lanes)} lanes)" if red and L.where else ""))
                finally:
                    (fx / "locating").unlink(missing_ok=True)
            if badge is not None and badge.poll() is not None:
                relaunch = getattr(a, "_relaunch", 0)
                if relaunch < 5:
                    a._relaunch = relaunch + 1
                    print(f"[{_t.strftime('%H:%M:%S')}] the icon closed (exit {badge.returncode}); bringing it back — "
                          f"see ~/.fluidnet/icon.log if it keeps happening")
                    badge = sp.Popen([py, str(Path(__file__).with_name("float_icon.py")), root]); _t.sleep(1.5)
                else:
                    print("the icon closed five times; stopping — ~/.fluidnet/icon.log has the reason"); break
            _t.sleep(a.interval if red else 1.0)
    except KeyboardInterrupt:
        print("\nbuggy stopped (Ctrl-C)")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"buggy stopped on an error: {type(e).__name__}: {e}")
    finally:
        if badge is not None and badge.poll() is None:
            badge.terminate()
    return 0


def cmd_scan(a) -> int:
    from .scan import serve
    return serve(a.workspace, port=a.port, python=a.python, bisect=not a.no_bisect)


def cmd_doctor(a) -> int:
    ok = True
    try:
        import fluidfix
        print(f"fluidfix {getattr(fluidfix, '__version__', '?')}  from {Path(fluidfix.__file__).parent}")
    except ImportError:
        print("fluidfix: NOT importable"); return 1
    try:
        from fluidfix import props  # noqa: F401
        print("class-property gate: present (fluidfix.props)")
    except ImportError:
        print("class-property gate: MISSING — this fluidfix predates it; install from git master"); ok = False
    try:
        import pytest_cov  # noqa: F401
        print("pytest-cov: present (fluidfix's localisation needs it)")
    except ImportError:
        print("pytest-cov: MISSING — pip install pytest-cov"); ok = False
    try:
        from .overseer import fluidfix_bin
        print(f"fluidfix CLI: {fluidfix_bin()}")
    except RuntimeError as e:
        print(f"fluidfix CLI: {e}"); ok = False
    print("selfcheck: run `fluidfix selfcheck` to re-derive the six laws on this machine")
    return 0 if ok else 1


def cmd_teach(a) -> int:
    print(TEACH_TEMPLATE, end="")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fluidnet", description=__doc__)
    p.add_argument("--version", action="version", version=f"fluidnet {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("watch", help="route a failing suite to the net whose taught shapes match; one "
                                     "fluidfix process per net")
    w.add_argument("root"); w.add_argument("--net", action="append", required=True,
                                            help="a dictionary file; repeat for each net")
    w.add_argument("--commit", action="store_true", help="commit the winning repair (default: dry-run)")
    w.add_argument("--python"); w.set_defaults(fn=cmd_watch)

    c = sub.add_parser("certify", help="judge a fix nobody here wrote under the repo's own suite")
    c.add_argument("root"); c.add_argument("--file", required=True, help="the file the patch replaces, relative")
    c.add_argument("--patch", required=True, help="a file holding the patched content")
    c.add_argument("--confirm", type=int, default=2); c.add_argument("--python"); c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_certify)

    d = sub.add_parser("descend", help="more than one bug in one file: walk the failing count down to zero")
    d.add_argument("file"); d.add_argument("--test", action="append", required=True, help="an assert; repeat")
    d.add_argument("--dictionary"); d.add_argument("--depth", type=int, default=1)
    d.add_argument("--write", action="store_true", help="write the repaired file (default: print only)")
    d.add_argument("--python"); d.set_defaults(fn=cmd_descend)

    g = sub.add_parser("gate", help="ALLOW / WARN / BLOCK a proposed change to a file — the code-action gate")
    g.add_argument("root"); g.add_argument("--file", required=True); g.add_argument("--patch", required=True)
    g.add_argument("--dictionary"); g.add_argument("--confirm", type=int, default=2); g.add_argument("--python")
    g.add_argument("--json", action="store_true"); g.set_defaults(fn=cmd_gate)

    l = sub.add_parser("locate", help="root cause of a red suite: WHERE (file, line), WHEN (commit, by "
                                      "bisect), WHY (first divergence from a passing test)")
    l.add_argument("root"); l.add_argument("--good", help="a revision known green (else searched, 24 back)")
    l.add_argument("--no-bisect", action="store_true"); l.add_argument("--no-trace", action="store_true")
    l.add_argument("--python"); l.add_argument("--json", action="store_true")
    l.add_argument("--format", choices=["text", "vscode"], default="text", help="vscode: file:line: message per finding")
    l.add_argument("--open", action="store_true", help="jump your editor to the top line (code/cursor/windsurf, or FLUIDNET_EDITOR)")
    l.add_argument("--editor"); l.set_defaults(fn=cmd_locate)

    vi = sub.add_parser("vscode-init", help="add a 'fluidnet: locate the bug' task with a problem matcher to a repo's .vscode/tasks.json")
    vi.add_argument("root"); vi.add_argument("--fluidnet", default="fluidnet", help="how the task should invoke fluidnet")
    vi.set_defaults(fn=cmd_vscode_init)

    for name in ("buggy", "float"):
        fl = sub.add_parser(name, help="buggy — the pixel bug: twitches while the suite is red; click it and it "
                                       "crawls your file to the root cause; drop it on a Finder window to scan "
                                       "that folder" + ("" if name == "buggy" else " (alias of buggy)"))
        fl.add_argument("root", nargs="?", default=".")
        fl.add_argument("--interval", type=float, default=15.0, help="re-locate this often while red (default 15s)")
        fl.add_argument("--no-bisect", action="store_true"); fl.add_argument("--headless", action="store_true")
        fl.add_argument("--python"); fl.set_defaults(fn=cmd_float)

    sc = sub.add_parser("scan", help="a workspace of project folders, scanned one after another, watched live "
                                      "in the browser: the ladybug follows real scan events")
    sc.add_argument("workspace"); sc.add_argument("--port", type=int, default=7777)
    sc.add_argument("--no-bisect", action="store_true"); sc.add_argument("--python"); sc.set_defaults(fn=cmd_scan)

    sub.add_parser("mcp", help="serve gate / certify / propose over MCP (stdio); needs fluidnet[mcp]").set_defaults(fn=cmd_mcp)

    sub.add_parser("doctor", help="is this install able to prove, not just guess?").set_defaults(fn=cmd_doctor)
    sub.add_parser("teach", help="print the template for a class and its property").set_defaults(fn=cmd_teach)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
