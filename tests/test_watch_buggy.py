"""watch with buggy: buggy locates, fluidnet certifies buggy's proposal, the nets repair with the file named."""
import shutil, sys
import pytest
from fluidnet import overseer
from fluidnet.overseer import Leads, apply_repair, leads_from, repair_file, watch_with_buggy

BUGGY_JSON = {
    "status": "red", "seconds": "12.5",
    "mutation": [{"file": "pkg/a.py", "line": "4", "rank": "13"}, {"file": "pkg/z.py", "line": "1", "rank": "0"}],
    "when": {"commit": "abc1234def", "hunks": {"pkg/b.py": []}},
    "where": [{"file": "pkg/c.py", "line": "9", "rank": "7"}, {"file": "pkg/a.py", "line": "2", "rank": "5"}],
    "omission": [{"file": "pkg/d.py", "line": "1", "rank": "3"}],
    "repairs": [{"file": "pkg/a.py", "line": "4", "was": "    return a <= b", "now": "    return a < b", "edit": "<= → <"}],
}


def test_files_ordered_by_kind_of_evidence_and_vetoes_skipped():
    L = leads_from(BUGGY_JSON, top_files=4)
    assert L.files == ["pkg/a.py", "pkg/b.py", "pkg/c.py", "pkg/d.py"]        # experiment, commit, coverage, omission
    assert "pkg/z.py" not in L.files                                           # rank 0 is a veto
    assert L.repairs[0]["edit"] == "<= → <" and L.commit == "abc1234def" and L.seconds == 12.5
    assert leads_from(BUGGY_JSON, top_files=2).files == ["pkg/a.py", "pkg/b.py"]


def test_apply_repair_only_when_the_line_still_reads_what_buggy_saw(tmp_path):
    (tmp_path / "pkg").mkdir(); f = tmp_path / "pkg/a.py"
    f.write_text("def lt(a, b):\n    x = 1\n    y = 2\n    return a <= b\n")
    assert apply_repair(tmp_path, BUGGY_JSON["repairs"][0]).endswith("    return a < b\n")
    f.write_text("def lt(a, b):\n    return a <= b\n")                          # the line moved: stale proposal
    assert apply_repair(tmp_path, BUGGY_JSON["repairs"][0]) is None


@pytest.mark.parametrize("status", ["green", "harness"])
def test_green_and_harness_do_nothing(monkeypatch, tmp_path, status):
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: Leads(status=status))
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: pytest.fail("no blind search on " + status))
    r = watch_with_buggy(tmp_path, [])
    assert r["winner"] is None and r["outcomes"] == [] and r["status"] == status


def test_without_buggy_the_nets_search_blind(monkeypatch, tmp_path):
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: None)
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: {"order": [], "outcomes": [], "winner": "blind"})
    r = watch_with_buggy(tmp_path, [])
    assert r["winner"] == "blind" and "not installed" in r["stages"][0][2]


BUG = "def lt(a, b):\n    return a <= b\n\n\ndef add(a, b):\n    return a + b\n"
TESTS = ("from pkg.mod import lt, add\n\n"
         "def test_lt():\n    assert lt(1, 2) and not lt(2, 2)\n\n"
         "def test_add():\n    assert add(2, 3) == 5\n")


def test_a_named_file_is_repaired_by_a_shipped_class_and_restored_in_dry_run(repo_factory):
    root = repo_factory(BUG, TESTS)
    before = (root / "pkg/mod.py").read_bytes()
    o = repair_file(root, None, "pkg/mod.py", commit=False, python=sys.executable)
    assert o.status == "repaired" and "+    return a < b" in o.output, o.output
    assert (root / "pkg/mod.py").read_bytes() == before


def _buggy_with_mutation():
    bb = overseer.buggy_bin()
    return bb and overseer.buggy_has_mutation(bb)


@pytest.mark.skipif(not _buggy_with_mutation(), reason="needs buggy with the mutation lane (GitHub HEAD)")
def test_end_to_end_buggy_proposes_fluidnet_certifies(repo_factory, tmp_path):
    root = repo_factory(BUG, TESTS)
    net = tmp_path / "net.py"; net.write_text("")
    before = (root / "pkg/mod.py").read_bytes()
    r = watch_with_buggy(root, [str(net)], python=sys.executable, jobs=1, mutate_seconds=60)
    assert r["winner"] == "buggy (certified by fluidnet)", r["stages"]
    assert any(name == "certify buggy's repair" and "CERTIFIED" in what for name, _, what in r["stages"])
    assert "+ return a < b" in r["outcomes"][0].output
    assert (root / "pkg/mod.py").read_bytes() == before          # dry-run: certified, reported, not applied
