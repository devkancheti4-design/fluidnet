# SPDX-License-Identifier: AGPL-3.0-or-later
"""buggy — the pixel bug. Standard-library Tk only — it reads <root>/.fluidfix/locate.json, which `fluidnet float`
keeps fresh, and imports nothing from fluidnet.

    grey    suite green, or no data        amber   locating        red, twitching   suite red

Drag it onto a Finder window and drop: that folder is scanned (the icon flies home). Drop anywhere else
and it just moved. Double-click: pick a folder, for every other app. Click it when it is red: your file opens and the bug crawls down the lines the failing test actually
executed — the law's rank in the gutter as it passes — and stops on the line the CAUSE law ranked first,
naming which of the four lanes were strong and which weak. Nothing it walks is invented: the path is the
locator's own evidence. Drag to move. Quit with Ctrl-C in the terminal that started it.

usage: float_icon.py <root> [--selftest] [--crawl]     (--crawl opens the crawl at once)"""
import json, os, sys, tkinter as tk

import subprocess
from tkinter import filedialog
HOME = os.path.join(os.path.expanduser("~"), ".fluidnet"); os.makedirs(HOME, exist_ok=True)
TARGET_FILE, SCAN_NOW = os.path.join(HOME, "target"), os.path.join(HOME, "scan-now")


def root():
    try:
        t = open(TARGET_FILE).read().strip()
        if t and os.path.isdir(t):
            return t
    except OSError:
        pass
    return sys.argv[1]


ROOT = root()
JSON = lambda: os.path.join(root(), ".fluidfix", "locate.json")
BUSY = lambda: os.path.join(root(), ".fluidfix", "locating")
SELFTEST, CRAWL_NOW = "--selftest" in sys.argv, "--crawl" in sys.argv
# 9x9 pixel ladybug, two frames (legs). k black, r red, w white, . transparent
FRAMES = [["...kkk...", "..kwkwk..", ".rrkkkrr.", "krrrrrrrk", ".rkrrrkr.", "krrrrrrrk", ".rrkkkrr.", "k.rrrrr.k", "..k...k.."],
          ["...kkk...", "..kwkwk..", "krrkkkrrk", ".rrrrrrr.", "krkrrrkrk", ".rrrrrrr.", "krrkkkrrk", "..rrrrr..", ".k.....k."]]
COL = {"green": "#7a7a72", "red": "#e0443e", "busy": "#c98a12", "none": "#5f5e5a"}
SCALE = 4

win = tk.Tk(); win.overrideredirect(True); win.attributes("-topmost", True)
sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
win.geometry(f"{9*SCALE}x{9*SCALE}+{sw - 70}+{sh - 120}")
win.configure(bg="#1e1e1e")
cv = tk.Canvas(win, width=9*SCALE, height=9*SCALE, highlightthickness=0, bg="#1e1e1e"); cv.pack()
state = {"status": "none", "frame": 0, "crawl": None}


def draw_sprite(canvas, frame, body, scale, ox=0, oy=0):
    canvas.delete("bug")
    for y, row in enumerate(FRAMES[frame]):
        for x, c in enumerate(row):
            if c == ".": continue
            col = {"k": "#1b1b1b", "w": "#ffffff", "r": body}[c]
            canvas.create_rectangle(ox + x*scale, oy + y*scale, ox + (x+1)*scale, oy + (y+1)*scale, fill=col, outline="", tags="bug")


def read():
    try:
        return json.load(open(JSON()))
    except Exception:
        return None


def toast(msg, ms=2600):
    t = tk.Toplevel(win); t.overrideredirect(True); t.attributes("-topmost", True)
    tk.Label(t, text=msg, bg="#1e1e1e", fg="#e6e4de", font=("Menlo", 11), padx=10, pady=6).pack()
    t.update_idletasks()
    t.geometry(f"+{max(4, win.winfo_x() - t.winfo_reqwidth() + 36)}+{max(4, win.winfo_y() - 44)}")
    t.after(ms, t.destroy)


def finder_folder_at(x, y):
    """The folder of the Finder window under screen point (x, y) — the selected folder in it if there is
    one — or "" if the point is not on a Finder window. Asked of Finder itself; nothing is guessed."""
    script = f'''
    tell application "Finder"
        set px to {x}
        set py to {y}
        set n to count of Finder windows
        repeat with i from 1 to n
            set {{x1, y1, x2, y2}} to (bounds of Finder window i)
            if (px >= x1) and (px <= x2) and (py >= y1) and (py <= y2) then
                try
                    set sel to selection
                    if ((count of sel) > 0) and (class of (item 1 of sel) is folder) then return POSIX path of ((item 1 of sel) as alias)
                end try
                try
                    return POSIX path of ((target of Finder window i) as alias)
                end try
            end if
        end repeat
        return ""
    end tell'''
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=6)
        return r.stdout.strip()
    except Exception:
        return ""


def is_project(path):
    return os.path.isdir(os.path.join(path, "tests")) or os.path.isfile(os.path.join(path, "pyproject.toml")) \
        or os.path.isfile(os.path.join(path, "pytest.ini")) or os.path.isfile(os.path.join(path, "setup.cfg"))


def scan_folder(path):
    path = path.rstrip("/")
    if not os.path.isdir(path):
        return
    if not is_project(path):
        toast(f"buggy: {os.path.basename(path) or path} has no tests/ or pyproject — nothing to run", 3200)
        return
    open(TARGET_FILE, "w").write(path)
    open(SCAN_NOW, "w").write("1")
    toast(f"buggy: scanning {os.path.basename(path) or path} …")


def repaint():
    d = read(); busy = os.path.exists(BUSY())
    st = "busy" if busy else ("none" if not d else ("red" if d.get("status") == "red" else "green"))
    state["status"] = st
    if st == "red":
        state["frame"] ^= 1                                  # it twitches when there is a bug
    draw_sprite(cv, state["frame"], COL[st], SCALE)
    win.after(420 if st == "red" else 1200, repaint)


# ------------------------------------------------------------------ the crawl
def lanes_of(bits):
    """The CAUSE law's four lanes, as the law grades them: which were strong, which weak."""
    b = bits or {}
    strong, weak = [], []
    (strong if b.get("BISECT") else weak if b.get("RECENT") else []).append("TIME")
    (strong if b.get("EF_ALL") and b.get("EP_NONE") else weak if b.get("EF_ALL") or b.get("IMPORT") else []).append("SPECTRUM")
    if b.get("DIVERGE"): strong.append("WHY")
    (strong if b.get("FRAME") and b.get("LITERAL") else weak if b.get("FRAME") or b.get("LITERAL") else []).append("SYMPTOM")
    return strong, weak


def open_crawl(d):
    if state["crawl"] is not None:
        try: state["crawl"].destroy()
        except tk.TclError: pass
    w = d.get("walk")
    if not w:
        return
    try:
        src = open(os.path.join(root(), w["file"]), encoding="utf-8").read().split("\n")
    except OSError:
        return
    top = tk.Toplevel(win); state["crawl"] = top
    top.overrideredirect(True); top.attributes("-topmost", True)
    W, H = min(900, sw - 60), min(560, sh - 160)
    top.geometry(f"{W}x{H}+{max(10, sw - W - 40)}+{max(10, sh - H - 140)}")
    top.configure(bg="#1e1e1e")
    head = tk.Label(top, text=f"{w['file']}   —   the bug walks the lines the failing test ran",
                    bg="#1e1e1e", fg="#a6adc8", font=("Menlo", 11), anchor="w"); head.pack(fill="x", padx=10, pady=(8, 2))
    frame = tk.Frame(top, bg="#1e1e1e"); frame.pack(fill="both", expand=True, padx=10)
    text = tk.Text(frame, bg="#181825", fg="#cdd6f4", font=("Menlo", 12), wrap="none", bd=0, padx=34, pady=6,
                   insertwidth=0, selectbackground="#181825", highlightthickness=0)
    text.pack(fill="both", expand=True, side="left")
    ranks = {l["line"]: l for l in w["lines"]}
    for i, line in enumerate(src, 1):
        r = ranks.get(i)
        gutter = f"{i:4d} {('c' + str(r['rank']).rjust(2)) if r else '   '}│ "
        text.insert("end", gutter + line + "\n", ("exec",) if r else ())
    text.tag_config("exec", background="#1f1f31")
    text.tag_config("cur", background="#3a3a1e")
    text.tag_config("win", background="#5a2430")
    text.config(state="disabled")
    foot = tk.Label(top, text="", bg="#1e1e1e", fg="#cdd6f4", font=("Menlo", 11), anchor="w", justify="left")
    foot.pack(fill="x", padx=10, pady=(4, 8))
    sprite = tk.Canvas(frame, width=9*3, height=9*3, bg="#181825", highlightthickness=0)
    path = [l["line"] for l in w["lines"]] or [w["winner"]]
    if w["winner"] not in path: path.append(w["winner"])
    step_ms = max(70, min(240, 5000 // max(1, len(path))))
    pos = {"i": 0, "f": 0}

    def place_at(lineno):
        text.see(f"{lineno}.0"); text.update_idletasks()
        bb = text.bbox(f"{lineno}.0")
        if bb:
            sprite.place(x=4, y=bb[1] + max(0, (bb[3] - 27) // 2))

    def step():
        i = pos["i"]
        if i > 0:
            text.tag_remove("cur", f"{path[i-1]}.0", f"{path[i-1]}.end+1c")
        if i >= len(path):
            text.tag_add("win", f"{w['winner']}.0", f"{w['winner']}.end+1c"); place_at(w["winner"])
            draw_sprite(sprite, 0, "#e0443e", 3)
            top_f = next((l for l in w["lines"] if l["line"] == w["winner"]), None)
            strong, weak = lanes_of(top_f and top_f.get("bits"))
            foot.config(text=(f"found: {w['file']}:{w['winner']}   cause {top_f['rank'] if top_f else '?'}/15\n"
                              f"strong: {', '.join(strong) or '—'}    weak: {', '.join(weak) or '—'}    "
                              f"evidence: {', '.join(top_f['lanes']) if top_f else ''}\n"
                              + (f"when: {d['when']['commit'][:8]} “{d['when']['subject']}”   " if d.get("when") else "")
                              + (f"why: {d['why'].get('note') or ('parts at %s:%s' % (d['why']['diverges_at']['file'], d['why']['diverges_at']['line']))}" if d.get("why") else "")))
            if SELFTEST:
                top.after(600, lambda: (print("crawl ok: parked on", w["winner"]), win.destroy()))
            return
        ln = path[i]; pos["f"] ^= 1
        text.tag_add("cur", f"{ln}.0", f"{ln}.end+1c"); place_at(ln)
        draw_sprite(sprite, pos["f"], "#e0443e", 3)
        r = ranks.get(ln, {})
        foot.config(text=f"line {ln}   cause {r.get('rank', 0)}/15   {', '.join(r.get('lanes', []))}")
        pos["i"] = i + 1
        top.after(step_ms, step)

    top.bind("<Button-1>", lambda e: (top.destroy(), state.update(crawl=None)))
    text.bind("<Button-1>", lambda e: (top.destroy(), state.update(crawl=None)))
    top.after(200, step)


# ------------------------------------------------------------------ input
drag = {}
def move(e):
    drag["moved"] = True; win.geometry(f"+{win.winfo_x() + e.x - drag['x']}+{win.winfo_y() + e.y - drag['y']}")
def release(e):
    if drag.get("moved"):
        # dropped: on a Finder window it is a scan of that folder (and the icon flies home); anywhere
        # else it is just a move
        x, y = win.winfo_pointerxy()
        folder = finder_folder_at(x, y) if sys.platform == "darwin" else ""
        if folder:
            win.geometry(f"+{drag.get('hx', win.winfo_x())}+{drag.get('hy', win.winfo_y())}")
            scan_folder(folder)
        return
    d = read()
    if d and d.get("status") == "red" and d.get("walk"):
        open_crawl(d)


def pick(e):
    folder = filedialog.askdirectory(title="fluidnet — scan which project folder?")
    if folder:
        scan_folder(folder)


def press(e): drag.update(x=e.x, y=e.y, moved=False, hx=win.winfo_x(), hy=win.winfo_y())
cv.bind("<ButtonPress-1>", press); cv.bind("<B1-Motion>", move); cv.bind("<ButtonRelease-1>", release)
cv.bind("<Double-Button-1>", pick)
def explain(e):
    toast("buggy: click = crawl · double-click = pick a folder · drag onto Finder = scan it · Ctrl-C in the terminal = quit", 3600)
cv.bind("<Button-2>", explain); cv.bind("<Button-3>", explain)
def _report(exc, val, tb):
    import traceback
    with open(os.path.join(HOME, "icon.log"), "a") as fh:
        fh.write(time.strftime("%H:%M:%S ") + "".join(traceback.format_exception(exc, val, tb)))
import time
win.report_callback_exception = _report
repaint()
if CRAWL_NOW:
    win.after(300, lambda: open_crawl(read() or {}))
if SELFTEST and not CRAWL_NOW:
    win.after(800, lambda: (print("float icon ok:", state["status"]), win.destroy()))
win.mainloop()
