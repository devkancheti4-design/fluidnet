import subprocess, sys, textwrap
from pathlib import Path
import pytest


def build_repo(root: Path, module: str, tests: str, name: str = "pkg") -> Path:
    """A tiny pytest project: <root>/<name>/mod.py + tests/test_mod.py, with git so restores are visible."""
    (root / name).mkdir(parents=True); (root / "tests").mkdir()
    (root / name / "__init__.py").write_text("")
    (root / name / "mod.py").write_text(textwrap.dedent(module).lstrip())
    (root / "tests" / "test_mod.py").write_text(textwrap.dedent(tests).lstrip())
    (root / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "0.0.1"\n\n'
                                         '[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.fluidfix/\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=root, check=True)
    return root


@pytest.fixture
def repo_factory(tmp_path):
    def make(module, tests, name="pkg"):
        return build_repo(tmp_path / "repo", module, tests, name)
    return make
