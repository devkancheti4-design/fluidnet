"""Every command that runs a project's tests defaults to the project's own interpreter."""
import sys
from fluidnet.locate import project_python


def test_the_projects_venv_wins(tmp_path):
    (tmp_path / ".venv/bin").mkdir(parents=True); (tmp_path / ".venv/bin/python").write_text("")
    assert project_python(str(tmp_path)) == str((tmp_path / ".venv/bin/python").resolve())


def test_plain_venv_dir_too(tmp_path):
    (tmp_path / "venv/bin").mkdir(parents=True); (tmp_path / "venv/bin/python").write_text("")
    assert project_python(str(tmp_path)).endswith("venv/bin/python")


def test_no_venv_means_this_interpreter(tmp_path):
    assert project_python(str(tmp_path)) == sys.executable
