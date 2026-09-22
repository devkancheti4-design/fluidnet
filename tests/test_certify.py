from fluidnet.certify import certify

BUGGY = """
def gross(net):
    return round(net * (1 - 0.19), 2)
"""
TESTS = """
from pkg.mod import gross

def test_gross():
    assert gross(100) == 119.0

def test_zero():
    assert gross(0) == 0
"""
RIGHT = "def gross(net):\n    return round(net * (1 + 0.19), 2)\n"
WRONG = "def gross(net):\n    return 119.0\n"                  # passes test_gross, breaks test_zero


def test_certified(repo_factory):
    root = repo_factory(BUGGY, TESTS)
    before = (root / "pkg/mod.py").read_bytes()
    c = certify(root, "pkg/mod.py", RIGHT)
    assert c.ok and c.verdict == "CERTIFIED"
    assert c.red_before == ["test_gross"]
    assert c.rolled_back_exact and (root / "pkg/mod.py").read_bytes() == before   # never left applied


def test_collateral_refused(repo_factory):
    root = repo_factory(BUGGY, TESTS)
    c = certify(root, "pkg/mod.py", WRONG)
    assert c.verdict == "COLLATERAL" and "test_zero" in c.broke and c.rolled_back_exact


def test_not_red(repo_factory):
    root = repo_factory(RIGHT, TESTS)
    c = certify(root, "pkg/mod.py", RIGHT)
    assert c.verdict == "NOT-RED"
