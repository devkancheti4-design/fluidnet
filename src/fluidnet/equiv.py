# SPDX-License-Identifier: AGPL-3.0-or-later
"""THE EQUIV LAW — two different programs both pass the whole suite: what to do with the oracle's answer about them.

A verbatim port of laws/equiv.c (generated; every lane authored by search). The AI agent is used as an ORACLE: it
hands over one fact — a test, or a NO-DIFFERENCE claim with a probe — and the law rules on what was MEASURED of it,
never on what it said. Every SHIP is backed by one program written twice (SAME_AST), a stable test seen to separate
the two, or a stable probe that reached every differing line and printed identical output under both.

    bit 0   SAME_AST   A and B parse to the same tree
    bit 1-2 KIND       0 no usable answer, 1 a test, 2 NO-DIFFERENCE + probe
    bit 3   E1         KIND=1: the test passes under A      KIND=2: the probe executed EVERY differing line
    bit 4   E2         KIND=1: the test passes under B      KIND=2: the outputs were byte-identical
    bit 5   SMALLER_A  A's edit changes no more characters than B's
    bit 6   LAST_ASK   the ask budget is spent
    bit 7   STABLE     the re-run agreed with the first run

    equiv(x) -> 0 REFUSE · 1 SHIP_A · 2 SHIP_B · 3 ASK

tests/test_equiv_law.py holds the independent branchy oracle: all 70 reachable words, Q0–Q5, the range on 0..255,
and the seven anchors — the C file's own main()."""

REFUSE, SHIP_A, SHIP_B, ASK = 0, 1, 2, 3
VERDICTS = ("REFUSE", "SHIP_A", "SHIP_B", "ASK")


def _same(x): return x & 1
def _e1(x):   return 1 & (x >> 3)
def _e2(x):   return 1 & (x >> 4)
def _sma(x):  return 1 & (x >> 5)
def _last(x): return 1 & (x >> 6)
def _stb(x):  return x >> 7
def _k0(x):   return (1 | (x >> 2)) - ((x + 3) >> 2)
def _k1(x):   return 1 & (x >> 1)
def _k2(x):   return 1 & (x >> 2)


def _sm(x):  return 2 - _sma(x)
def _ask(x): return 3 - 3 * _last(x)
def _t1(x):  return (_e1(x) + 2 * _e2(x)) & ~(0 - (_e1(x) & _e2(x) & _last(x)))
def _g2(x):  return _stb(x) & _e1(x) & _e2(x)


def equiv(x: int) -> int:
    st, g2 = 0 - _stb(x), 0 - _g2(x)
    return (((0 - _same(x)) & _sm(x))
            | ((0 - _k0(x)) & _ask(x))
            | ((0 - _k1(x)) & ((st & _t1(x)) | (~st & _ask(x))))
            | ((0 - _k2(x)) & ((g2 & _sm(x)) | (~g2 & _ask(x))))) & 3


def situation(same_ast: bool, kind: int, e1: bool, e2: bool, smaller_a: bool, last_ask: bool, stable: bool) -> int:
    return (int(same_ast) | (kind & 3) << 1 | int(e1) << 3 | int(e2) << 4 | int(smaller_a) << 5
            | int(last_ask) << 6 | int(stable) << 7)
