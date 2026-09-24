"""A suite that cannot run, or that dies, is never "green". Measured 2026-09-24: no tests collected, a
conftest that broke pytest, and a test that killed the process were all reported "suite green"."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from conftest import build_repo
from fluidnet.locate import locate

MOD = "def f():\n    return 1\n"


def run(root):
    return locate(root, bisect=False, trace=False)


def test_no_tests_collected_is_not_green(tmp_path):
    L = run(build_repo(tmp_path / "r", MOD, "# nothing here\n"))
    assert L.status == "harness" and "collected no tests" in " ".join(L.notes), L.render()


def test_a_broken_conftest_is_not_green(tmp_path):
    root = build_repo(tmp_path / "r", MOD, "from pkg.mod import f\n\ndef test_f():\n    assert f() == 2\n")
    (root / "conftest.py").write_text("def pytest_collection_modifyitems(items):\n    raise RuntimeError('broken hook')\n")
    L = run(root)
    assert L.status == "harness" and "internal error" in " ".join(L.notes), L.render()


def test_a_test_that_kills_the_process_is_not_green(tmp_path):
    root = build_repo(tmp_path / "r", MOD, "import os\nfrom pkg.mod import f\n\ndef test_f():\n    os._exit(7)\n")
    L = run(root)
    assert L.status == "harness" and "exit 7" in " ".join(L.notes), L.render()


def test_a_collection_error_is_not_green_and_names_the_error(tmp_path):
    root = build_repo(tmp_path / "r", MOD, "import nonexistent_module\nfrom pkg.mod import f\n\ndef test_f():\n    assert f() == 1\n")
    L = run(root)
    assert L.status == "harness" and "could not be collected" in " ".join(L.notes) and "nonexistent_module" in " ".join(L.notes), L.render()


def test_a_missing_interpreter_is_not_green(tmp_path):
    root = build_repo(tmp_path / "r", MOD, "from pkg.mod import f\n\ndef test_f():\n    assert f() == 1\n")
    L = locate(root, python="/no/such/python", bisect=False, trace=False)
    assert L.status == "harness" and "could not be run" in " ".join(L.notes), L.render()


def test_green_still_means_green(tmp_path):
    L = run(build_repo(tmp_path / "r", MOD, "from pkg.mod import f\n\ndef test_f():\n    assert f() == 1\n"))
    assert L.status == "green"
