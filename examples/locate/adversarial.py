#!/usr/bin/env python3
"""Adversarial and ambiguous cases for the locator, graded against a known truth line. Every case is a real
pytest project with git history built in a temp dir; nothing is mocked. A case that fails is reported as a
failure with the reason — that is the point of the battery."""
import os, random, shutil, subprocess, sys, tempfile, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from fluidnet.locate import locate

def g(root, *a):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)

def repo(files: dict, commits=None):
    root = Path(tempfile.mkdtemp(prefix="adv-")) / "r"; root.mkdir()
    (root / "pkg").mkdir(); (root / "tests").mkdir(); (root / "pkg/__init__.py").write_text("")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.fluidfix/\n")
    for rel, txt in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text(textwrap.dedent(txt).lstrip())
    g(root, "init", "-q", "-b", "main"); g(root, "add", "-A"); g(root, "commit", "-qm", "start")
    for msg, changes in (commits or []):
        for rel, txt in changes.items(): (root / rel).write_text(textwrap.dedent(txt).lstrip())
        g(root, "add", "-A"); g(root, "commit", "-qm", msg)
    return root

def rank_of(findings, file, lines):
    """Rank in the PRESENTED order (the law's rank, then the spectrum tie-break), ties given the group's
    mid-rank; the second value is the size of the law's own band, i.e. how many lines the law alone could
    not tell apart from the guilty one."""
    for i, f in enumerate(findings):
        if f.file == file and f.line in lines:
            grp = [j for j, x in enumerate(findings) if (x.rank, x.ochiai) == (f.rank, f.ochiai)]
            band = sum(1 for x in findings if x.rank == f.rank)
            return (grp[0] + grp[-1]) / 2 + 1, band
    return None, 0

CASES = []
def case(name, hint): 
    def deco(fn): CASES.append((name, hint, fn)); return fn
    return deco

# A. the bug is in a shared helper the assertion never names, and passing tests run it too
@case("shared helper, wrong file", "truth in pkg/util.py; the assertion is about pkg/api.py")
def _():
    root = repo({"pkg/util.py": "def scale(x, k):\n    return x * k + 1\n\n\ndef clamp(x):\n    return max(0, x)\n",
                 "pkg/api.py": "from .util import scale, clamp\n\n\ndef price(q):\n    base = scale(q, 10)\n    return clamp(base)\n\n\ndef label(q):\n    return f'{clamp(q)} units'\n",
                 "tests/test_a.py": "from pkg.api import price, label\n\n\ndef test_label():\n    assert label(3) == '3 units'\n\n\ndef test_clamp_neg():\n    from pkg.util import clamp\n    assert clamp(-2) == 0\n\n\ndef test_price():\n    assert price(2) == 20\n"})
    L = locate(root, bisect=False); return L, ("pkg/util.py", {2})

# B. two candidate lines with identical evidence — the honest answer is a tie, not a pick
@case("genuine tie", "two lines, same evidence, one guilty; a tie should be reported as a tie")
def _():
    root = repo({"pkg/m.py": "def f(a, b):\n    x = a + 1\n    y = b + 1\n    return x * y\n",
                 "tests/test_m.py": "from pkg.m import f\n\n\ndef test_f():\n    assert f(2, 3) == 2 * 4\n"})
    L = locate(root, bisect=False); return L, ("pkg/m.py", {2})

# C. a big recent commit elsewhere, after the bug — recency must not outrank real evidence
@case("decoy recency", "40 recent lines in another file; the old guilty line must still win")
def _():
    noise = "def noise():\n" + "".join(f"    v{i} = {i}\n" for i in range(40)) + "    return 0\n"
    root = repo({"pkg/m.py": "def area(w, h):\n    return w + h\n", "pkg/noise.py": "def noise():\n    return 0\n",
                 "tests/test_m.py": "from pkg.m import area\nfrom pkg.noise import noise\n\n\ndef test_area():\n    assert area(3, 4) == 12\n\n\ndef test_noise():\n    assert noise() == 0\n"},
                commits=[("big unrelated change", {"pkg/noise.py": noise})])
    L = locate(root, bisect=False); return L, ("pkg/m.py", {2})

# D. the bug is a wrong value in a module-level table — an import-time line the spectrum cannot see
@case("data, not code", "wrong constant in a dict at import time; the law keeps it alive at rank 1 only")
def _():
    root = repo({"pkg/rates.py": "RATES = {\n    'eu': 9,\n    'us': 4,\n}\n\n\ndef rate(zone):\n    return RATES[zone]\n",
                 "tests/test_r.py": "from pkg.rates import rate\n\n\ndef test_us():\n    assert rate('us') == 5\n\n\ndef test_eu():\n    assert rate('eu') == 9\n"})
    L = locate(root, bisect=False); return L, ("pkg/rates.py", {3})

# E. a missing return — the fix ADDS a line; only the omission law can point
@case("missing return (omission)", "the function mutates and never returns; the omission law should name the last line")
def _():
    root = repo({"pkg/m.py": "def add(xs, v):\n    xs.append(v)\n",
                 "tests/test_m.py": "from pkg.m import add\n\n\ndef test_add():\n    assert add([1], 9) == [1, 9]\n"})
    L = locate(root, bisect=False); return L, ("pkg/m.py", {2, 3}), "omission"

# F. the exception is raised inside the standard library; the guilty line built the bad input two lines up
@case("exception inside a library", "the frame is on the call; the truth is the line that built the argument")
def _():
    root = repo({"pkg/m.py": "import json\n\n\ndef parse(s):\n    text = s.strip() + ']'\n    doc = json.loads(text)\n    return doc\n",
                 "tests/test_m.py": "from pkg.m import parse\n\n\ndef test_parse():\n    assert parse('[1, 2]') == [1, 2]\n"})
    L = locate(root, bisect=False); return L, ("pkg/m.py", {5})

# G. a 2,000-line file, one wrong line deep inside a 60-step pipeline; passing tests also run that line
@case("2,000-line file", "one wrong line in step 37 of 60; passing tests touch the same functions")
def _():
    fns = "".join(f"def step{i}(x):\n    y = x + {i}\n    z = y - {i}\n    return z\n\n\n" for i in range(200))
    fns = fns.replace("def step37(x):\n    y = x + 37\n    z = y - 37\n", "def step37(x):\n    y = x + 37\n    z = y - 36\n")
    pipe = "def pipeline(x):\n" + "".join(f"    x = step{i}(x)\n" for i in range(60)) + "    return x\n"
    tests = "from pkg.big import pipeline, " + ", ".join(f"step{i}" for i in range(0, 60, 3)) + "\n\n\n"
    tests += "".join(f"def test_s{i}():\n    assert step{i}(1) == (1 if {i} != 37 else 2)\n\n\n" for i in range(0, 60, 3))
    tests += "def test_pipeline():\n    assert pipeline(0) == 0\n"
    root = repo({"pkg/big.py": fns + pipe, "tests/test_big.py": tests})
    L = locate(root, bisect=False)
    truth = next(i + 1 for i, l in enumerate((root / "pkg/big.py").read_text().split("\n")) if l == "    z = y - 36")
    return L, ("pkg/big.py", {truth})

# H. two unrelated bugs at once — EF_ALL demands every failing test; both guilty lines fail it
@case("two unrelated bugs", "two failing tests, two files; the law's veto should bite, and the tool must say so")
def _():
    root = repo({"pkg/a.py": "def double(x):\n    return x * 3\n", "pkg/b.py": "def half(x):\n    return x / 3\n",
                 "tests/test_ab.py": "from pkg.a import double\nfrom pkg.b import half\n\n\ndef test_double():\n    assert double(2) == 4\n\n\ndef test_half():\n    assert half(4) == 2\n"})
    L = locate(root, bisect=False); return L, ("pkg/a.py", {2})

# I. five failing tests, one cause; decoys run by only some of the failing tests are vetoed
@case("five failures, one cause", "the shared line is run by every failing test; decoys by only some")
def _():
    root = repo({"pkg/m.py": "def core(x):\n    return x - 1\n\n\ndef a(x):\n    t = x * 2\n    return core(t)\n\n\ndef b(x):\n    t = x * 3\n    return core(t)\n",
                 "tests/test_m.py": "from pkg.m import a, b, core\n\n\ndef test_a1():\n    assert a(1) == 2\n\n\ndef test_a2():\n    assert a(2) == 4\n\n\ndef test_b1():\n    assert b(1) == 3\n\n\ndef test_b2():\n    assert b(2) == 6\n\n\ndef test_core():\n    assert core(5) == 5\n"})
    L = locate(root, bisect=False); return L, ("pkg/m.py", {2})

# J. the bug was introduced 30 commits ago and the regression test only exists now — bisect with the overlay
@case("bug 30 commits deep", "the test arrives with the fix; bisect must carry it back and name the introducing commit")
def _():
    good = "def tax(net):\n    return round(net * 1.19, 2)\n"; bad = good.replace("1.19", "1.91")
    commits = [("break tax", {"pkg/m.py": bad})] + [(f"noise {i}", {f"pkg/n{i}.py": f"N{i} = {i}\n"}) for i in range(29)]
    root = repo({"pkg/m.py": good, "tests/test_m.py": "def test_nothing():\n    assert True\n"}, commits=commits)
    test = "from pkg.m import tax\n\n\ndef test_tax():\n    assert tax(100) == 119.0\n"
    (root / "tests/test_tax.py").write_text(test)
    first = subprocess.run(["git", "-C", root, "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True).stdout.strip()
    L = locate(root, bisect=True, good=first, overlay={"tests/test_tax.py": test}, lookback=40, budget_s=600)
    bug_sha = subprocess.run(["git", "-C", root, "log", "--format=%H", "--grep=break tax"], capture_output=True, text=True).stdout.strip()
    L._bug_sha = bug_sha
    return L, ("pkg/m.py", {2})

def main():
    print(f"{'case':28} {'cause':>7} {'tie':>4} {'omission':>9} {'when':>6}  verdict")
    print("-" * 96)
    passed = 0
    for name, hint, fn in CASES:
        try:
            out = fn()
        except Exception as e:
            print(f"{name:28} {'crash':>7} {'':>4} {'':>9} {'':>6}  FAIL — {type(e).__name__}: {str(e)[:50]}"); continue
        L, (file, lines), *mode = out
        cr, tie = rank_of(L.where, file, lines); orank, _ = rank_of(L.omission, file, lines)
        when_ok = ""
        if getattr(L, "_bug_sha", None):
            when_ok = "yes" if L.when and L.when["commit"] == L._bug_sha else "no"
        primary = orank if mode and mode[0] == "omission" else cr
        if primary is not None and primary <= 1: verdict, passed = "PASS", passed + 1
        elif primary is not None and primary <= 5: verdict, passed = "PARTIAL top-5", passed + 0.5
        elif primary is not None: verdict = f"WEAK rank {primary}"
        else: verdict = "FAIL — truth never a candidate" + (f" ({L.vetoed} vetoed)" if L.vetoed else "")
        if when_ok == "no": verdict += " / WHEN wrong"
        if when_ok == "yes": verdict += " / WHEN right"
        if len(L.failing_all) > len(L.failing): verdict += f" / {len(L.failing_all)} failing, judged the first"
        print(f"{name:28} {str(cr):>7} {tie:>4} {str(orank):>9} {when_ok:>6}  {verdict}")
        print(f"{'':28} {hint}")
        if L.notes: print(f"{'':28} notes: {'; '.join(L.notes)[:110]}")
    print("-" * 96); print(f"score {passed}/{len(CASES)}")

if __name__ == "__main__":
    main()
