"""`fluidnet resolve` — two fixes pass the suite; a NEW test must choose exactly one, and fluidnet checks it."""
import subprocess
from fluidnet.resolve import resolve

BUG = """
def first_line(text, pad):
    line = ""
    line -= pad
    return line + text
"""
TESTS = """
from pkg.mod import first_line

def test_first_line():
    assert first_line("a", "") == "a"
"""
RIGHT = 'def first_line(text, pad):\n    line = ""\n    line += pad\n    return line + text\n'
CANCEL = 'def first_line(text, pad):\n    line = ""\n    pass\n    return line + text\n'    # also passes the suite
DECIDING = "from pkg.mod import first_line\n\ndef test_pad_kept():\n    assert first_line('a', '  ') == '  a'\n"


def test_a_new_test_that_separates_resolves_to_the_candidate_it_passes(repo_factory):
    root = repo_factory(BUG, TESTS)
    (root / "tests/test_pin.py").write_text(DECIDING)
    before = (root / "pkg/mod.py").read_bytes()
    r = resolve(root, "pkg/mod.py", [CANCEL, RIGHT], "tests/test_pin.py")
    assert r.verdict == "RESOLVED" and r.winner == 1 and r.passes == [False, True], r.why
    assert (root / "pkg/mod.py").read_bytes() == before and r.rolled_back_exact


def test_a_test_both_candidates_pass_decides_nothing(repo_factory):
    root = repo_factory(BUG, TESTS)
    (root / "tests/test_pin.py").write_text(TESTS)
    r = resolve(root, "pkg/mod.py", [CANCEL, RIGHT], "tests/test_pin.py")
    assert r.verdict == "UNDECIDED" and r.passes == [True, True]


def test_the_deciding_test_must_be_new_and_touch_nothing_else(repo_factory):
    root = repo_factory(BUG, TESTS)
    r = resolve(root, "pkg/mod.py", [CANCEL, RIGHT], "tests/test_mod.py")
    assert r.verdict == "NOT-NEW"
    (root / "tests/test_pin.py").write_text(DECIDING)
    (root / "tests/test_mod.py").write_text(TESTS + "\ndef test_x():\n    pass\n")
    r = resolve(root, "pkg/mod.py", [CANCEL, RIGHT], "tests/test_pin.py")
    assert r.verdict == "TOUCHED" and "tests/test_mod.py" in r.why
