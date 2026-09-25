"""The engineers' question: do bug PATTERNS (shape + the property the fix restores) repeat? Same 565 real fixes,
same commit order, multi-line fixes included this time. Families declared before running; a fix may carry
several. A fix is KNOWN if one of its families was already seen earlier in the same repository."""
import json, re, runpy, contextlib, io
from collections import Counter, defaultdict
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("recur_real.py")
def code(ls): return [l for l in ls if l.strip() and not l.strip().startswith("#")]
FAM = {
  "None guard":            lambda a, r: re.search(r"\bis (not )?None\b|\bif not \w+\b", a) and not re.search(r"\bis (not )?None\b", r),
  "boundary comparison":   lambda a, r: (set(re.findall(r"<=|>=|(?<![<>=!])[<>](?![<>=])", a)) ^ set(re.findall(r"<=|>=|(?<![<>=!])[<>](?![<>=])", r))) != set(),
  "boolean logic":         lambda a, r: Counter(re.findall(r"\b(and|or|not)\b", a)) != Counter(re.findall(r"\b(and|or|not)\b", r)),
  "off by one":            lambda a, r: Counter(re.findall(r"[+-]\s*1\b", a)) != Counter(re.findall(r"[+-]\s*1\b", r)),
  "missing default":       lambda a, r: re.search(r"\.get\([^,()]+,|=\s*None\b|\bor\s+(\"\"|''|0|\[\]|\{\})", a) and not re.search(r"\.get\([^,()]+,|=\s*None\b", r),
  "exception handling":    lambda a, r: re.search(r"\b(try:|except\b|raise\b)", a) and not re.search(r"\b(try:|except\b)", r),
  "type check":            lambda a, r: "isinstance(" in a and "isinstance(" not in r,
  "length / emptiness":    lambda a, r: re.search(r"\blen\(|\bif not \w+:", a) and not re.search(r"\blen\(", r),
  "wrong name":            lambda a, r: None,
  "text only":             lambda a, r: None,
}
def families(row):
    A = "\n".join(code(row["plus"])); R = "\n".join(code(row["minus"]))
    out = {f for f, fn in FAM.items() if fn(A, R)}
    e, c = g["keys"](row)
    if c and c[0] in (("N",), (".N",)) and c[1] in (("N",), (".N",)): out.add("wrong name")
    if c and c == (("S",), ("S",)) and not out: out.add("text only")
    return out
by = defaultdict(list)
for repo, d, e, c, r in g["data"]: by[repo].append((d, r))
tot = known = anyfam = 0; fam_n = Counter(); fam_known = Counter(); multi_known = multi = 0
thirds = [[0, 0], [0, 0], [0, 0]]
for repo, xs in by.items():
    xs.sort(key=lambda x: x[0]); seen = set()
    for n, (d, r) in enumerate(xs):
        f = families(r); tot += 1; t = min(2, 3 * n // len(xs)); thirds[t][1] += 1
        ml = not (len(code(r["minus"])) == 1 and len(code(r["plus"])) == 1)
        if f: anyfam += 1
        if ml: multi += 1
        k = bool(f & seen)
        if k:
            known += 1; thirds[t][0] += 1; multi_known += ml
            for x in f & seen: fam_known[x] += 1
        for x in f: fam_n[x] += 1
        seen |= f
print(f"fixes carrying a named pattern: {anyfam}/{tot} = {100*anyfam/tot:.0f}%")
print(f"KNOWN at pattern level (a family already seen in that repo): {known}/{tot} = {100*known/tot:.0f}%   (token level was 88 = 16%)")
print(f"   multi-line fixes known: {multi_known}/{multi} = {100*multi_known/multi:.0f}%")
print("   by age: " + "   ".join(f"{['early','middle','late'][i]} {k}/{n} = {100*k/n:.0f}%" for i, (k, n) in enumerate(thirds)))
print("\nfamily                 fixes  repeats (seen before in that repo)")
for f in FAM: print(f"  {f:21} {fam_n[f]:>5}  {fam_known[f]:>5}")
json.dump({"any": anyfam, "known": known, "total": tot, "thirds": thirds, "fam_n": fam_n, "fam_known": fam_known}, open("recur_pattern.json", "w"))
