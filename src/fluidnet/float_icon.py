# SPDX-License-Identifier: AGPL-3.0-or-later
"""The floating icon. Standard-library Tk only, so it runs under any Python that has Tk — it reads
<root>/.fluidfix/locate.json, which `fluidnet float` keeps fresh, and never imports fluidnet itself.

    grey    suite green, or no data yet         amber   locating
    red     suite red — click for the root cause, by lanes of evidence agreeing

Drag to move. Click to expand or collapse. Right-click to quit.   usage: float_icon.py <root> [--selftest]"""
import json, os, sys, time, tkinter as tk

ROOT = sys.argv[1]
JSON = os.path.join(ROOT, ".fluidfix", "locate.json")
BUSY = os.path.join(ROOT, ".fluidfix", "locating")
SELFTEST = "--selftest" in sys.argv
COL = {"green": "#7a7a72", "red": "#c2412d", "busy": "#c98a12", "none": "#5f5e5a"}

win = tk.Tk(); win.overrideredirect(True); win.attributes("-topmost", True)
try: win.attributes("-alpha", 0.94)
except tk.TclError: pass
sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
win.geometry(f"58x58+{sw - 90}+{sh - 130}")
cv = tk.Canvas(win, width=58, height=58, highlightthickness=0, bg="#1e1e1e"); cv.pack()
dot = cv.create_oval(6, 6, 52, 52, fill=COL["none"], outline="")
txt = cv.create_text(29, 29, text="fn", fill="white", font=("Helvetica", 13, "bold"))
panel = None; state = {"status": "none"}

def read():
    try:
        d = json.load(open(JSON))
    except Exception:
        return None
    return d

def repaint():
    busy = os.path.exists(BUSY)
    d = read()
    st = "busy" if busy else ("none" if not d else ("red" if d.get("status") == "red" else "green"))
    state["status"] = st; cv.itemconfig(dot, fill=COL[st])
    n = len(d.get("failing", [])) if d else 0
    cv.itemconfig(txt, text=(str(n) if st == "red" else "fn"))
    if panel is not None:
        fill_panel(d)
    win.after(1000, repaint)

def fill_panel(d):
    body.config(state="normal"); body.delete("1.0", "end")
    if not d or d.get("status") != "red":
        body.insert("end", "suite green — nothing to locate\n" if d else "no data yet — is `fluidnet float` running?\n")
    else:
        body.insert("end", f"RED — {len(d['failing'])} failing  ·  {d.get('at', '')}\n")
        for i, f in enumerate(d.get("where", [])[:5], 1):
            body.insert("end", f"{i}. {f['file']}:{f['line']}   {f['source'].strip()[:48]}\n")
            body.insert("end", f"     [{', '.join(f['lanes'])}]  {len(f['lanes'])} lanes\n")
        w = d.get("when")
        if w: body.insert("end", f"when: {w['commit'][:8]} \"{w['subject']}\"\n")
        y = d.get("why") or {}
        if y.get("diverges_at"): body.insert("end", f"why:  parts at {y['diverges_at']['file']}:{y['diverges_at']['line']}\n")
        elif y.get("note"): body.insert("end", f"why:  {y['note']}\n")
        for n in d.get("notes", []): body.insert("end", f"note: {n}\n")
    body.config(state="disabled")

def toggle(_=None):
    global panel, body
    if panel is not None:
        panel.destroy(); panel = None; return
    panel = tk.Toplevel(win); panel.overrideredirect(True); panel.attributes("-topmost", True)
    x, y = win.winfo_x(), win.winfo_y()
    panel.geometry(f"520x230+{max(10, x - 470)}+{max(10, y - 240)}")
    body = tk.Text(panel, bg="#1e1e1e", fg="#e6e4de", font=("Menlo", 11), wrap="none", padx=10, pady=8, bd=0)
    body.pack(fill="both", expand=True); fill_panel(read())
    body.bind("<Button-1>", toggle)

drag = {}
def press(e): drag.update(x=e.x, y=e.y, moved=False)
def move(e):
    drag["moved"] = True
    win.geometry(f"+{win.winfo_x() + e.x - drag['x']}+{win.winfo_y() + e.y - drag['y']}")
def release(e):
    if not drag.get("moved"): toggle()
cv.bind("<ButtonPress-1>", press); cv.bind("<B1-Motion>", move); cv.bind("<ButtonRelease-1>", release)
cv.bind("<Button-2>", lambda e: win.destroy()); cv.bind("<Button-3>", lambda e: win.destroy())
repaint()
if SELFTEST:
    win.after(800, lambda: (print("float icon ok:", state["status"]), win.destroy()))
win.mainloop()
