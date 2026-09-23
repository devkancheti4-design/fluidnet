"""The C file's own main(), in Python, against the port."""
from fluidnet.omission import omission, word, BITS

BASE = [0, 5, 9, 12, 14]


def bits(x): return [(x >> i) & 1 for i in range(8)]


def oracle(x):
    en, nx, tg, hd, po, rs, dv, rc = bits(x)
    if not en and not nx and not tg and not po and not dv: return 0            # R0
    e = 2 if en else (1 if nx else 0)
    sc = 2 if (tg and hd) else (1 if (tg or hd) else 0)
    co = 2 if dv else (1 if po else 0)
    ti = 1 if rc else 0
    s = sum(1 for g in (e, sc, co, ti) if g == 2); w = sum(1 for g in (e, sc, co, ti) if g == 1)
    r = 1 + BASE[s] + w
    return r if rs else r >> 1


def reach(x):
    en, nx, tg, hd, po, *_ = bits(x); return not ((en and nx) or (en and po))


def s_of(x): en, nx, tg, hd, po, rs, dv, rc = bits(x); return en + int(tg and hd) + dv
def w_of(x):
    en, nx, tg, hd, po, rs, dv, rc = bits(x)
    return int(not en and nx) + int(not (tg and hd) and (tg or hd)) + int(not dv and po) + rc


R = [x for x in range(256) if reach(x)]


def test_reachable_words(): assert len(R) == 160
def test_against_the_table(): assert all(omission(x) == oracle(x) for x in R)


def test_r0_r1_r3_within_a_regime():
    for x in R:
        en, nx, tg, hd, po, rs, dv, rc = bits(x)
        if not (en or nx or tg or po or dv): assert omission(x) == 0
    live = [x for x in R if omission(x)]
    for x in live:
        for y in live:
            if ((x >> 5) & 1) != ((y >> 5) & 1): continue          # RAISED scales the whole ruling
            if s_of(x) > s_of(y): assert omission(x) >= omission(y)
            if s_of(x) == s_of(y) and w_of(x) > w_of(y): assert omission(x) >= omission(y)
            if s_of(x) == s_of(y) and w_of(x) == w_of(y): assert omission(x) == omission(y)


def test_r2_monotone_raised_excepted_and_range():
    for x in R:
        for i in range(8):
            if i == 5: continue
            if not (x & (1 << i)) and reach(x | (1 << i)): assert omission(x | (1 << i)) >= omission(x)
        if not ((x >> 5) & 1): assert omission(x | 32) >= omission(x)         # monotone in RAISED too
    assert all(0 <= omission(x) <= 15 for x in range(256))
    assert max(omission(x) for x in R) == 14                                    # 15 is unreachable, by structure


def test_the_anchors():
    assert omission(45) == 10     # ENDED+TARGET+HEAD+RAISED   click bec59289d8
    assert omission(44) == 6      # TARGET+HEAD+RAISED         click f58ca3e814
    assert omission(26) == 2      # NEXT+HEAD+PASSONLY         rich 720800e6
    assert omission(128) == 0     # RECENT only
    assert omission(1) == 3       # ENDED alone, RAISED=0


def test_word_order(): assert word({"ENDED": 1, "TARGET": 1, "HEAD": 1, "RAISED": 1}) == 45
