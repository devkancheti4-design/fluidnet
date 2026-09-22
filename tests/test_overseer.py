"""Two nets, one overseer. Each net is a real `fluidfix guard` process with its own dictionary."""
import textwrap
from fluidnet.overseer import score, watch, signals_of

MODULE = """
class Ledger:
    def __init__(self, entries):
        self.entries = list(entries)
    def first(self):
        return self.entries[0]
    def last(self):
        return self.entries[-1]

def closing(ledger):
    return ledger.first()

def statement(ledger):
    return f"last {ledger.last()}"
"""
TESTS = """
from pkg.mod import Ledger, closing, statement

def test_closing():
    assert closing(Ledger([5, 1, 7])) == 7

def test_statement():
    assert statement(Ledger([5, 1, 7])) == "last 7"
"""
NET_A = r'''
_ATTR = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b(?!\s*=[^=])")
def sibling(line, o):
    text = "\n".join(getattr(o, "all_lines", None) or [])
    out = []
    for m in _ATTR.finditer(line):
        recv, wrong = m.group(1), m.group(2)
        pool = set(re.findall(r"\b" + re.escape(recv) + r"\.(\w+)", text)) - {wrong}
        out += [line[:m.start(2)] + c + line[m.end(2):] for c in sorted(pool)]
    return out or [line]
register(4, "wrong-attribute-sibling", "an attribute by the wrong name", _ATTR, sibling)
'''
NET_B = r'''
_LEN = re.compile(r"\blen\(\w+\)(?!\s*-\s*1\b)")
register(7, "len-as-last-index", "len(x) where len(x) - 1 belongs", _LEN,
         lambda line, o: [line[:m.end()] + " - 1" + line[m.end():] for m in _LEN.finditer(line)])
'''


def test_signals_captured_without_touching_registry(tmp_path):
    p = tmp_path / "a.py"; p.write_text(NET_A)
    sigs = signals_of(str(p))
    assert len(sigs) == 1 and sigs[0][0] == 4 and sigs[0][1] == "wrong-attribute-sibling"


def test_routes_to_the_net_that_recognises_the_repo(repo_factory, tmp_path):
    root = repo_factory(MODULE, TESTS)
    a = tmp_path / "net_a.py"; a.write_text(NET_A)
    b = tmp_path / "net_b.py"; b.write_text(NET_B)
    order = score(root, [str(b), str(a)])
    assert order[0].dictionary == str(a) and order[0].hits > order[1].hits


def test_first_repairing_net_wins_and_the_other_is_kept(repo_factory, tmp_path):
    root = repo_factory(MODULE, TESTS)
    a = tmp_path / "net_a.py"; a.write_text(NET_A)
    b = tmp_path / "net_b.py"; b.write_text(NET_B)
    before = (root / "pkg/mod.py").read_bytes()
    r = watch(root, [str(b), str(a)], commit=False)
    assert r["winner"] == str(a), [o.output[-300:] for o in r["outcomes"]]
    assert r["outcomes"][0].status == "repaired"
    assert "ledger.last()" in r["outcomes"][0].output
    assert (root / "pkg/mod.py").read_bytes() == before          # dry-run: proposed, restored byte-exact
