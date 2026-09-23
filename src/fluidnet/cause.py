# SPDX-License-Identifier: AGPL-3.0-or-later
"""THE CAUSE LAW, REVISION 2 — which candidate line to examine first, from eight measured bits and nothing else.

A verbatim port of laws/cause.c (generated; every lane authored by search). Revision 1 is laws/cause_r1.c.
Revision 2 changed one cell by one principle, after being judged on 26 real click fixes held out: an
unmeasured lane is silent, not weak. IMPORT keeps a line from the veto and grades nothing; 16 of the 144
reachable words moved, all of them IMPORT-set and EF_ALL-clear; replayed on the logged bits, 3 better,
0 worse, 5 unchanged. No number here is a weight:
four evidence lanes are counted STRONG or WEAK and the priority is the dense lexicographic rank of
(strong, weak) — one strong beats any number of weak because the rank says so. 0 means the line cannot
be the cause: not run by every failing test and not import-time (R0), which is the same lane as SPEC_W
negated, so the veto and the measurement are one thing.

    bit 0 EF_ALL   bit 1 EP_NONE   bit 2 IMPORT   bit 3 BISECT
    bit 4 DIVERGE  bit 5 FRAME     bit 6 LITERAL  bit 7 RECENT

tests/test_cause_law.py holds the independent branchy oracle and checks all 144 reachable words, the
lanes against their specs, R0–R3, the range on 0..255, and the four anchors — the C file's own main()."""

BITS = ("EF_ALL", "EP_NONE", "IMPORT", "BISECT", "DIVERGE", "FRAME", "LITERAL", "RECENT")


def _ef_all(x):  return x & 1
def _ep_none(x): return 1 & (x >> 1)
def _import(x):  return 1 & (x >> 2)
def _bisect(x):  return 1 & (x >> 3)
def _diverge(x): return 1 & (x >> 4)
def _frame(x):   return 1 & (x >> 5)
def _literal(x): return 1 & (x >> 6)
def _recent(x):  return x >> 7
def _f(x):       return (x + (x - (x >> 1))) + (x + (x & (4 - x)))


def keep(x: int) -> int:
    """R0: IMPORT exempts, never grades."""
    return _ef_all(x) | _import(x)


def strong(x: int) -> int:
    return (_ef_all(x) & _ep_none(x)) + _bisect(x) + _diverge(x) + (_frame(x) & _literal(x))


def nonsilent(x: int) -> int:
    """SPECTRUM is non-silent on EF_ALL — and on EF_ALL only, since revision 2."""
    return _ef_all(x) + (_bisect(x) | _recent(x)) + _diverge(x) + (_frame(x) | _literal(x))


def cause(x: int) -> int:
    """0..15; higher = examine first; 0 = cannot be the cause."""
    return ((0 - keep(x)) & (1 + nonsilent(x) + _f(strong(x)))) & 15


def word(bits: dict) -> int:
    """The body's whole job: turn what is known about a line into one byte."""
    return sum((1 << i) for i, k in enumerate(BITS) if bits.get(k))
