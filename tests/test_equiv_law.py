"""The EQUIV law, ported verbatim from laws/equiv.c, checked the way the C file's own main() checks it: an
independent branchy oracle from the principles, all 70 reachable words, Q0-Q5 on the kernel, the range, the anchors."""
import subprocess, shutil
from pathlib import Path
import pytest
from fluidnet.equiv import equiv, situation, REFUSE, SHIP_A, SHIP_B, ASK


def oracle(x):
    sa, k, e1, e2, sm, la, st = x & 1, (x >> 1) & 3, (x >> 3) & 1, (x >> 4) & 1, (x >> 5) & 1, (x >> 6) & 1, (x >> 7) & 1
    S, A = (1 if sm else 2), (0 if la else 3)
    if sa: return S                                              # Q0
    if k == 0: return A                                          # Q1
    if k == 1:                                                   # Q2
        if not st: return A
        if e1 and not e2: return 1
        if e2 and not e1: return 2
        if e1 and e2: return A
        return 0
    return S if (st and e1 and e2) else A                        # Q3


def reach(x):
    sa, k, e1, e2, la, st = x & 1, (x >> 1) & 3, (x >> 3) & 1, (x >> 4) & 1, (x >> 6) & 1, (x >> 7) & 1
    return not (k == 3 or (sa and (k or e1 or e2 or la or st)) or (k == 0 and (e1 or e2 or st)))


def test_all_70_reachable_words_match_the_principles():
    R = [x for x in range(256) if reach(x)]
    assert len(R) == 70
    assert [x for x in R if equiv(x) != oracle(x)] == []
    counts = [sum(equiv(x) == v for x in R) for v in (REFUSE, SHIP_A, SHIP_B, ASK)]
    assert counts == [30, 7, 7, 26]


def test_q4_q5_and_range_on_the_kernel():
    for x in range(256):
        v = equiv(x)
        assert 0 <= v <= 3
        if not reach(x):
            continue
        sa, k, e1, e2, la, st = x & 1, (x >> 1) & 3, (x >> 3) & 1, (x >> 4) & 1, (x >> 6) & 1, (x >> 7) & 1
        assert not (la and v == ASK)                                            # Q4: the budget is respected
        if v in (SHIP_A, SHIP_B):                                               # Q5: claims never ship
            assert sa or (k == 1 and st and (e1 ^ e2)) or (k == 2 and st and e1 and e2)


@pytest.mark.parametrize("bits,want", [
    (dict(same_ast=1, kind=0, e1=0, e2=0, smaller_a=1, last_ask=0, stable=0), SHIP_A),   # a twin
    (dict(same_ast=0, kind=1, e1=1, e2=0, smaller_a=0, last_ask=0, stable=1), SHIP_A),   # core.py:1877 live
    (dict(same_ast=0, kind=1, e1=0, e2=1, smaller_a=1, last_ask=0, stable=1), SHIP_B),   # _textwrap.py:168
    (dict(same_ast=0, kind=2, e1=1, e2=1, smaller_a=1, last_ask=0, stable=1), SHIP_A),   # _termui_impl.py:579
    (dict(same_ast=0, kind=2, e1=0, e2=1, smaller_a=0, last_ask=0, stable=1), ASK),      # probe missed a line
    (dict(same_ast=0, kind=1, e1=0, e2=0, smaller_a=0, last_ask=0, stable=1), REFUSE),   # a test both fail
    (dict(same_ast=0, kind=0, e1=0, e2=0, smaller_a=0, last_ask=1, stable=0), REFUSE)])  # no answer, spent
def test_the_anchors(bits, want):
    assert equiv(situation(**bits)) == want


@pytest.mark.skipif(not shutil.which("cc"), reason="no C compiler")
def test_the_c_kernel_agrees_with_the_port(tmp_path):
    src = Path(__file__).resolve().parents[1] / "laws" / "equiv.c"
    exe = tmp_path / "equiv"
    subprocess.run(["cc", "-O2", "-o", str(exe), str(src)], check=True, capture_output=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True)
    assert out.returncode == 0 and "TOTAL  0 violations" in out.stdout
