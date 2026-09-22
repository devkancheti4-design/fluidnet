import subprocess, sys


def run(*args):
    return subprocess.run([sys.executable, "-m", "fluidnet.cli", *args], capture_output=True, text=True)


def test_doctor_passes_in_this_env():
    r = run("doctor")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "class-property gate: present" in r.stdout


def test_teach_prints_a_class_and_a_property():
    r = run("teach")
    assert "register(" in r.stdout and "teach_property(" in r.stdout


def test_version():
    assert "fluidnet" in run("--version").stdout
