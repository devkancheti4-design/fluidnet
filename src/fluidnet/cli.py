# SPDX-License-Identifier: AGPL-3.0-or-later
"""fluidnet — the overseer, certification, descent, and a doctor for the setup."""
from __future__ import annotations

import argparse
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
    from .locate import locate
    L = locate(a.root, python=a.python or sys.executable, good=a.good, bisect=not a.no_bisect,
               trace=not a.no_trace)
    if a.json:
        from dataclasses import asdict
        print(json.dumps(asdict(L), indent=1))
    else:
        print(L.render())
    return {"green": 0, "red": 3}.get(L.status, 1)


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
    from .locate import locate
    root = str(Path(a.root).resolve()); fx = Path(root, ".fluidfix"); fx.mkdir(exist_ok=True)
    badge = None
    if not a.headless:
        py = _tk_python()
        if py:
            badge = sp.Popen([py, str(Path(__file__).with_name("float_icon.py")), root])
            print(f"floating icon up (Tk via {py}); click it for the root cause, right-click to quit")
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
    print(f"watching {root} — Ctrl-C to stop")
    try:
        while True:
            now = snapshot()
            if now != last or (red and a.interval):
                last = now
                (fx / "locating").touch()
                try:
                    L = locate(root, python=a.python or sys.executable, bisect=not a.no_bisect)
                    red = L.status == "red"
                    print(f"[{_t.strftime('%H:%M:%S')}] {L.status}" + (f": {L.where[0].file}:{L.where[0].line} ({len(L.where[0].lanes)} lanes)" if red and L.where else ""))
                finally:
                    (fx / "locating").unlink(missing_ok=True)
            if badge is not None and badge.poll() is not None:
                print("icon closed; stopping"); break
            _t.sleep(a.interval if red else 1.0)
    except KeyboardInterrupt:
        pass
    finally:
        if badge is not None and badge.poll() is None:
            badge.terminate()
    return 0


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
    l.add_argument("--python"); l.add_argument("--json", action="store_true"); l.set_defaults(fn=cmd_locate)

    fl = sub.add_parser("float", help="a floating icon: grey green, red red, click for the root cause; keeps "
                                      "locate.json fresh on every source change")
    fl.add_argument("root"); fl.add_argument("--interval", type=float, default=15.0,
                                             help="re-locate this often while red (default 15s)")
    fl.add_argument("--no-bisect", action="store_true"); fl.add_argument("--headless", action="store_true")
    fl.add_argument("--python"); fl.set_defaults(fn=cmd_float)

    sub.add_parser("mcp", help="serve gate / certify / propose over MCP (stdio); needs fluidnet[mcp]").set_defaults(fn=cmd_mcp)

    sub.add_parser("doctor", help="is this install able to prove, not just guess?").set_defaults(fn=cmd_doctor)
    sub.add_parser("teach", help="print the template for a class and its property").set_defaults(fn=cmd_teach)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
