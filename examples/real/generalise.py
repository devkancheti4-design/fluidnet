#!/usr/bin/env python3
"""Generated instances of the three shapes — names, values, files and positions all new — judged by tests.
Runs in-process through fluidnet.descend (the same candidates, property gate and judge the CLI uses)."""
import random, sys
from pathlib import Path
from fluidnet.descend import descend
DICT = str(Path(__file__).resolve().parent / "rules.py")
rng = random.Random(20260922)
W = ["opts", "cfg", "params", "meta", "env", "conf", "settings", "args"]
K = ["label", "title", "name", "path", "tag", "mode", "kind", "unit"]
MODS = [("math", "math.floor(x)"), ("json", "json.dumps(x)"), ("time", "time.time() and x"),
        ("os", "os.path.basename(x)"), ("re", "re.sub('a', 'b', x)"), ("string", "string.capwords(x)")]

def guard_instance(k):
    r = random.Random(k); w, key = r.choice(W), r.choice(K)
    forms = [
        (f"def f({w}):\n    v = {w}.get('{key}')\n    return v.upper()\n",
         [f"assert f({{}}) == ''", f"assert f({{'{key}': 'ab'}}) == 'AB'"]),
        (f"def f({w}):\n    v = {w}.get('{key}')\n    return len(v) + 1\n",
         [f"assert f({{}}) == 1", f"assert f({{'{key}': 'abc'}}) == 4"]),
        (f"DEFAULT_{key.upper()} = 7\n\ndef f({w}):\n    {key} = {w}.get('{key}')\n    return {key} * 2\n",
         [f"assert f({{}}) == 14", f"assert f({{'{key}': 3}}) == 6"]),
        (f"class C:\n    {key.upper()}_LIMIT = 5\n    def __init__(self, {w}):\n        self.{key} = {w}.get('{key}')\n"
         f"    def go(self):\n        return self.{key} + 1\n",
         [f"assert C({{}}).go() == 6", f"assert C({{'{key}': 1}}).go() == 2"]),
    ]
    return forms[k % 4]

def import_instance(k):
    r = random.Random(1000 + k); mod, expr = MODS[k % len(MODS)]; w = r.choice(W)
    code = f"import sys\n\ndef {w}_fn(x):\n    return {expr}\n"
    tests = {"math": ["assert opts_fn(2.5) == 2"], "json": ["assert opts_fn([1]) == '[1]'"],
             "time": ["assert opts_fn(1) == 1"], "os": ["assert opts_fn('a/b') == 'b'"],
             "re": ["assert opts_fn('a') == 'b'"], "string": ["assert opts_fn('ab cd') == 'Ab Cd'"]}[mod]
    return code, [t.replace("opts_fn", f"{w}_fn") for t in tests]

def return_instance(k):
    r = random.Random(2000 + k); w = r.choice(W); meth = r.choice(["append", "insert", "extend", "sort"])
    arg = {"append": "9", "insert": "0, 9", "extend": "[9]", "sort": ""}[meth]
    code = f"def {w}_add(xs):\n    xs.{meth}({arg})\n"
    want = {"append": "[1, 9]", "insert": "[9, 1]", "extend": "[1, 9]", "sort": "[1]"}[meth]
    return code, [f"assert {w}_add([1]) == {want}"]

for title, gen, n in (("none-flows-on-unguarded", guard_instance, 12),
                      ("module-used-never-imported", import_instance, 12),
                      ("mutating-call-missing-its-return", return_instance, 8)):
    ok = 0; runs = 0; blocked = 0
    for k in range(n):
        code, tests = gen(k)
        r = descend(code, tests, dictionary=DICT, depth=1)
        ok += not r["refused"]; runs += r["runs"]; blocked += r["blocked_by_property"]
    print(f"{title:36} {ok:>2}/{n} repaired   {runs/n:4.1f} runs each   {blocked} refuted by property")
