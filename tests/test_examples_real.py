"""The shipped real-shape example must keep repairing what it claims to."""
import sys
from pathlib import Path
from fluidnet.descend import descend
DICT = str(Path(__file__).resolve().parents[1] / "examples/real/rules.py")


def test_guard_with_a_vouched_default():
    code = "class C:\n    LIMIT = 5\n    def __init__(self, opts):\n        self.limit = opts.get('limit')\n    def go(self):\n        return self.limit + 1\n"
    r = descend(code, ["assert C({}).go() == 6", "assert C({'limit': 1}).go() == 2"], dictionary=DICT)
    assert not r["refused"] and "self.limit = self.LIMIT" in r["code"], r


def test_missing_stdlib_import():
    r = descend("import sys\n\ndef f(x):\n    return math.floor(x)\n", ["assert f(2.5) == 2"], dictionary=DICT)
    assert not r["refused"] and r["code"].startswith("import math\n"), r


def test_mutated_then_returned():
    r = descend("def add(xs):\n    xs.append(9)\n", ["assert add([1]) == [1, 9]"], dictionary=DICT)
    assert not r["refused"] and "return xs" in r["code"], r
