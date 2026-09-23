"""WHEN on histories that look like real ones: a src layout with an editable install, a regression test that
arrives with the fix and cannot even be collected at old revisions, and a fault as old as the repository."""
import os, subprocess
from pathlib import Path
from fluidnet.locate import locate


def g(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


CALC_GOOD = "def area(w, h):\n    return w * h\n\n\ndef perimeter(w, h):\n    return 2 * (w + h)\n"
CALC_BAD = CALC_GOOD.replace("return w * h", "return w + h")
OLD_TEST = "from shapes.calc import perimeter\n\n\ndef test_perimeter():\n    assert perimeter(2, 3) == 10\n"
# the modern test file imports a helper module that only exists at HEAD: at every older revision the whole
# file fails to collect, so the new test can only travel back as a function appended to the old file
NEW_TEST = ("from shapes.calc import perimeter\nfrom shapes.helpers import UNIT\n\n\n"
            "def test_perimeter():\n    assert perimeter(2, 3) == 10\n\n\n"
            "def test_area():\n    assert area_of(2, 3) == 6\n\n\n"
            "def area_of(w, h):\n    from shapes.calc import area\n    return area(w, h)\n")


def src_repo(tmp_path, born_at_root=False):
    root = tmp_path / "r"; (root / "src/shapes").mkdir(parents=True); (root / "tests").mkdir()
    (root / "src/shapes/__init__.py").write_text("")
    (root / "src/shapes/calc.py").write_text(CALC_BAD if born_at_root else CALC_GOOD)
    (root / "tests/test_calc.py").write_text(OLD_TEST)
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.fluidfix/\n")
    g(root, "init", "-q", "-b", "main"); g(root, "add", "-A"); g(root, "commit", "-qm", "initial")
    for i in range(6):
        (root / "src/shapes/__init__.py").write_text(f"# rev {i}\n"); g(root, "commit", "-qam", f"noise {i}")
    if not born_at_root:
        (root / "src/shapes/calc.py").write_text(CALC_BAD); g(root, "commit", "-qam", "calc: simplify area")
    for i in range(6, 10):
        (root / "src/shapes/__init__.py").write_text(f"# rev {i}\n"); g(root, "commit", "-qam", f"noise {i}")
    (root / "src/shapes/helpers.py").write_text("UNIT = 'cm'\n"); (root / "tests/test_calc.py").write_text(NEW_TEST)
    g(root, "add", "-A"); g(root, "commit", "-qm", "helpers + the regression test")
    return root


def test_bisect_runs_each_revisions_own_code_under_an_editable_install(tmp_path, monkeypatch):
    """An editable install of HEAD makes every bisect worktree import HEAD's code unless the worktree's own
    src comes first. PYTHONPATH pointing at the ROOT's src stands in for the .pth of a venv."""
    root = src_repo(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    L = locate(str(root), lookback=40, budget_s=240)
    assert L.status == "red" and L.failing == ["tests/test_calc.py::test_area"], L.render()
    assert L.when and L.when.get("subject") == "calc: simplify area", (L.when, L.notes)


def test_a_fault_as_old_as_the_repository_is_a_verdict(tmp_path, monkeypatch):
    root = src_repo(tmp_path, born_at_root=True)
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    L = locate(str(root), lookback=40, budget_s=240)
    assert L.status == "red"
    assert L.when and L.when.get("commit") is None and L.when.get("older_than"), (L.when, L.notes)
    first = subprocess.run(["git", "-C", str(root), "rev-list", "--max-parents=0", "HEAD"],
                           capture_output=True, text=True).stdout.strip()
    assert L.when["older_than"]["commit"] == first, L.when
    assert "at least as old as" in L.render()
