"""The compact bug store: each click file once, each bug as an edit against it."""
import json
from pathlib import Path
LB = Path(__file__).resolve().parent
FILES = json.load(open(LB / "files.json"))
def load(): return {m["id"]: m for m in json.load(open(LB / "bugs.json"))}
def orig_text(m): return FILES[m["file"]]
def mut_text(m):
    L = FILES[m["file"]].split("\n"); return "\n".join(L[:m["s"]] + m["new"] + L[m["e"]:])
