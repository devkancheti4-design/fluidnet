"""A fault of OMISSION: the fix adds a guard the old code never had. The cause law can only point at the
line that raised; the omission law should name the same line as the place the missing code belongs,
with EDGE and SCOPE strong and the exception regime on."""
import subprocess
from fluidnet.locate import locate

MODULE = ("def label(opts):\n    v = opts.get('label')\n    return v.upper()\n\n\n"
          "def other(opts):\n    return opts.get('x', '')\n")
TESTS = ("from pkg.mod import label, other\n\n"
         "def test_label_present():\n    assert label({'label': 'a'}) == 'A'\n\n"
         "def test_label_absent():\n    assert label({}) == ''\n\n"        # AttributeError: None.upper()
         "def test_other():\n    assert other({}) == ''\n")


def test_missing_guard_is_ranked_where_it_belongs(repo_factory):
    root = repo_factory(MODULE, TESTS)
    L = locate(root, bisect=False)
    assert L.status == "red" and L.raised is True
    top = L.omission[0]
    assert (top.file, top.line) == ("pkg/mod.py", 3), [(f.file, f.line, f.rank, f.lanes) for f in L.omission]
    assert top.bits["ENDED"] == 1 and top.bits["TARGET"] == 1 and top.bits["HEAD"] == 1 and top.bits["RAISED"] == 1
    # this fixture carries more than the click anchor: the passing sibling continues where the failing run
    # ended (DIVERGE) and the file was just committed (RECENT) — three strong lanes, one weak: the top rank
    assert top.bits["DIVERGE"] == 1 and top.rank == 14
    # the cause law still speaks for itself, beside it, on the executed line
    assert L.where and L.where[0].file == "pkg/mod.py"


def test_no_exception_halves_the_omission_priority(repo_factory):
    root = repo_factory("def f(x):\n    return x + 1\n", "from pkg.mod import f\n\ndef test_f():\n    assert f(1) == 3\n")
    L = locate(root, bisect=False)
    assert L.status == "red" and L.raised is False
    assert all(f.rank <= 7 for f in L.omission)               # 14 >> 1 at most; a wrong line, not a missing one
