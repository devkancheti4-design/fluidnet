#!/usr/bin/env python3
"""The held-out REAL instances, against their actual parent-commit files.

usage: real_history.py <dir-with-clones-of-click-arrow-rich-python-sortedcontainers>

For each real fix: fetch the file as it was before, find the line the class would act on, and ask whether
any candidate's ADDED lines contain every line the maintainer added (whitespace-insensitive, comments
ignored). No suite runs — this is the knowledge question: could it have proposed the maintainer's fix.
Instances whose fix does more than the class's mechanical insertion are counted as misses, not excused."""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from fluidfix.acts import ACTS, KINDS, Observation, act_for, load_dictionary

HERE = Path(__file__).resolve().parent
REPOS = Path(sys.argv[1])
load_dictionary(str(HERE / "rules.py"))
rows = json.load(open(HERE / "held_out.json"))
norm = lambda s: re.sub(r"\s+", " ", s.strip())
KIND = {"guard": 4, "import": 5}

def parent(r):
    return subprocess.run(["git", "-C", str(REPOS / r["repo"]), "show", f"{r['sha']}^:{r['file']}"],
                          capture_output=True, text=True).stdout

def anchors(r, lines):
    if r["shape"] == "import":
        return [i for i, l in enumerate(lines) if KINDS[5][2].match(l)][:1]
    names = set()
    for l in r["plus"]:
        m = re.match(r"^\s*if (?:not )?(\S+?)(?: is None)?:\s*$", l)
        if m: names.add(m.group(1))
    return [i for i, l in enumerate(lines) if any(re.match(rf"^\s*{re.escape(n)}\s*=[^=]", l) for n in names)]

print(f"{'shape':7} {'repo':7} {'sha':9} {'reached':>7} {'cands':>5}  what the maintainer added   (YES = whole fix, part = the class's own lines)")
print("-" * 100)
tally = {}
for r in rows:
    src = parent(r); lines = src.split("\n")
    added = [norm(l) for l in r["plus"] if l.strip() and not l.strip().startswith("#")
             and norm(l) not in {norm(m) for m in r["minus"]}]
    # the class's OWN part of the fix: the guard lines, or the import line — real fixes bundle more
    own = [a for a in added if (r["shape"] == "guard" and (re.match(r"^if \S+ is None:$|^if not \S+:$", a)
                                                          or re.match(r"^(?:self\.)?[A-Za-z_]\w* = .+$", a)))
           or (r["shape"] == "import" and a.startswith("import "))]
    kind = KIND[r["shape"]]; hit = part = False; ncand = 0
    for i in anchors(r, lines):
        obs = Observation(lineno=i + 1); obs.kinds = [kind]; obs.all_lines = lines
        try:
            cands = ACTS[act_for(kind)](lines[i], obs) or []
        except Exception:
            cands = []
        ncand = max(ncand, len(cands))
        for c in cands:
            got = {norm(x) for x in c.split("\n")}
            need = set(added) - {norm(lines[i])}              # a rewritten anchor is not an addition
            if need and need <= got:
                hit = True
            if own and set(own) - {norm(lines[i])} <= got:
                part = True
        if hit: break
    t = tally.setdefault(r["shape"], [0, 0, 0]); t[2] += 1; t[0] += hit; t[1] += part
    print(f"{r['shape']:7} {r['repo'][:7]:7} {r['sha'][:8]:9} {'YES' if hit else ('part' if part else 'no'):>7} {ncand:>5}  {' | '.join(added)[:60]}")
print("-" * 100)
for k, (a, b, n) in tally.items(): print(f"{k:7} whole fix reached {a}/{n}   the class's own part reached {b}/{n}")
