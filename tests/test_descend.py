"""Only SHIPPED classes are used, so the test needs no dictionary file."""
from fluidnet.descend import descend

THREE = """def gap(a, b):
    return a - b

def step(n):
    return n + 1

def small(a, b):
    return a < b
"""
THREE_TESTS = ["assert gap(2, 5) == 3", "assert step(5) == 4",
               "assert small(3, 3) is True", "assert small(2, 3) is True"]


def test_three_faults_three_lines():
    r = descend(THREE, THREE_TESTS)
    assert not r["refused"], r
    assert [s["failing"] for s in r["steps"]] == ["3 -> 2", "2 -> 1", "1 -> 0"]
    assert "return b - a" in r["code"] and "return n - 1" in r["code"] and "return a <= b" in r["code"]


ONE_LINE = "def f(a, b):\n    return a - b + 1\n"
ONE_LINE_TESTS = ["assert f(2, 5) == 2", "assert f(1, 4) == 2"]   # only  b - a - 1  satisfies both


def test_two_faults_one_line_needs_depth_two():
    assert descend(ONE_LINE, ONE_LINE_TESTS, depth=1)["refused"]        # no single rewrite moves the count
    r = descend(ONE_LINE, ONE_LINE_TESTS, depth=2)
    assert not r["refused"], r
    # the repaired FUNCTION is what matters, not its spelling: descent may land on `b - 1 - a`
    ns = {}; exec(r["code"], ns)
    assert all(ns["f"](a, b) == b - a - 1 for a in range(-3, 4) for b in range(-3, 4))
    assert len(r["steps"]) == 1 and " + " in r["steps"][0]["shape"]        # one step, two classes composed


def test_refusal_restores_original():
    r = descend("def f(x):\n    return x * 3\n", ["assert f(2) == 7"])
    assert r["refused"] and r["code"] == "def f(x):\n    return x * 3\n"
