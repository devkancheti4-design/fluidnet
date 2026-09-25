"""Does novel become known? 565 real maintainer fixes (click, arrow, rich, sortedcontainers), replayed in
commit order. Policy: every shape is taught the first time it is seen. A later fix is KNOWN if its shape was
seen earlier in the same repository. Two keys, declared before looking: EXACT (the same tokens changed the
same way) and CLASS (the same kind of change one taught class would own). Multi-line fixes are novel every
time. Knowledge only: a known shape is the most a vocabulary could reach, not a certified repair."""
import json, subprocess, tokenize, io, difflib
from collections import Counter, defaultdict
rows = json.load(open("/Users/kanchetidevieswar/neo/fluidfix/research/real-history-2026-09-19/remine.json"))["rows"]
OLD = "/private/tmp/claude-501/-Users-kanchetidevieswar-neo/107a7e63-6bc9-4d5b-b4a5-b0d23111954f/scratchpad/repos_full"
def date(r):
    p = subprocess.run(["git", "-C", f"{OLD}/{r['repo']}", "show", "-s", "--format=%ct", r["sha"]], capture_output=True, text=True)
    return int(p.stdout.split()[0]) if p.returncode == 0 else None
def toks(s):
    out = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(s.strip()).readline):
            if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT):
                out.append((t.type, t.string))
    except Exception:
        pass
    return out
def keys(r):
    m = [l for l in r["minus"] if l.strip()]; p = [l for l in r["plus"] if l.strip()]
    if len(m) != 1 or len(p) != 1 or r["hunks"] != 1:
        return None, None                                        # multi-line: novel every time
    a, b = toks(m[0]), toks(p[0])
    sm = difflib.SequenceMatcher(a=[x[1] for x in a], b=[x[1] for x in b], autojunk=False)
    ca, cb = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            ca += [(x, a[k - 1][1] if k else "") for k, x in enumerate(a[i1:i2], i1)]
            cb += [(x, b[k - 1][1] if k else "") for k, x in enumerate(b[j1:j2], j1)]
    if not ca and not cb:
        return None, None
    exact = (tuple(x[1] for x, _ in ca), tuple(x[1] for x, _ in cb))
    def cls(t, prev):
        ty, s = t
        if ty == tokenize.NAME and s not in ("True", "False", "None", "and", "or", "not", "in", "is"):
            return ".N" if prev == "." else "N"
        if ty == tokenize.STRING: return "S"
        if ty == tokenize.NUMBER: return "#"
        return s
    if sorted(exact[0]) == sorted(exact[1]) and len(ca) == 2 and all(x[0] == tokenize.NAME for x, _ in ca):
        return exact, ("exchange of two names",)
    return exact, (tuple(cls(*c) for c in ca), tuple(cls(*c) for c in cb))
data = []
for r in rows:
    d = date(r)
    if d is None: continue
    e, c = keys(r); data.append((r["repo"], d, e, c, r))
print(f"dated {len(data)} of {len(rows)} real fixes")
res = {"exact": [], "class": []}
by_repo = defaultdict(list)
for x in data: by_repo[x[0]].append(x)
recur = Counter(); firsts = Counter()
for repo, xs in by_repo.items():
    xs.sort(key=lambda x: x[1]); seen = {"exact": set(), "class": set()}
    for n, (_, d, e, c, r) in enumerate(xs):
        third = min(2, 3 * n // len(xs))
        for name, k in (("exact", e), ("class", c)):
            known = k is not None and k in seen[name]
            res[name].append((repo, third, known, k is not None))
            if k is not None:
                seen[name].add(k)
        if c is not None: (recur if c in seen["class"] and any(y[3] == c for y in xs[:n]) else firsts)[c] += 1
out = {}
for name, rs in res.items():
    tot = len(rs); kn = sum(1 for x in rs if x[2]); one = sum(1 for x in rs if x[3])
    kn1 = sum(1 for x in rs if x[2] and x[3])
    thirds = [(sum(1 for x in rs if x[1] == t and x[2]), sum(1 for x in rs if x[1] == t)) for t in range(3)]
    out[name] = {"known": kn, "total": tot, "one_line": one, "known_one_line": kn1, "thirds": thirds}
    print(f"\n{name.upper():6} known {kn}/{tot} = {100*kn/tot:.1f}% of all fixes · {kn1}/{one} = {100*kn1/one:.1f}% of one-line fixes")
    print("        by age of the repo:  " + "   ".join(f"{['early','middle','late'][t]} third {k}/{n} = {100*k/n:.1f}%" for t, (k, n) in enumerate(thirds)))
    for repo in by_repo:
        rr = [x for x in rs if x[0] == repo]
        print(f"        {repo:25} {sum(x[2] for x in rr):>3}/{len(rr):<3} = {100*sum(x[2] for x in rr)/len(rr):4.1f}%")
print("\nclass shapes that came back, most first (times seen after the first):")
for k, v in recur.most_common(12):
    print(f"  {v:>3}  {' '.join(k[0])!s:24} -> {' '.join(k[1]) if len(k) > 1 else ''}")
out["distinct_class_shapes"] = len(set(x[3] for x in data if x[3] is not None))
out["multi_line"] = sum(1 for x in data if x[3] is None)
print(f"\ndistinct class shapes: {out['distinct_class_shapes']}; multi-line or whitespace (novel by rule): {out['multi_line']}/{len(data)}")
json.dump(out, open("recur_real.json", "w"))
