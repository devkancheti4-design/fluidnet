# SPDX-License-Identifier: AGPL-3.0-or-later
"""THE CAUSE LAW — which candidate line to examine first, decided from eight measured bits and nothing else.

A verbatim port of laws/cause.c (generated; every lane authored by search). No number here is a weight:
four evidence lanes are counted STRONG or WEAK and the priority is the dense lexicographic rank of
(strong, weak) — one strong beats any number of weak because the rank says so. 0 means the line cannot
be the cause: not run by every failing test and not import-time (R0), which is the same lane as SPEC_W
negated, so the veto and the measurement are one thing.

    bit 0 EF_ALL   bit 1 EP_NONE   bit 2 IMPORT   bit 3 BISECT
    bit 4 DIVERGE  bit 5 FRAME     bit 6 LITERAL  bit 7 RECENT

tests/test_cause_law.py holds the independent branchy oracle and checks all 144 reachable words, the
lanes against their specs, R0–R3, the range on 0..255, and the four anchors — the C file's own main()."""

BITS = ("EF_ALL", "EP_NONE", "IMPORT", "BISECT", "DIVERGE", "FRAME", "LITERAL", "RECENT")


def _spec_w(x): return (x & 1) + (1 & (x >> 2))
def _spec_s(x): return (0 - (x >> 2)) + ((x + 1) >> 2)
def _time_s(x): return 1 & (x >> 3)
def _time_w(x): return (0 - ((x >> 4) << 1)) + ((x >> 3) | (x >> 7))
def _why(x):    return 1 & (x >> 4)
def _symp_s(x): return (0 - (x >> 7)) + ((x + 32) >> 7)
def _symp_w(x): return (1 - (x >> 7)) + ((x - 32) >> 7)
def _f(x):      return (x + (x - (x >> 1))) + (x + (x & (4 - x)))


def strong(x: int) -> int:
    return _time_s(x) + _spec_s(x) + _why(x) + _symp_s(x)


def nonsilent(x: int) -> int:
    return _time_w(x) + _spec_w(x) + _why(x) + _symp_w(x)


def cause(x: int) -> int:
    """0..15; higher = examine first; 0 = cannot be the cause."""
    return ((0 - _spec_w(x)) & (1 + nonsilent(x) + _f(strong(x)))) & 15


def word(bits: dict) -> int:
    """The body's whole job: turn what is known about a line into one byte."""
    return sum((1 << i) for i, k in enumerate(BITS) if bits.get(k))
