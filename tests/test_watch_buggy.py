"""watch with buggy: buggy locates, fluidnet certifies buggy's proposal, the nets repair with the file named."""
import shutil, sys
from pathlib import Path
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
    assert L.lines == {"pkg/a.py": [2, 4], "pkg/c.py": [9], "pkg/d.py": [1]}           # vetoed lines never focus
    assert leads_from(BUGGY_JSON, top_files=2).files == ["pkg/a.py", "pkg/b.py"]


def test_apply_repair_only_when_the_line_still_reads_what_buggy_saw(tmp_path):
    (tmp_path / "pkg").mkdir(); f = tmp_path / "pkg/a.py"
    f.write_text("def lt(a, b):\n    x = 1\n    y = 2\n    return a <= b\n")
    assert apply_repair(tmp_path, BUGGY_JSON["repairs"][0]).endswith("    return a < b\n")
    f.write_text("def lt(a, b):\n    return a <= b\n")                          # the line moved: stale proposal
    assert apply_repair(tmp_path, BUGGY_JSON["repairs"][0]) is None


def test_green_does_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: Leads(status="green"))
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: pytest.fail("no search on a green suite"))
    r = watch_with_buggy(tmp_path, [])
    assert r["winner"] is None and r["outcomes"] == [] and r["status"] == "green"


def test_buggys_harness_never_stops_fluidnet_judging_for_itself(monkeypatch, tmp_path):
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: Leads(status="harness"))
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: {"order": [], "outcomes": [], "winner": "net.py"})
    r = watch_with_buggy(tmp_path, [])
    assert r["winner"] == "net.py" and "harness" in r["stages"][0][2] and "alone" in r["stages"][0][2]


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
    assert "+    return a < b" in r["outcomes"][-1].output
    # certified is not enough: the nets search buggy's line — and where this fluidfix cannot, the stage says so
    check = [w for n, _, w in r["stages"] if n == "is buggy's repair the only fix at its line?"]
    assert check and ("confirmed" in check[0] if overseer.fluidfix_has_focus() else check[0].startswith("NOT CHECKED")), r["stages"]
    assert (root / "pkg/mod.py").read_bytes() == before          # dry-run: certified, reported, not applied


def test_a_focused_fix_that_fails_certification_is_rejected_and_the_file_is_searched(monkeypatch, tmp_path):
    """buggy's help goes ahead only if fluidnet certifies what it led to."""
    (tmp_path / "pkg").mkdir(); (tmp_path / "pkg/a.py").write_text("x = 1\n")
    leads = Leads(files=["pkg/a.py"], lines={"pkg/a.py": [1]}, status="red")
    calls = []
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: leads)
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore("net.py", 1, 1)])
    budgets = []
    monkeypatch.setattr(overseer, "fluidfix_has_budget", lambda: True)
    def fake_repair(root, net, rel, commit, python=None, focus=None, budget=None):
        calls.append("focus" if focus else "file"); budgets.append(budget)
        return overseer.Outcome("net.py", "repaired" if focus else "refused", "diff", 0, "x = 2\n" if focus else "")
    monkeypatch.setattr(overseer, "repair_file", fake_repair)
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="COLLATERAL", why="broke test_b"))
    r = watch_with_buggy(tmp_path, ["net.py"])
    assert calls == ["focus", "file"]                                   # rejected, then the whole file
    assert budgets == [None, 600]                   # buggy's lines are small; a whole file is bounded
    assert r["winner"] is None
    assert any(n == "certify the fix buggy's focus found" and w == "COLLATERAL" for n, _, w in r["stages"])
    assert (tmp_path / "pkg/a.py").read_text() == "x = 1\n"             # nothing uncertified was kept


def test_when_buggys_files_lead_nowhere_fluidnet_searches_alone(monkeypatch, tmp_path):
    leads = Leads(files=["pkg/wrong.py"], lines={}, status="red")
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: leads)
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: False)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore("net.py", 1, 1)])
    monkeypatch.setattr(overseer, "repair_file", lambda *a, **k: overseer.Outcome("net.py", "refused", "", 2))
    seen = {}
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: seen.update(k) or {"order": [], "outcomes": [], "winner": "net.py"})
    r = watch_with_buggy(tmp_path, ["net.py"])
    assert r["winner"] == "net.py" and "searches alone" in r["stages"][-1][0]
    assert seen.get("extra") == ["--budget", "600"]          # the blind search is bounded too
    r = watch_with_buggy(tmp_path, ["net.py"], fallback=False)
    assert r["winner"] is None


def test_certifier_reads_test_ids_with_spaces_in_their_parameters():
    from fluidnet import certify as C
    class O:
        root, extra_args, python = ".", [], "python"
        def clear_pyc(self): pass
        def run(self, args):
            return 1, ("FAILED tests/t.py::test_x[no-wrap mark-sentence < max] - AssertionError\n"
                       "FAILED tests/t.py::test_x[-digit after dot] - AssertionError\n")
    green, ids = C.failing_ids(O())
    assert not green and ids == {"test_x[no-wrap mark-sentence < max]", "test_x[-digit after dot]"}


def test_focus_is_buggys_top_findings_not_every_scored_line():
    d = {"status": "red", "where": [{"file": "pkg/a.py", "line": str(n), "rank": "4"} for n in range(1, 601)]}
    L = leads_from(d)
    assert L.lines["pkg/a.py"] == list(range(1, 9))        # the 8 buggy's report shows, not all 600


def test_nets_run_cheapest_first_in_each_of_buggys_files(monkeypatch, tmp_path):
    """Measured 2026-09-25: the net recognising most of the repository went first on the whole of termui.py and
    was still proving uniqueness after 49 minutes; the net owning the bug's shape repairs it in 45 s. Per file,
    nets run by their signal hits THERE, fewest first, in buggy's file order."""
    root = tmp_path / "r"; (root / "pkg").mkdir(parents=True)
    (root / "pkg/a.py").write_text("x = a.b\ny = c.d\nz = e.f and g\n")
    (root / "pkg/b.py").write_text("p = q and r\ns = t and u\nv = w.x\n")
    broad = tmp_path / "broad.py"; broad.write_text('register(4, "attr", "", re.compile(r"\\w\\.\\w"), lambda l, o: l)\n')
    narrow = tmp_path / "narrow.py"; narrow.write_text('register(4, "andor", "", re.compile(r"\\band\\b"), lambda l, o: l)\n')
    assert overseer.hits_in_scope(str(broad), root, "pkg/a.py") == 3
    assert overseer.hits_in_scope(str(narrow), root, "pkg/a.py") == 1
    assert overseer.hits_in_scope(str(narrow), root, "pkg/b.py", [1, 3]) == 1
    leads = Leads(files=["pkg/a.py", "pkg/b.py"], lines={}, status="red")
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: leads)
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: False)
    # the repository-wide ranking puts the broad net first — as it did on click
    monkeypatch.setattr(overseer, "score", lambda r, nets: [overseer.NetScore(str(broad), 1, 9),
                                                            overseer.NetScore(str(narrow), 1, 3)])
    tried = []
    monkeypatch.setattr(overseer, "repair_file",
                        lambda root, net, rel, *a, **k: tried.append((Path(net).name, rel)) or
                        overseer.Outcome(net, "refused", "", 2))
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: {"order": [], "outcomes": [], "winner": None})
    overseer.watch_with_buggy(root, [str(broad), str(narrow)])
    # a.py: narrow 1 hit, broad 3 -> narrow first; b.py: broad 1 hit, narrow 2 -> broad first. Cost is per file.
    assert tried == [("narrow.py", "pkg/a.py"), ("broad.py", "pkg/a.py"),
                     ("broad.py", "pkg/b.py"), ("narrow.py", "pkg/b.py")]


def test_the_hive_is_sized_from_buggys_own_first_run():
    """click, 2026-09-25: one worker, 241.8 s, 47 lines measured, 1,130 cut. Covering 1,177 lines at that rate
    is ~7,300 worker-seconds with headroom: five workers under the 1,800 s ceiling, cores and memory allowing."""
    first = Leads(measured=47, cut=1130, mut_seconds=241.8, workers=0)
    assert overseer.hive_size(first, cores=12, free=10 * 2 ** 30) == (5, 1454, 7062)
    # memory is a bound too: 1 GB holds two workers of 400 MB, and the ceiling then caps the time
    assert overseer.hive_size(first, cores=12, free=2 ** 30) == (2, 1800, 7062)
    d = {"status": "red", "mutation": [], "mutation_cost": {"measured": 47, "cut": 1130, "seconds": 241.8, "workers": 0}}
    L = leads_from(d)
    assert (L.measured, L.cut, L.mut_seconds, L.workers) == (47, 1130, 241.8, 0)


def test_more_buggies_when_the_first_run_left_the_target_unmeasured(monkeypatch, tmp_path):
    (tmp_path / "pkg").mkdir(); (tmp_path / "pkg/a.py").write_text("x = 1\n"); (tmp_path / "pkg/b.py").write_text("y = 1\n")
    first = Leads(files=["pkg/a.py"], lines={"pkg/a.py": [1]}, status="red", measured=47, cut=1130, mut_seconds=241.8)
    hive = Leads(files=["pkg/b.py"], lines={"pkg/b.py": [1]}, status="red", measured=1177, cut=0, mut_seconds=1400)
    runs = []
    def fake_leads(root, python=None, jobs=1, mutate_seconds=240, top_files=3, timeout=1800, mutants=None):
        runs.append((jobs, mutate_seconds, mutants)); return first if len(runs) == 1 else hive
    monkeypatch.setattr(overseer, "buggy_leads", fake_leads)
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "fluidfix_has_budget", lambda: True)
    monkeypatch.setattr(overseer, "_free_bytes", lambda: 10 * 2 ** 30)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore("net.py", 1, 1)])
    tried = []
    def fake_repair(root, net, rel, commit, python=None, focus=None, budget=None):
        tried.append((rel, "focus" if focus else "file"))
        ok = rel == "pkg/b.py"
        return overseer.Outcome(net, "repaired" if ok else "refused", "diff", 0 if ok else 2, "y = 2\n" if ok else "")
    monkeypatch.setattr(overseer, "repair_file", fake_repair)
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="CERTIFIED"))
    r = watch_with_buggy(tmp_path, ["net.py"])
    assert r["winner"] == "net.py"
    assert len(runs) == 2 and runs[1][0] > 1                        # redeployed, as a hive
    assert tried == [("pkg/a.py", "focus"), ("pkg/b.py", "focus")]   # before any whole-file search
    assert any("buggy hive" in n for n, _, _ in r["stages"])


def test_no_hive_when_nothing_was_cut(monkeypatch, tmp_path):
    (tmp_path / "pkg").mkdir(); (tmp_path / "pkg/a.py").write_text("x = 1\n")
    runs = []
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: runs.append(1) or
                        Leads(files=["pkg/a.py"], lines={}, status="red", measured=40, cut=0, mut_seconds=100))
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore("net.py", 1, 1)])
    monkeypatch.setattr(overseer, "repair_file", lambda *a, **k: overseer.Outcome("net.py", "refused", "", 2))
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: {"order": [], "outcomes": [], "winner": None})
    watch_with_buggy(tmp_path, ["net.py"])
    assert runs == [1]


def test_a_proposed_repair_leads_even_when_call_path_lines_outrank_it():
    """click, 2026-09-25, the whole target measured: five call-path lines ranked 8, the fault 7 — but the fault
    was the only line whose mutant flipped every failing test and broke nothing, i.e. buggy's one repair. The
    place leads; what goes there is still certified separately."""
    d = {"status": "red",
         "mutation": [{"file": "f/formatting.py", "line": 262, "rank": 8}, {"file": "f/decorators.py", "line": 614, "rank": 8},
                      {"file": "f/core.py", "line": 190, "rank": 8}, {"file": "f/_textwrap.py", "line": 168, "rank": 7}],
         "repairs": [{"file": "f/_textwrap.py", "line": 168, "was": "x -= i", "now": "pass", "edit": "statement → pass"}]}
    L = leads_from(d, top_files=3)
    assert L.files[0] == "f/_textwrap.py" and len(L.files) == 3
    assert 168 in L.lines["f/_textwrap.py"]


def test_a_certified_repair_with_a_rival_program_at_its_line_is_ambiguous(monkeypatch, tmp_path):
    """click, 2026-09-25: buggy's `-=` -> `pass` passed click's full suite and was certified; a net writes
    `+=` at the same line, which also passes. Two programs the tests cannot choose between: refuse."""
    (tmp_path / "pkg").mkdir(); (tmp_path / "pkg/t.py").write_text("x = 1\ny = 2\nx -= y\n")
    rep = {"file": "pkg/t.py", "line": 3, "was": "x -= y", "now": "pass", "edit": "statement → pass"}
    leads = Leads(files=["pkg/t.py"], lines={"pkg/t.py": [3]}, repairs=[rep], status="red")
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: leads)
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore("net.py", 1, 1)])
    monkeypatch.setattr(overseer, "repair_file", lambda *a, **k: overseer.Outcome(
        "net.py", "repaired", "+ x += y", 0, "x = 1\ny = 2\nx += y\n"))
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="CERTIFIED"))
    r = watch_with_buggy(tmp_path, ["net.py"], commit=True)
    assert r["winner"] is None and r["status"] == "ambiguous"
    assert any("AMBIGUOUS" in w for _, _, w in r["stages"])
    assert (tmp_path / "pkg/t.py").read_text() == "x = 1\ny = 2\nx -= y\n"      # nothing written, even with commit


def test_the_same_program_written_differently_confirms_and_the_smaller_edit_ships(monkeypatch, tmp_path):
    """click, 2026-09-25: buggy wrote `kwargs.get('cls')` where click writes `kwargs.get("cls")` — the same
    program; the net's edit changes fewer characters, so it is the one that ships."""
    (tmp_path / "pkg").mkdir(); (tmp_path / "pkg/c.py").write_text('ok = a or k.get("cls")\n')
    rep = {"file": "pkg/c.py", "line": 1, "was": 'ok = a or k.get("cls")', "now": "ok = a and k.get('cls')", "edit": "or → and"}
    leads = Leads(files=["pkg/c.py"], lines={"pkg/c.py": [1]}, repairs=[rep], status="red")
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: leads)
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore("net.py", 1, 1)])
    monkeypatch.setattr(overseer, "repair_file", lambda *a, **k: overseer.Outcome(
        "net.py", "repaired", "", 0, 'ok = a and k.get("cls")\n'))
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="CERTIFIED"))
    r = watch_with_buggy(tmp_path, ["net.py"], commit=False)
    assert r["winner"].startswith("buggy located, a net wrote the same program")
    assert r["outcomes"][-1].patched == 'ok = a and k.get("cls")\n'


def _setup_lead(monkeypatch, tmp_path, repairs):
    """repairs: {net name: patched text or None} for a focus repair at the lead."""
    (tmp_path / "pkg").mkdir(); (tmp_path / "pkg/a.py").write_text("x = 1\ny = x or 2\n")
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "fluidfix_has_budget", lambda: True)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore(n, 1, 1) for n in repairs])
    def fake_repair(root, net, rel, commit, python=None, focus=None, budget=None):
        t = repairs.get(net)
        return overseer.Outcome(net, "repaired" if t else "refused", "diff", 0 if t else 2, t or "")
    monkeypatch.setattr(overseer, "repair_file", fake_repair)
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="CERTIFIED"))


def test_a_lead_is_searched_first_and_buggy_never_runs_when_it_ships(monkeypatch, tmp_path):
    _setup_lead(monkeypatch, tmp_path, {"andor.py": "x = 1\ny = x and 2\n", "other.py": None})
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: pytest.fail("the lead was enough; buggy must not run"))
    r = watch_with_buggy(tmp_path, ["andor.py", "other.py"], lead={"pkg/a.py": [2]})
    assert r["winner"] == "andor.py"
    assert any("only one" in n and w.startswith("yes") for n, _, w in r["stages"])


def test_two_nets_writing_different_passing_programs_at_the_lead_is_ambiguous(monkeypatch, tmp_path):
    """click core.py:1877: `and` from one net, `context_settings` from another — both pass the suite."""
    _setup_lead(monkeypatch, tmp_path, {"andor.py": "x = 1\ny = x and 2\n", "sibling.py": "x = 1\ny = z or 2\n"})
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: pytest.fail("ambiguous is an answer; buggy must not run"))
    r = watch_with_buggy(tmp_path, ["andor.py", "sibling.py"], lead={"pkg/a.py": [2]}, commit=True)
    assert r["status"] == "ambiguous" and len(r["candidates"]) == 2
    assert (tmp_path / "pkg/a.py").read_text() == "x = 1\ny = x or 2\n"          # nothing written, even with commit


def test_a_lead_that_leads_nowhere_hands_over_to_buggy(monkeypatch, tmp_path):
    _setup_lead(monkeypatch, tmp_path, {"andor.py": None})
    called = []
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: called.append(1) or Leads(status="green"))
    r = watch_with_buggy(tmp_path, ["andor.py"], lead={"pkg/a.py": [2]})
    assert called == [1] and r["status"] == "green"
    assert any(n == "the lead led nowhere" for n, _, _ in r["stages"])
