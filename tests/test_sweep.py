"""`fluidnet sweep` — taught work with nothing red to start from. A real lint migration, `== None` -> `is None`:
behaviour-preserving for ordinary objects, NOT for a class whose __eq__ lies, which is what the suite is for."""
import subprocess
from pathlib import Path

from fluidnet.sweep import sweep, APPLIED, BROKE, UNEXERCISED, REFUTED, AMBIGUOUS

MOD = """
class Always:
    def __eq__(self, other):
        return True


def missing(x):
    return x == None


def blank(x):
    return x == None or x == ""


def odd(x):
    return x == None


def unused(x):
    return x == None
"""
TESTS = """
from pkg.mod import missing, blank, odd, Always

def test_missing():
    assert missing(None) and not missing(1)

def test_blank():
    assert blank(None) and blank("") and not blank("a")

def test_odd():
    assert odd(Always())          # Always() == None is True; Always() is None is not
"""
RULE = '''
def _to_is(line, o):
    return re.sub(r"==(\\s*)None\\b", r"is\\1None", line)

register(4, "eq-none-to-is-none", "a comparison to None written with ==", re.compile(r"==\\s*None\\b"), _to_is)

import io as _io, tokenize as _tk
def _toks(s):
    return [t.string for t in _tk.generate_tokens(_io.StringIO(s.strip()).readline) if t.string.strip()]

def _prop(orig, cand):
    a, b = _toks(orig), _toks(cand)
    if len(a) != len(b):
        return False, "token count changed", len(a)
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y and not (x == "==" and y == "is" and i + 1 < len(a) and a[i + 1] == "None"):
            return False, f"{x!r} became {y!r}", len(a)
    return True, "", len(a)

teach_property(4, "only an == before None became is; nothing else moved", _prop)
'''


def _net(tmp_path, text=RULE, name="rules.py"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def _by_line(r):
    return {s.line: s for s in r.sites}


def test_dry_run_certifies_safe_sites_and_refuses_the_rest(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS)
    before = (root / "pkg/mod.py").read_bytes()
    r = sweep(root, [_net(tmp_path)], python=None)
    s = _by_line(r)
    assert r.status == "CERTIFIED"
    assert s[7].verdict == APPLIED and s[7].after.strip() == "return x is None"
    assert s[11].verdict == APPLIED and s[11].after.strip() == 'return x is None or x == ""'
    assert s[15].verdict == BROKE                      # the suite knows Always() == None
    assert s[19].verdict == UNEXERCISED                # no test runs unused(): the suite cannot vouch
    assert (root / "pkg/mod.py").read_bytes() == before and r.rolled_back_exact
    assert "+    return x is None" in r.diff
    assert not r.committed


def test_commit_keeps_exactly_the_certified_sites(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "config", k, v], cwd=root, check=True)
    r = sweep(root, [_net(tmp_path)], commit=True)
    assert r.committed
    lines = (root / "pkg/mod.py").read_text().split("\n")
    assert lines[6].strip() == "return x is None" and lines[10].strip() == 'return x is None or x == ""'
    assert lines[14].strip() == "return x == None" and lines[18].strip() == "return x == None"
    log = subprocess.run(["git", "log", "--format=%s"], cwd=root, capture_output=True, text=True).stdout
    assert log.splitlines()[0].startswith("fluidnet sweep: eq-none-to-is-none at 2 site(s)")
    assert subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout == ""


def test_trust_property_writes_unexercised_lines(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS)
    r = sweep(root, [_net(tmp_path)], trust_property=True)
    s = _by_line(r)
    assert s[19].verdict == APPLIED and "NOT run by any test" in s[19].why
    assert s[15].verdict == BROKE


def test_property_refutes_a_rewrite_that_does_more(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS)
    bad = RULE.replace('r"is\\1None"', 'r"is not\\1None"')
    assert bad != RULE
    r = sweep(root, [_net(tmp_path, bad)])
    assert {s.verdict for s in r.sites} == {REFUTED} and r.status == "NOTHING"
    assert r.suite_runs == 0                            # refused before a single test ran


def test_a_class_that_chooses_is_ambiguous(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS)
    two = RULE.replace('    return re.sub(r"==(\\s*)None\\b", r"is\\1None", line)',
                       '    return [re.sub(r"==(\\s*)None\\b", r"is\\1None", line), line.replace("== None", "is None ")]')
    assert two != RULE
    r = sweep(root, [_net(tmp_path, two)])
    assert r.sites and all(s.verdict == AMBIGUOUS for s in r.sites)


def test_no_property_no_sweep(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS)
    r = sweep(root, [_net(tmp_path, RULE.split("import io as _io")[0])])
    assert r.status == "NO-PROPERTY" and r.suite_runs == 0


def test_red_before_is_refused(repo_factory, tmp_path):
    root = repo_factory(MOD, TESTS + "\ndef test_red():\n    assert False\n")
    before = (root / "pkg/mod.py").read_bytes()
    r = sweep(root, [_net(tmp_path)])
    assert r.status == "RED-BEFORE" and (root / "pkg/mod.py").read_bytes() == before


def test_cli(repo_factory, tmp_path):
    import sys
    root = repo_factory(MOD, TESTS)
    bin_ = Path(sys.executable).parent / "fluidnet"
    p = subprocess.run([str(bin_), "sweep", str(root), "--net", _net(tmp_path)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "CERTIFIED: 2 site(s) certified" in p.stdout and "dry run: the tree is as you left it" in p.stdout
