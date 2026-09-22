# SPDX-License-Identifier: AGPL-3.0-or-later
"""More than one bug at a time.

Fixing one of two bugs leaves the tests red, so a pass/fail judge throws the correct fix away. Counting
how many tests fail restores the signal: a step is kept when the failing set STRICTLY shrinks and no
passing test starts failing, and descent walks downhill until green. Only the final state is accepted;
stuck short of green means every edit is undone and the answer is still refusal. Measured 2026-09-20:
three faults from three classes never taught together, 11 suite runs, failing 5 -> 4 -> 2 -> 0.

The class property is what keeps this safe, not the descent: a looser intermediate gate reproduced the
rich incident on a weak suite until the property refused the wrong candidate 8 times over."""
from __future__ import annotations

import subprocess
import sys

from fluidfix.acts import ACTS, KINDS, Observation, act_for, candidate_cap, load_dictionary
from fluidfix.props import REFUTED, check


def shape_candidates(line: str, lineno: int, all_lines: list[str]):
    """Every repair the loaded vocabulary proposes for this line, as (kind, name, candidate)."""
    out = []
    for kind, entry in sorted(KINDS.items()):
        name, _desc, signal = entry[0], entry[1], entry[2]
        if signal is None or not signal.search(line):
            continue
        applier = ACTS.get(act_for(kind))
        if applier is None:
            continue
        obs = Observation(lineno=lineno)
        obs.kinds = [kind]
        obs.all_lines = all_lines
        try:
            proposed = applier(line, obs)
        except Exception:                                # a rule that raises is a rule that abstains
            continue
        for cand in (proposed if isinstance(proposed, list) else [proposed])[:candidate_cap()]:
            if isinstance(cand, str) and cand != line:
                out.append((kind, name, cand))
    return out


def line_candidates(line, lineno, all_lines, depth=1):
    """Candidates for a line, composed up to `depth` rewrites deep. Depth 2 is what two faults on ONE line
    need: neither single repair changes which tests fail, so the pair has to be tested together."""
    seen, out, frontier = {line}, [], [(line, ())]
    for _ in range(depth):
        nxt = []
        for base, hist in frontier:
            for kind, name, cand in shape_candidates(base, lineno, all_lines):
                if cand in seen:
                    continue
                seen.add(cand)
                rec = (cand, hist + ((kind, name, base),))
                out.append(rec); nxt.append(rec)
        frontier = nxt
    return out


def failing(code: str, tests: list[str], python: str = sys.executable) -> frozenset:
    """Which of the caller's tests fail. One subprocess."""
    harness = code + "\n\n_f = []\n"
    for i, t in enumerate(tests):
        harness += f"try:\n    {t}\nexcept Exception:\n    _f.append({i})\n"
    harness += "print(','.join(map(str, _f)))\n"
    try:
        r = subprocess.run([python, "-c", harness], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return frozenset(range(len(tests)))
    if r.returncode != 0:
        return frozenset(range(len(tests)))
    return frozenset(int(x) for x in r.stdout.strip().split(",") if x != "")


def descend(code: str, tests: list[str], dictionary: str | None = None, max_steps: int = 6,
            depth: int = 1, use_property: bool = True, python: str = sys.executable) -> dict:
    """Greedy descent over the taught vocabulary on one file's source.

    Returns {"code", "steps", "runs", "blocked_by_property", "refused"}. `code` is the repaired source on
    success and the ORIGINAL source on refusal — nothing partial ever leaves this function."""
    if dictionary:
        load_dictionary(dictionary)
    original, lines = code, code.split("\n")
    runs, blocked, steps = 1, 0, []
    cur = failing("\n".join(lines), tests, python)
    if not cur:
        return {"code": original, "steps": [], "runs": runs, "blocked_by_property": 0,
                "refused": True, "why": "not red before repair"}
    for _ in range(max_steps):
        best = None
        for i, line in enumerate(lines):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            for cand, hist in line_candidates(line, i + 1, lines, depth):
                if use_property:
                    bad = False
                    prev = line
                    for k, _n, _base in hist:
                        nxt = hist[hist.index((k, _n, _base)) + 1][2] if hist.index((k, _n, _base)) + 1 < len(hist) else cand
                        if check(k, prev, nxt)[0] == REFUTED:
                            bad = True; break
                        prev = nxt
                    if bad:
                        blocked += 1; continue
                trial = lines[:]; trial[i] = cand
                try:
                    compile("\n".join(trial), "<candidate>", "exec")
                except SyntaxError:
                    continue
                runs += 1
                got = failing("\n".join(trial), tests, python)
                if got < cur:                                 # strictly fewer, nothing new broken
                    best = (i, cand, hist, got, line); break
            if best:
                break
        if not best:
            break
        i, cand, hist, got, was = best
        lines[i] = cand
        steps.append({"kind": hist[-1][0], "shape": " + ".join(h[1] for h in hist), "line": i + 1,
                      "before": was.strip(), "after": cand.strip(), "failing": f"{len(cur)} -> {len(got)}"})
        cur = got
        if not cur:
            return {"code": "\n".join(lines), "steps": steps, "runs": runs,
                    "blocked_by_property": blocked, "refused": False}
    return {"code": original, "steps": steps, "runs": runs, "blocked_by_property": blocked,
            "refused": True, "why": "descent stalled short of green; every edit undone"}
