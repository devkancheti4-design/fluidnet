# SPDX-License-Identifier: AGPL-3.0-or-later
"""fluidnet scan — a workspace of project folders, scanned one after another, watched live.

Dependency-free: the standard library's HTTP server and one page. Every movement on the page is a real
event from the locator's progress hook — the suite running, the files WHERE opened, the spectrum pass,
the bisect, the trace — and the ladybug parks on the line the CAUSE law ranked first. Nothing is animated
that did not happen.

    fluidnet scan <workspace> [--port 7777] [--no-bisect] [--python P]
    workspace: one project, or a folder whose subfolders are projects (a .git, a pyproject, or a tests/)."""
from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".fluidfix", "build", "dist", "node_modules"}
STATE = {"projects": [], "queue": [], "current": None, "stage": "idle", "detail": "", "files": [],
         "candidates": [], "log": [], "results": {}, "started": None}
LOCK = threading.Lock()
OPTS = {"python": sys.executable, "bisect": True}


def is_project(p: Path) -> bool:
    return p.is_dir() and ((p / ".git").exists() or (p / "pyproject.toml").exists() or (p / "tests").is_dir())


def projects(ws: Path) -> list[dict]:
    roots = [ws] if is_project(ws) else [p for p in sorted(ws.iterdir()) if p.name not in _SKIP and is_project(p)]
    out = []
    for r in roots:
        files = source_files(r)
        out.append({"name": r.name, "path": str(r), "files": len(files), "tests": (r / "tests").is_dir()})
    return out


def source_files(root: Path) -> list[str]:
    out = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if any(part in _SKIP for part in rel.parts):
            continue
        out.append(str(rel))
    return out[:600]


def _log(msg: str) -> None:
    with LOCK:
        STATE["log"].append(f"{time.strftime('%H:%M:%S')}  {msg}")
        STATE["log"] = STATE["log"][-40:]


def worker() -> None:
    from .locate import locate
    while True:
        with LOCK:
            name = STATE["queue"].pop(0) if STATE["queue"] else None
        if not name:
            time.sleep(0.3); continue
        proj = next((p for p in STATE["projects"] if p["name"] == name), None)
        if not proj:
            continue
        root = Path(proj["path"])
        with LOCK:
            STATE.update(current=name, stage="starting", detail="", candidates=[], started=time.time(),
                         files=source_files(root))
        _log(f"scanning {name}")

        def tell(stage, detail=""):
            with LOCK:
                if stage == "candidates":
                    STATE["candidates"] = detail.split()
                else:
                    STATE["stage"], STATE["detail"] = stage, detail
            _log(f"{name}: {stage} {detail}"[:120])

        try:
            L = locate(str(root), python=OPTS["python"], bisect=OPTS["bisect"], progress=tell)
            res = asdict(L); res.pop("_vetoed_list", None)
            res["where"] = res["where"][:12]
        except Exception as e:
            res = {"status": "harness", "notes": [f"{type(e).__name__}: {str(e)[:200]}"], "where": [], "failing": []}
        res["files"] = source_files(root); res["finished"] = time.time()
        with LOCK:
            STATE["results"][name] = res
            STATE.update(stage="done", detail=res.get("status", ""), current=None)
        _log(f"{name}: {res.get('status')} in {res.get('seconds', 0)}s")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/":
            b = PAGE.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if u.path == "/api/projects":
            with LOCK: return self._json(STATE["projects"])
        if u.path == "/api/status":
            with LOCK:
                return self._json({k: STATE[k] for k in ("queue", "current", "stage", "detail", "files", "candidates",
                                                          "log", "results", "started")})
        if u.path == "/api/source":
            name, rel, line = q.get("project", [""])[0], q.get("file", [""])[0], int(q.get("line", ["1"])[0])
            proj = next((p for p in STATE["projects"] if p["name"] == name), None)
            if not proj or ".." in rel:
                return self._json({"error": "no"}, 404)
            try:
                lines = Path(proj["path"], rel).read_text(encoding="utf-8").split("\n")
            except OSError:
                return self._json({"error": "unreadable"}, 404)
            lo, hi = max(1, line - 6), min(len(lines), line + 6)
            return self._json({"file": rel, "from": lo, "lines": lines[lo - 1:hi], "line": line})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/api/scan":
            names = [p["name"] for p in STATE["projects"]] if q.get("all") else q.get("project", [])
            with LOCK:
                for n in names:
                    if n not in STATE["queue"] and n != STATE["current"]:
                        STATE["queue"].append(n)
            return self._json({"queued": names}, 202)
        self._json({"error": "not found"}, 404)


def serve(workspace: str, port: int = 7777, python: str | None = None, bisect: bool = True) -> int:
    ws = Path(workspace).resolve()
    OPTS.update(python=python or sys.executable, bisect=bisect)
    STATE["projects"] = projects(ws)
    if not STATE["projects"]:
        print(f"no projects under {ws} (a project has a .git, a pyproject.toml, or a tests/)"); return 1
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"fluidnet scan — {len(STATE['projects'])} project(s) under {ws}\n  http://127.0.0.1:{port}   Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>fluidnet scan</title>
<style>
:root{--bg:#1e1e2e;--panel:#181825;--line:#313244;--txt:#cdd6f4;--dim:#a6adc8;--mute:#6c7086;--red:#f38ba8;--grn:#a6e3a1;--amb:#f9e2af;--blu:#89b4fa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid var(--line)}
header h1{font-size:16px;font-weight:600;margin:0}header .st{margin-left:auto;color:var(--dim);font-family:Menlo,monospace;font-size:12px}
main{display:grid;grid-template-columns:230px minmax(0,1fr) 420px;height:calc(100vh - 53px)}
aside,section{overflow:auto}aside{border-right:1px solid var(--line);padding:10px}
.proj{display:flex;align-items:center;gap:8px;padding:8px;border-radius:8px;cursor:pointer}.proj:hover{background:var(--panel)}
.proj .n{flex:1;font-weight:500}.proj .c{font-size:11px;color:var(--mute)}.proj.cur{background:var(--panel);outline:1px solid var(--line)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--mute)}.dot.red{background:var(--red)}.dot.grn{background:var(--grn)}.dot.amb{background:var(--amb)}
button{background:transparent;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit}button:hover{border-color:var(--dim)}
#grid{position:relative;padding:18px;display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}
.tile{width:26px;height:26px;border-radius:6px;background:#2a2b3d;border:1px solid var(--line);position:relative;transition:background .4s,box-shadow .4s}
.tile.test{background:#232336;border-style:dashed}.tile.cand{background:#45475a;border-color:var(--dim)}.tile.hot{background:#5b3a44;border-color:var(--red)}
.tile.win{background:#7a2e3e;border-color:var(--red);box-shadow:0 0 0 4px rgba(243,139,168,.25)}
.tile:hover::after{content:attr(data-f);position:absolute;left:0;top:-22px;background:#11111b;padding:2px 6px;border-radius:6px;font:11px Menlo,monospace;white-space:nowrap;z-index:5}
#bug{position:absolute;width:34px;height:34px;left:18px;top:18px;transition:left .55s cubic-bezier(.4,.1,.3,1),top .55s cubic-bezier(.4,.1,.3,1);z-index:4;filter:drop-shadow(0 2px 3px rgba(0,0,0,.6))}
#bug.walk{animation:wig .35s infinite alternate}@keyframes wig{from{transform:rotate(-7deg)}to{transform:rotate(7deg)}}
#bug.idle{animation:breathe 2.2s infinite ease-in-out}@keyframes breathe{50%{transform:scale(1.06)}}
#res{border-left:1px solid var(--line);padding:14px;font-size:13px}
.f{padding:9px 10px;border:1px solid var(--line);border-radius:10px;margin-bottom:8px;cursor:pointer}.f:hover{border-color:var(--dim)}
.f .h{font-family:Menlo,monospace;font-size:12px}.f .src{font-family:Menlo,monospace;font-size:12px;color:var(--dim);white-space:pre;overflow:hidden;text-overflow:ellipsis}
.bar{height:6px;background:#313244;border-radius:3px;margin:6px 0}.bar i{display:block;height:6px;border-radius:3px;background:var(--red)}
.lane{display:inline-block;font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 6px;margin:2px 3px 0 0;color:var(--dim)}
.k{color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:12px 0 6px}
pre.code{background:#11111b;border-radius:10px;padding:10px;font:12px Menlo,monospace;overflow:auto;margin:8px 0}pre.code b{color:var(--red)}
#log{font:11px Menlo,monospace;color:var(--mute);white-space:pre;max-height:120px;overflow:auto;border-top:1px solid var(--line);padding-top:8px;margin-top:10px}
.note{color:var(--amb);font-size:12px}
</style></head><body>
<header><svg width="30" height="30" viewBox="0 0 34 34"><ellipse cx="17" cy="19" rx="12" ry="11" fill="#e0443e"/><path d="M17 8v22" stroke="#1b1b1b" stroke-width="1.4"/><circle cx="17" cy="9" r="6" fill="#1b1b1b"/><circle cx="11" cy="16" r="2.2" fill="#1b1b1b"/><circle cx="23" cy="16" r="2.2" fill="#1b1b1b"/><circle cx="13" cy="24" r="2" fill="#1b1b1b"/><circle cx="21" cy="24" r="2" fill="#1b1b1b"/><circle cx="14.5" cy="7.5" r="1.3" fill="#fff"/><circle cx="19.5" cy="7.5" r="1.3" fill="#fff"/></svg>
<h1>fluidnet scan</h1><span id="hint" style="color:var(--dim)">pick a project, or scan all</span><span class="st" id="st">idle</span></header>
<main><aside><div style="display:flex;gap:6px;margin-bottom:8px"><button id="all" style="flex:1">scan all</button></div><div id="projs"></div></aside>
<section id="grid"><svg id="bug" class="idle" viewBox="0 0 34 34"><ellipse cx="17" cy="19" rx="12" ry="11" fill="#e0443e"/><path d="M17 8v22" stroke="#1b1b1b" stroke-width="1.4"/><circle cx="17" cy="9" r="6" fill="#1b1b1b"/><circle cx="11" cy="16" r="2.2" fill="#1b1b1b"/><circle cx="23" cy="16" r="2.2" fill="#1b1b1b"/><circle cx="13" cy="24" r="2" fill="#1b1b1b"/><circle cx="21" cy="24" r="2" fill="#1b1b1b"/><circle cx="14.5" cy="7.5" r="1.3" fill="#fff"/><circle cx="19.5" cy="7.5" r="1.3" fill="#fff"/></svg></section>
<section id="res"><div id="out" style="color:var(--dim)">Nothing scanned yet.</div><div id="log"></div></section></main>
<script>
const $=s=>document.querySelector(s);let projs=[],sel=null,lastStage='',walkTimer=null,shown=null;
const bug=$('#bug');
function tileOf(f){return document.querySelector(`.tile[data-f="${CSS.escape(f)}"]`)}
function moveTo(el){if(!el)return;const g=$('#grid').getBoundingClientRect(),r=el.getBoundingClientRect();bug.style.left=(r.left-g.left+$('#grid').scrollLeft-4)+'px';bug.style.top=(r.top-g.top+$('#grid').scrollTop-4)+'px'}
function walk(list,ms){clearInterval(walkTimer);let i=0;bug.className='walk';walkTimer=setInterval(()=>{if(i>=list.length){i=0}moveTo(tileOf(list[i++]))},ms)}
function stopWalk(){clearInterval(walkTimer);walkTimer=null;bug.className='idle'}
async function loadProjects(){projs=await (await fetch('/api/projects')).json();renderProjects({})}
function renderProjects(results,current,queue){$('#projs').innerHTML=projs.map(p=>{const r=results[p.name];const c=r?(r.status==='red'?'red':(r.status==='green'?'grn':'amb')):(current===p.name?'amb':'');return `<div class="proj ${sel===p.name?'cur':''}" data-n="${p.name}"><span class="dot ${c}"></span><span class="n">${p.name}</span><span class="c">${p.files} files${(queue||[]).includes(p.name)?' · queued':''}</span><button class="rs" title="scan">↻</button></div>`}).join('');
document.querySelectorAll('.proj').forEach(el=>{el.onclick=()=>{sel=el.dataset.n;shown=null;renderProjects(results,current,queue)};el.querySelector('.rs').onclick=e=>{e.stopPropagation();sel=el.dataset.n;shown=null;fetch('/api/scan?project='+encodeURIComponent(sel),{method:'POST'})}})}
function renderGrid(files,cands){$('#grid').querySelectorAll('.tile').forEach(t=>t.remove());const cs=new Set(cands||[]);files.forEach(f=>{const t=document.createElement('div');t.className='tile'+(f.startsWith('tests/')||f.startsWith('test/')?' test':'')+(cs.has(f)?' cand':'');t.dataset.f=f;$('#grid').appendChild(t)})}
function show(name){shown=name}
async function tick(){const s=await (await fetch('/api/status')).json();renderProjects(s.results,s.current,s.queue);$('#st').textContent=s.current?`${s.current} · ${s.stage} ${s.detail||''}`:(s.queue.length?`queued: ${s.queue.join(', ')}`:'idle');
$('#log').textContent=s.log.slice(-8).join('\n');
const name=s.current||shown||sel;const r=name?s.results[name]:null;
if(s.current){if(shown!==s.current||!$('#grid').querySelector('.tile')){shown=s.current;renderGrid(s.files,s.candidates);$('#out').innerHTML=`<div class="k">scanning ${s.current}</div><div style="color:var(--dim)">the ladybug follows what the scan is actually doing</div>`}
if(s.candidates.length)s.candidates.forEach(f=>{const t=tileOf(f);if(t)t.classList.add('cand')});
const key=s.stage+'|'+s.candidates.join(',');if(key!==lastStage){lastStage=key;
 if(s.stage==='suite'){walk(s.files.filter(f=>f.startsWith('tests/')||f.startsWith('test/')).concat(s.files.slice(0,8)),420)}
 else if(s.stage==='where'||s.stage==='spectrum'){walk(s.candidates.length?s.candidates:s.files.slice(0,12),380);if(s.stage==='spectrum')$('#grid').querySelectorAll('.tile').forEach(t=>{if(!t.classList.contains('test'))t.classList.add('hot')})}
 else if(s.stage==='when'||s.stage==='why'){walk(s.candidates.length?s.candidates:s.files.slice(0,6),650)}}}
else{const pick=sel||Object.keys(s.results).sort((a,b)=>s.results[b].finished-s.results[a].finished)[0];const rr=pick?s.results[pick]:null;
 if(rr&&shown!==pick+'#done'){shown=pick+'#done';lastStage='';stopWalk();renderGrid(rr.files||[],[]);renderResult(pick,rr)}}}
function renderResult(name,r){const o=$('#out');if(r.status==='green'){o.innerHTML=`<div class="k">${name}</div><div style="color:var(--grn)">suite green — nothing to locate</div>`;return}
if(r.status!=='red'){o.innerHTML=`<div class="k">${name}</div><div class="note">${(r.notes||[]).join('<br>')}</div>`;return}
const top=r.where[0];if(top){const t=tileOf(top.file);if(t){t.classList.add('win');moveTo(t)}}
o.innerHTML=`<div class="k">${name} · ${r.failing.length} failing</div><div style="font-family:Menlo,monospace;font-size:12px;color:var(--dim);margin-bottom:8px">${r.failing.slice(0,3).join('<br>')}</div>
<div class="k">root cause · by the cause law</div>`+r.where.slice(0,6).map((f,i)=>`<div class="f" data-i="${i}"><div class="h">${i+1}. ${f.file}:${f.line}</div><div class="src">${(f.source||'').trim().replace(/</g,'&lt;')}</div><div class="bar"><i style="width:${(f.rank/15*100)|0}%"></i></div><div>cause ${f.rank}/15 ${f.lanes.map(l=>`<span class="lane">${l}</span>`).join('')}</div></div>`).join('')
+(r.vetoed?`<div class="note">${r.vetoed} candidate(s) vetoed by the law: not run by every failing test, not import-time</div>`:'')
+(r.law_ranked===false?`<div class="note">the law could not rule — no per-test coverage; order is the old sum</div>`:'')
+(r.when?`<div class="k">when</div><div style="font-family:Menlo,monospace;font-size:12px">${r.when.commit.slice(0,8)} “${r.when.subject}” — bisect, ${r.when.runs} runs</div>`:'')
+(r.why?`<div class="k">why</div><div style="font-size:12px;color:var(--dim)">${r.why.diverges_at?`paths part at ${r.why.diverges_at.file}:${r.why.diverges_at.line}${r.why.detail?' — '+r.why.detail:''}`:(r.why.note||'')}</div>`:'')
+((r.notes||[]).length?`<div class="k">notes</div><div class="note">${r.notes.join('<br>')}</div>`:'')+`<div id="src"></div>`;
o.querySelectorAll('.f').forEach(el=>el.onclick=async()=>{const f=r.where[+el.dataset.i];const t=tileOf(f.file);if(t)moveTo(t);const s=await (await fetch(`/api/source?project=${encodeURIComponent(name)}&file=${encodeURIComponent(f.file)}&line=${f.line}`)).json();if(s.lines)$('#src').innerHTML=`<div class="k">${f.file}</div><pre class="code">`+s.lines.map((l,i)=>{const n=s.from+i;const txt=(String(n).padStart(4)+'| '+l).replace(/</g,'&lt;');return n===f.line?`<b>${txt}</b>`:txt}).join('\n')+`</pre>`})}
$('#all').onclick=()=>fetch('/api/scan?all=1',{method:'POST'});loadProjects();setInterval(tick,700);
</script></body></html>"""
