# SPDX-License-Identifier: AGPL-3.0-or-later
"""THE OMISSION LAW — where missing code belongs, decided for one candidate line from eight measured bits.

A verbatim port of laws/omission.c (generated; every lane authored by search). The CAUSE law ranks lines
the failing test executed and is blind to the fix that ADDS code the old file never ran — a sixth of real
fixes. What can still be measured is where the path stopped looking, and that is what this rules on.

    bit 0 ENDED    bit 1 NEXT     bit 2 TARGET   bit 3 HEAD
    bit 4 PASSONLY bit 5 RAISED   bit 6 DIVERGE  bit 7 RECENT

Four lanes counted strong or weak — EDGE (ENDED / NEXT), SCOPE (TARGET+HEAD / either), CONTRAST
(DIVERGE / PASSONLY), TIME (— / RECENT) — priority = the dense lexicographic rank of (strong, weak).
RAISED is the regime, and it is a shift: without an exception the priority is halved. R0 is the lanes the
law already computes: no EDGE bit, no CONTRAST bit and not TARGET is 0. Rank 15 is unreachable, by
structure. Run beside the CAUSE law, never blended."""

BITS = ("ENDED", "NEXT", "TARGET", "HEAD", "PASSONLY", "RAISED", "DIVERGE", "RECENT")


def _ended(x):    return x & 1
def _next(x):     return 1 & (x >> 1)
def _target(x):   return 1 & (x >> 2)
def _head(x):     return 1 & (x >> 3)
def _passonly(x): return 1 & (x >> 4)
def _raised(x):   return 1 & (x >> 5)
def _diverge(x):  return 1 & (x >> 6)
def _recent(x):   return x >> 7
def _f(x):        return (x - (x >> 1)) + (x | (x + x))


def edge_w(x):  return _ended(x) | _next(x)
def scope_w(x): return _target(x) | _head(x)
def scope_s(x): return _target(x) & _head(x)
def contr_w(x): return _diverge(x) | _passonly(x)
def keep(x):    return edge_w(x) | _target(x) | contr_w(x)
def strong(x):  return _ended(x) + scope_s(x) + _diverge(x)
def nonsil(x):  return edge_w(x) + scope_w(x) + contr_w(x) + _recent(x)


def omission(x: int) -> int:
    """0..15; higher = examine first; 0 = no reach evidence."""
    return ((0 - keep(x)) & ((1 + nonsil(x) + _f(strong(x))) >> (1 - _raised(x)))) & 15


def word(bits: dict) -> int:
    return sum((1 << i) for i, k in enumerate(BITS) if bits.get(k))


def lanes(bits: dict):
    """(strong lane names, weak lane names) — as the law grades them, for display."""
    b = bits or {}
    s, w = [], []
    (s if b.get("ENDED") else w if b.get("NEXT") else []).append("EDGE")
    (s if b.get("TARGET") and b.get("HEAD") else w if b.get("TARGET") or b.get("HEAD") else []).append("SCOPE")
    (s if b.get("DIVERGE") else w if b.get("PASSONLY") else []).append("CONTRAST")
    if b.get("RECENT"): w.append("TIME")
    return s, w
