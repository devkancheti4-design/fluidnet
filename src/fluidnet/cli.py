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

    sub.add_parser("doctor", help="is this install able to prove, not just guess?").set_defaults(fn=cmd_doctor)
    sub.add_parser("teach", help="print the template for a class and its property").set_defaults(fn=cmd_teach)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
