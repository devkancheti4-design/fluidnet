"""The three-lane root-cause locator on a project with a git history where the answer is known:
a green commit, then the commit that broke it, then an unrelated commit on top."""
import subprocess
from pathlib import Path
from fluidnet.locate import locate

RATES = "ZONES = {'domestic': 4, 'eu': 9}\n\n\ndef zone_rate(zone):\n    return ZONES[zone]\n"
QUOTE_GOOD = ("from .rates import zone_rate\n\n\ndef quote(kg, zone, express=False):\n"
              "    total = kg * zone_rate(zone)\n    if express:\n        total = total * 2\n    return total\n")
QUOTE_BAD = QUOTE_GOOD.replace("total = total * 2", "total = total + 2")            # the root cause: quote.py:7
OTHER = "def banner():\n    return 'shipwise'\n"
TESTS = ("from pkg.quote import quote\nfrom pkg.other import banner\n\n"
         "def test_plain():\n    assert quote(2, 'domestic') == 8\n\n"
         "def test_express():\n    assert quote(2, 'domestic', express=True) == 16\n\n"
         "def test_banner():\n    assert banner() == 'shipwise'\n")


def g(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def make(tmp_path, with_sibling=True):
    root = tmp_path / "r"; (root / "pkg").mkdir(parents=True); (root / "tests").mkdir()
    (root / "pkg/__init__.py").write_text(""); (root / "pkg/rates.py").write_text(RATES)
    (root / "pkg/quote.py").write_text(QUOTE_GOOD); (root / "pkg/other.py").write_text(OTHER)
    tests = TESTS if with_sibling else TESTS.replace(
        "def test_plain():\n    assert quote(2, 'domestic') == 8\n\n", "")
    (root / "tests/test_mod.py").write_text(tests)
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.fluidfix/\n")
    g(root, "init", "-q", "-b", "main"); g(root, "add", "-A"); g(root, "commit", "-qm", "green")
    (root / "pkg/quote.py").write_text(QUOTE_BAD); g(root, "commit", "-qam", "quote: tidy express")   # the bad one
    (root / "pkg/other.py").write_text(OTHER + "\n\ndef footer():\n    return 'end'\n")
    g(root, "commit", "-qam", "other: footer")                                                      # noise on top
    return root


def test_green_is_green(tmp_path):
    root = make(tmp_path)
    (root / "pkg/quote.py").write_text(QUOTE_GOOD); g(root, "commit", "-qam", "fix")
    assert locate(root).status == "green"


def test_where_when_why_agree_on_the_line(tmp_path):
    root = make(tmp_path)
    L = locate(root)
    assert L.status == "red" and L.failing == ["tests/test_mod.py::test_express"]
    top = L.where[0]
    assert top.file == "pkg/quote.py" and top.line == 7 and "total + 2" in top.source, L.render()
    # WHEN: bisect names the commit that broke it, not the noise commit on top
    assert L.when and L.when["subject"] == "quote: tidy express", L.render()
    assert any(l.startswith("when-commit") for l in top.lanes)
    # WHY: the failing run and the passing sibling part at the express branch
    assert L.why and L.why.get("diverges_at", {}).get("line") in (6, 7), L.why
    assert len(top.lanes) >= 3                                          # independent lanes agreeing


def test_no_sibling_means_the_why_lane_says_so(tmp_path):
    root = make(tmp_path, with_sibling=False)
    L = locate(root)
    assert L.status == "red" and L.where[0].file == "pkg/quote.py"
    assert L.why and "no evidence" in L.why.get("note", "")


def test_tree_untouched_by_bisect(tmp_path):
    root = make(tmp_path)
    before = (root / "pkg/quote.py").read_bytes()
    head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    locate(root)
    assert (root / "pkg/quote.py").read_bytes() == before
    assert subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout == head
    assert not subprocess.run(["git", "-C", root, "worktree", "list"], capture_output=True, text=True).stdout.count("\n") > 1
