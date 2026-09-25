"""The body: an agent that only SUPPLIES — a pointer, a deciding test, vocabulary — while the core decides and
does every file operation. A scripted body stands in for the agent, speaking `claude -p --output-format json`."""
import json, subprocess, sys
from pathlib import Path
import pytest
from fluidnet import overseer
from fluidnet.body import Body, parse_lead, parse_code, no_difference
from fluidnet.overseer import Leads, watch_with_buggy

BUG = 'def first_line(text, pad):\n    line = ""\n    line -= pad\n    return line + text\n'
TESTS = 'from pkg.mod import first_line\n\ndef test_first_line():\n    assert first_line("a", "") == "a"\n'
RIGHT = BUG.replace("line -= pad", "line += pad")
CANCEL = BUG.replace("line -= pad", "pass")
PIN = "from pkg.mod import first_line\n\ndef test_pad_kept():\n    assert first_line('a', '  ') == '  a'\n"


def _body(tmp_path, pin=PIN, lead="LEAD: pkg/mod.py:3", vocab=None, tokens=(1200, 80)):
    script = tmp_path / "body.py"
    script.write_text(
        "import sys, json\n"
        "req = sys.stdin.read()\n"
        f"PIN, LEAD, VOCAB = {pin!r}, {lead!r}, {vocab!r}\n"
        "if 'Two different fixes' in req:\n"
        "    out = PIN if PIN.startswith('NO-DIFFERENCE') else '```python\\n' + PIN + '```'\n"
        "elif 'teach a repair engine' in req:\n"
        "    out = '```python\\n' + (VOCAB or '') + '```'\n"
        "else:\n"
        "    out = LEAD\n"
        f"print(json.dumps({{'result': out, 'usage': {{'input_tokens': {tokens[0]}, 'output_tokens': {tokens[1]}}}}}))\n")
    return Body(f"{sys.executable} {script}")


def _core(monkeypatch, repairs):
    monkeypatch.setattr(overseer, "fluidfix_has_focus", lambda: True)
    monkeypatch.setattr(overseer, "fluidfix_has_budget", lambda: True)
    monkeypatch.setattr(overseer, "score", lambda root, nets: [overseer.NetScore(n, 1, 1) for n in repairs])
    def fake_repair(root, net, rel, commit, python=None, focus=None, budget=None):
        t = repairs.get(net) if net in repairs else repairs.get(Path(net).name)
        return overseer.Outcome(net, "repaired" if t else "refused", "diff", 0 if t else 2, t or "")
    monkeypatch.setattr(overseer, "repair_file", fake_repair)


def test_the_body_speaks_json_and_is_read_for_data_only():
    assert parse_lead("text\nLEAD: src/a.py:3,5\nLEAD: src/b.py:9") == {"src/a.py": [3, 5], "src/b.py": [9]}
    assert parse_code("x\n```python\nprint(1)\n```\n") == "print(1)\n"
    assert no_difference("NO-DIFFERENCE: env values are strings") == "env values are strings"


def test_ambiguity_is_resolved_by_a_test_the_body_supplies_and_the_core_verifies(repo_factory, tmp_path, monkeypatch):
    root = repo_factory(BUG, TESTS)
    before = (root / "pkg/mod.py").read_bytes()
    _core(monkeypatch, {"augassign.py": RIGHT, "deletion.py": CANCEL})
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: pytest.fail("the lead was given; buggy must not run"))
    body = _body(tmp_path)
    r = watch_with_buggy(root, ["augassign.py", "deletion.py"], python=sys.executable, lead={"pkg/mod.py": [3]}, body=body)
    assert r["winner"] == "the EQUIV law (SHIP_A) on the oracle's test", r["stages"]
    assert r["outcomes"][-1].patched.rstrip() == RIGHT.rstrip()                 # the core chose `+=`, not `pass`
    assert any(n.startswith("body: the oracle") and "1,280 tokens" in w for n, _, w in r["stages"])
    assert (root / "pkg/mod.py").read_bytes() == before and not (root / "tests/test_fluidnet_pin.py").exists()


def test_a_body_that_finds_no_difference_leaves_it_refused(repo_factory, tmp_path, monkeypatch):
    root = repo_factory(BUG, TESTS)
    _core(monkeypatch, {"augassign.py": RIGHT, "deletion.py": CANCEL})
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: pytest.fail("buggy must not run"))
    r = watch_with_buggy(root, ["augassign.py", "deletion.py"], python=sys.executable, lead={"pkg/mod.py": [3]},
                         body=_body(tmp_path, pin="NO-DIFFERENCE: they agree on every input"))
    # a claim with no probe is no evidence: ask again, and with the budget spent, refuse (Q1, Q4, Q5)
    assert r["status"] == "ambiguous" and r["winner"] is None
    law = [w for n, _, w in r["stages"] if n == "the EQUIV law"]
    assert [w.rsplit("-> ", 1)[1] for w in law] == ["ASK", "REFUSE"]


def test_speed_mode_the_body_points_first_and_buggy_never_runs(repo_factory, tmp_path, monkeypatch):
    root = repo_factory(BUG, TESTS)
    _core(monkeypatch, {"augassign.py": RIGHT, "other.py": None})
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="CERTIFIED"))
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: pytest.fail("the body pointed; buggy must not run"))
    r = watch_with_buggy(root, ["augassign.py", "other.py"], python=sys.executable, body=_body(tmp_path), mode="speed")
    assert r["winner"] == "augassign.py"
    assert r["stages"][0][0] == "body: point at the fault" and r["stages"][1][2] == "pkg/mod.py:3"


def test_vocabulary_from_the_body_becomes_a_learned_net_that_fixes_it(repo_factory, tmp_path, monkeypatch):
    root = repo_factory(BUG, TESTS)
    learned = tmp_path / "learned"
    _core(monkeypatch, {"known.py": None})
    import fluidnet.certify as C
    monkeypatch.setattr(C, "certify", lambda *a, **k: C.Certificate(verdict="CERTIFIED"))
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: Leads(files=["pkg/mod.py"], lines={"pkg/mod.py": [3]}, status="red"))
    monkeypatch.setattr(overseer, "watch", lambda *a, **k: {"order": [], "outcomes": [], "winner": None})
    real_repair = overseer.repair_file
    def repair(root, net, rel, commit, python=None, focus=None, budget=None):
        if Path(net).parent == learned:
            return overseer.Outcome(net, "repaired", "diff", 0, RIGHT)
        return overseer.Outcome(net, "refused", "", 2, "")
    monkeypatch.setattr(overseer, "repair_file", repair)
    r = watch_with_buggy(root, ["known.py"], python=sys.executable, body=_body(tmp_path, vocab="# a rule\n"), learned=str(learned))
    saved = list(learned.glob("learned_*.py"))
    assert len(saved) == 1 and saved[0].read_text() == "# a rule\n"
    assert r["winner"] == str(saved[0])
    assert any(n.startswith("body: vocabulary") for n, _, _ in r["stages"])


EQUIV_A = BUG.replace("line -= pad", "line += pad")
EQUIV_B = BUG.replace("line -= pad", "line = line + pad")          # a different tree, the same behaviour
PROBE = ("NO-DIFFERENCE: for strings, x += y and x = x + y are the same\n```python\n"
         "from pkg.mod import first_line\nfor t, p in [('a', ''), ('a', '  '), ('', '\\t')]:\n"
         "    print(repr(first_line(t, p)))\n```")


def _ambiguous_pair(monkeypatch, a, b):
    _core(monkeypatch, {"one.py": a, "two.py": b})
    monkeypatch.setattr(overseer, "buggy_leads", lambda *a, **k: pytest.fail("the lead was given; buggy must not run"))


def test_a_measured_equivalence_ships_the_smaller_edit(repo_factory, tmp_path, monkeypatch):
    """Q3: the probe reached the differing line under both, printed identical output, twice — ship the smaller."""
    root = repo_factory(BUG, TESTS)
    _ambiguous_pair(monkeypatch, EQUIV_A, EQUIV_B)
    r = watch_with_buggy(root, ["one.py", "two.py"], python=sys.executable, lead={"pkg/mod.py": [3]},
                         body=_body(tmp_path, pin=PROBE))
    assert r["winner"] == "the EQUIV law (SHIP_A) on the oracle's probe", r["stages"]
    assert r["outcomes"][-1].patched.rstrip() == EQUIV_A.rstrip()             # `+=` is the smaller edit
    law = [w for n, _, w in r["stages"] if n == "the EQUIV law"]
    assert len(law) == 1 and "reached every differing line, identical output, stable" in law[0]


def test_a_false_equivalence_claim_is_refuted_by_its_own_probe(repo_factory, tmp_path, monkeypatch):
    """`pass` and `+=` are NOT the same; the oracle says they are. Its probe prints different output under the
    two, so the claim is no evidence: ask again, then refuse — nothing ships on the oracle's word."""
    root = repo_factory(BUG, TESTS)
    before = (root / "pkg/mod.py").read_bytes()
    _ambiguous_pair(monkeypatch, EQUIV_A, CANCEL)
    r = watch_with_buggy(root, ["one.py", "two.py"], python=sys.executable, lead={"pkg/mod.py": [3]},
                         body=_body(tmp_path, pin=PROBE), commit=True)
    assert r["status"] == "ambiguous" and r["winner"] is None
    law = [w for n, _, w in r["stages"] if n == "the EQUIV law"]
    assert [w.rsplit("-> ", 1)[1] for w in law] == ["ASK", "REFUSE"] and "different output" in law[0]
    assert (root / "pkg/mod.py").read_bytes() == before


def test_a_test_that_passes_both_separates_nothing(repo_factory, tmp_path, monkeypatch):
    root = repo_factory(BUG, TESTS)
    _ambiguous_pair(monkeypatch, EQUIV_A, CANCEL)
    both = "from pkg.mod import first_line\n\ndef test_empty_pad():\n    assert first_line('a', '') == 'a'\n"
    r = watch_with_buggy(root, ["one.py", "two.py"], python=sys.executable, lead={"pkg/mod.py": [3]},
                         body=_body(tmp_path, pin=both))
    law = [w for n, _, w in r["stages"] if n == "the EQUIV law"]
    assert [w.rsplit("-> ", 1)[1] for w in law] == ["ASK", "REFUSE"] and r["winner"] is None
    assert not list((root / "tests").glob("test_fluidnet_pin*.py"))          # the useless test is not left behind
