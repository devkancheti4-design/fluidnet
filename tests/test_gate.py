"""The code-action gate: suite AND property. The decisive case is the one a suite-only gate gets wrong."""
from fluidnet.gate import gate

# a suite that only ever asks k = 1 — where the wrong placement and the right one agree
BUGGY = "def cut_at(text, k):\n    return int(k * len(text))\n"
TESTS = "from pkg.mod import cut_at\n\ndef test_cut():\n    assert cut_at('abcdef', 1) == 5\n"
WRONG = "def cut_at(text, k):\n    return int(k * len(text) - 1)\n"       # green on this suite, wrong at k = 2
RIGHT = "def cut_at(text, k):\n    return int(k * (len(text) - 1))\n"
RULES = r'''
_LEN = re.compile(r"\blen\(\w+\)(?!\s*-\s*1\b)")
register(7, "len-as-last-index", "len(x) where len(x) - 1 belongs", _LEN,
         lambda line, o: [line[:m.end()] + " - 1" + line[m.end():] for m in _LEN.finditer(line)])
def placement_preserves_value(orig, cand):
    o, c = propcheck.rhs(orig), propcheck.rhs(cand)
    intended = re.sub(r"\blen\(\w+\)", "(__L - 1)", o, count=1)
    actual = re.sub(r"\blen\(\w+\)", "__L", c, count=1)
    return propcheck.agree_over(intended, actual, grid=(1, 2, 3, 5, 8))
teach_property(7, "the candidate equals the original with len(x) -> (len(x) - 1), for every length",
               placement_preserves_value)
'''


def test_suite_alone_allows_the_wrong_fix(repo_factory):
    root = repo_factory(BUGGY, TESTS)
    assert gate(root, "pkg/mod.py", WRONG)["verdict"] == "ALLOW"        # the hole a weak suite leaves


def test_property_blocks_it_before_any_suite_run(repo_factory, tmp_path):
    root = repo_factory(BUGGY, TESTS)
    rules = tmp_path / "rules.py"; rules.write_text(RULES)
    g = gate(root, "pkg/mod.py", WRONG, dictionary=str(rules))
    assert g["verdict"] == "BLOCK" and g["suite_runs"] == 0
    assert g["property"][0]["verdict"] == "REFUTED" and "'k': 2" in g["property"][0]["why"]


def test_right_fix_is_allowed_and_proven(repo_factory, tmp_path):
    root = repo_factory(BUGGY, TESTS)
    rules = tmp_path / "rules.py"; rules.write_text(RULES)
    g = gate(root, "pkg/mod.py", RIGHT, dictionary=str(rules))
    assert g["verdict"] == "ALLOW" and g["property"][0]["verdict"] == "PROVEN"
    assert g["certificate"]["rolled_back_exact"] is True


def test_green_code_warns_nothing_to_certify(repo_factory):
    root = repo_factory(RIGHT, TESTS)
    assert gate(root, "pkg/mod.py", RIGHT)["verdict"] == "WARN"
