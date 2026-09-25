# The taught vocabulary for the real-repo corpus, with every class in its post-audit state.
#
# A user dictionary owns kinds 4..7 — four slots — and there are now six taught classes competing for
# them. The earlier "combined" file spent slots 4 and 5 on the two classes learned from model-written
# bugs (mutating-call, missing-separator) and thereby DROPPED flipped-boolean-operator and
# get-without-default, which are exactly what this corpus needs. The net then hit its node budget on
# click/andor-1 without ever holding the class that repairs it — a harness failure that looks like a
# refusal, which is the same mistake this project keeps having to catch.
#
#   4  flipped-boolean-operator   from the 2026-09-16 session, unchanged
#   5  get-without-default        from the 2026-09-16 session, unchanged
#   6  inverted-bare-guard        unchanged (audited 2026-09-19: sound)
#   7  len-as-last-index          FIXED: signal widened, and the PLACEMENT LAW rules where the token goes

from fluidfix.place import insert_token


# kind 4 — incident: zsh completion printed "_" for the wrong items (click shell_completion.py:467)
#   help_ = item.help and "_"      <- shipped
#   help_ = item.help or "_"       <- the fix
# The class: one boolean operator on the line is the wrong one. Every `and`<->`or` flip on the line
# is a candidate; the suite picks (the direction differs per incident).
def _flip_andor(line, o):
    out = []
    for m in re.finditer(r"\b(and|or)\b", line):
        other = "or" if m.group(1) == "and" else "and"
        out.append(line[:m.start()] + other + line[m.end():])
    return out or [line]

register(4, "flipped-boolean-operator",
         "an `and` where an `or` belongs on the line, or the reverse; the condition is wrong for the boundary case",
         re.compile(r"\b(and|or)\b"),
         _flip_andor)

# kind 5 — incident: LESS unset, None reached a str parameter (click _termui_impl.py:579)
#   less_env = os.environ.get("LESS")         <- shipped
#   less_env = os.environ.get("LESS", "")     <- the fix
# The class: a `.get(key)` with no default. The default is the neutral value of the type the caller
# expects: "" for text, 0 for a number — both are candidates for every such .get on the line.
def _get_default(line, o):
    out = []
    for m in re.finditer(r"\.get\(\s*((?:\"[^\"]*\"|'[^']*'))\s*\)", line):
        for d in ('""', "0"):
            out.append(line[:m.start()] + f".get({m.group(1)}, {d})" + line[m.end():])
    return out or [line]

register(5, "get-without-default",
         "a .get(key) with no default, so a missing key yields None where a value of the key's type is expected",
         re.compile(r"\.get\(\s*(?:\"[^\"]*\"|'[^']*')\s*\)"),
         _get_default)

# kind 6 — incident: an emptiness guard inverted, empty value fell through to value[0] (click shell_completion.py:664)
#   if value:          <- shipped
#   if not value:      <- the fix
# The class: a bare-name condition `if X:` / `elif X:` / `while X:` whose sense is inverted.
def _negate_guard(line, o):
    m = re.match(r"^(\s*)(if|elif|while) (\w+):\s*$", line)
    if not m:
        return [line]
    ind, kw, name = m.groups()
    return [f"{ind}{kw} not {name}:"]

register(6, "inverted-bare-guard",
         "a bare-name guard `if X:` that should read `if not X:`, so the empty/None case takes the wrong branch",
         re.compile(r"^\s*(?:if|elif|while) \w+:\s*$"),
         _negate_guard)


# kind 7 — the class the 2026-09-19 audit rewrote. The old signal refused `len(x) * 2` outright, and the
# old applier trailed ` - 1` after the call, which is (k*len) - 1 rather than k*(len - 1). The law decides
# placement now, which the byte-exact criterion requires: always bracketing is semantically correct and
# scores 0 of 4 against this corpus, where every lenm1 original is unparenthesised.
_LEN = re.compile(r"\blen\([\w.\[\]]+\)(?!\s*-\s*1\b)")


def _len_minus_one(line, o):
    return [insert_token(line, m.start(), m.end(), " - 1") for m in _LEN.finditer(line)] or [line]


register(7, "len-as-last-index",
         "a len(x) standing where the last valid index len(x) - 1 belongs",
         _LEN,
         _len_minus_one)
# Properties for the four taught classes — what every rewrite of each class must be true of, whatever
# code surrounds the line. Taught the same way the classes are: one statement, one checker, versioned
# beside the dictionary. Loaded with load_dictionary(), which supplies `teach_property` and `propcheck`.
#
# Why these and not properties of the repaired FUNCTION: a function property has to be written once per
# function, and only helps where someone wrote one. A class property is written once when the class is
# taught and then holds every future rewrite of that class to account — in repositories nobody has cloned
# yet, at zero suite runs.
#
# Each one is stated in English first, because the English is what a maintainer reviews.

_LEN_CALL = re.compile(r"\blen\([\w.\[\]]+\)")


# ---------------------------------------------------------------- class 7
# "The candidate must be worth exactly the original with THIS len(x) replaced by (len(x) - 1)."
#
# Every len(...) on the line becomes its own free integer on both sides, so the check ranges over every
# length those lists could ever hold rather than the lengths some test happened to use. This is the
# property that `* len(text) - 1` violated in rich while rich's own suite accepted it.
def _prop_len_minus_one(orig, cand):
    o, c = propcheck.rhs(orig), propcheck.rhs(cand)
    occ_o, occ_c = list(_LEN_CALL.finditer(o)), list(_LEN_CALL.finditer(c))
    if not occ_o or len(occ_o) != len(occ_c):
        return None, "len(...) count differs between the two lines", 0
    d = next((i for i, (x, y) in enumerate(zip(o, c)) if x != y), min(len(o), len(c)))
    k = min(sum(1 for m in occ_o if m.end() <= d), len(occ_o) - 1)

    def subst(expr, occs, target):
        out, last = [], 0
        for i, m in enumerate(occs):
            out.append(expr[last:m.start()])
            out.append(f"(__L{i} - 1)" if i == target else f"__L{i}")
            last = m.end()
        out.append(expr[last:])
        return "".join(out)

    intended, actual = subst(o, occ_o, k), subst(c, occ_c, None)
    names = sorted(set(propcheck.free_names(intended)) | set(propcheck.free_names(actual)))
    return propcheck.agree_over(intended, actual, grid=(1, 2, 3, 5, 8), names=names)


teach_property(7, "the placement must preserve the value: the candidate equals the original with "
                  "len(x) replaced by (len(x) - 1), for every length",
               _prop_len_minus_one)


# ---------------------------------------------------------------- class 4
# "Flipping one and/or TEXTUALLY must mean the same as swapping that operator at its node."
#
# `and` binds tighter than `or`, so a textual flip can regroup the expression — the same hazard class 7
# has with `- 1` under `*`. On a flattened chain (`a or b or c` is one Or of three values) the flip has
# no node-level meaning at all, and the property says so rather than guessing.
def _prop_boolean_flip(orig, cand):
    o, c = propcheck.rhs(orig), propcheck.rhs(cand)
    to = [m.start() for m in re.finditer(r"\b(and|or)\b", o)]
    tc = [m.start() for m in re.finditer(r"\b(and|or)\b", c)]
    if len(to) != len(tc):
        return None, "operator count changed", 0
    which = next((i for i, (a, b) in enumerate(zip(to, tc))
                  if o[a:a + 3].strip() != c[b:b + 3].strip()), None)
    if which is None:
        return None, "nothing flipped", 0
    intended = propcheck.nth_boolop_swapped(o, which)
    if intended is None:
        return None, "could not locate the operator", 0
    if intended == "AMB":
        return None, "flattened chain — a one-operator flip is not a node swap; rule AMB", 0
    return propcheck.agree_over(intended, c, grid=(0, 1, "", "x", (), (7,)))


teach_property(4, "the flip must not regroup: flipping the token must mean the same as swapping that "
                  "operator at its node, for every truth assignment",
               _prop_boolean_flip)


# ---------------------------------------------------------------- class 6
# "The candidate guard must be the exact negation — no value on which the two agree."
def _prop_guard_negation(orig, cand):
    o, c = propcheck.rhs(orig), propcheck.rhs(cand)
    names = sorted(set(propcheck.free_names(o)) | set(propcheck.free_names(c)))
    co, cc = compile(o, "<o>", "eval"), compile(c, "<c>", "eval")
    import itertools as _it
    n = 0
    for combo in _it.product(propcheck.TRUTH_GRID, repeat=len(names)):
        env = dict(propcheck.SAFE); env.update(dict(zip(names, combo)))
        try:
            a, b = bool(eval(co, env)), bool(eval(cc, env))
        except Exception:
            continue
        n += 1
        if a == b:
            return False, f"{dict(zip(names, combo))} -> both {a}; not a negation", n
    return True, "", n


teach_property(6, "the candidate must be the exact negation of the original guard, on every value",
               _prop_guard_negation)


# ---------------------------------------------------------------- class 5
# "Supplying a default may only change what happens when the key is ABSENT."
_GET = re.compile(r"\.get\(\s*((?:\"[^\"]*\"|'[^']*'))\s*(?:,\s*(.+?)\s*)?\)")


def _prop_get_default(orig, cand):
    o, c = propcheck.rhs(orig), propcheck.rhs(cand)
    mo = _GET.search(o)
    if not mo or mo.group(2) is not None:
        return None, "no bare .get(key) on the line", 0
    import ast as _ast
    key = _ast.literal_eval(mo.group(1))
    names = sorted(set(propcheck.free_names(o)) | set(propcheck.free_names(c)))
    co, cc = compile(o, "<o>", "eval"), compile(c, "<c>", "eval")
    n = 0
    for v in ("", "a", 0, 1, [], None, "z", 5):
        d = {key: v, "other": 9}
        env = dict(propcheck.SAFE); env.update({nm: d for nm in names})
        try:
            va = eval(co, env)
        except Exception:
            continue
        try:
            vb = eval(cc, env)
        except Exception as e:
            return False, f"{d} -> candidate raised {type(e).__name__}", n
        n += 1
        if va != vb:
            return False, f"key present in {d} -> was {va!r}, now {vb!r}", n
    return True, "", n


teach_property(5, "supplying a default may only change the key-absent case: on every mapping that holds "
                  "the key, the candidate returns what the original did",
               _prop_get_default)
