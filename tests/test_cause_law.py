"""The C file's own main(), in Python, against the port. The oracle is branchy and shares nothing with a lane."""
from fluidnet.cause import cause, _spec_w, _spec_s, _time_s, _time_w, _why, _symp_s, _symp_w, _f, word, BITS

BASE = [0, 5, 9, 12, 14]


def bits(x):
    return [(x >> i) & 1 for i in range(8)]


def oracle(x):
    ef, ep, im, bi, dv, fr, li, re = bits(x)
    if not ef and not im: return 0                                      # R0
    t = 2 if bi else (1 if re else 0)
    sp = 2 if (ef and ep) else (1 if (ef or im) else 0)
    wy = 2 if dv else 0
    sy = 2 if (fr and li) else (1 if (fr or li) else 0)
    s = sum(1 for g in (t, sp, wy, sy) if g == 2); w = sum(1 for g in (t, sp, wy, sy) if g == 1)
    return 1 + BASE[s] + w


def reach(x):
    ef, ep, im, bi, dv, *_ = bits(x)
    return not (im and (ef or ep or dv))


def s_of(x):
    ef, ep, im, bi, dv, fr, li, re = bits(x); return bi + (ef and ep) + dv + (fr and li)


def w_of(x):
    ef, ep, im, bi, dv, fr, li, re = bits(x)
    return int(not bi and re) + int(not (ef and ep) and (ef or im)) + int(not (fr and li) and (fr or li))


R = [x for x in range(256) if reach(x)]


def test_reachable_words():
    assert len(R) == 144


def test_against_the_table_all_144():
    assert all(cause(x) == oracle(x) for x in R)


def test_each_lane_against_its_own_spec():
    for x in R:
        ef, ep, im, bi, dv, fr, li, re = bits(x)
        assert _spec_w(x) == int(ef or im) and _spec_s(x) == int(ef and ep)
        assert _time_s(x) == bi and _time_w(x) == int(bi or re) and _why(x) == dv
        assert _symp_s(x) == int(fr and li) and _symp_w(x) == int(fr or li)
    assert all(_f(i) == BASE[i] - i for i in range(5))


def test_r0_veto_r1_lexicographic_r3_no_lane_privileged():
    for x in R:
        if not (x & 1) and not ((x >> 2) & 1): assert cause(x) == 0
    live = [x for x in R if cause(x)]
    for x in live:
        for y in live:
            if s_of(x) > s_of(y): assert cause(x) > cause(y)
            if s_of(x) == s_of(y) and w_of(x) > w_of(y): assert cause(x) > cause(y)
            if s_of(x) == s_of(y) and w_of(x) == w_of(y): assert cause(x) == cause(y)


def test_r2_monotone_import_excepted_and_range():
    for x in R:
        for i in range(8):
            if i == 2: continue
            if not (x & (1 << i)) and reach(x | (1 << i)):
                assert cause(x | (1 << i)) >= cause(x)
    assert all(0 <= cause(x) <= 15 for x in range(256))


def test_the_anchors():
    assert cause(11) == 10       # rich segment.py: ef==F, ep==0, bisect
    assert cause(12) == 7        # module constant the bad commit changed
    assert cause(1) == 2         # a shared helper every test runs
    assert cause(34) == 0        # frame on a line only one failing test runs


def test_word_packs_the_bits_in_law_order():
    assert word({"EF_ALL": 1, "EP_NONE": 1, "BISECT": 1}) == 11
    assert word({k: 1 for k in BITS}) == 255
