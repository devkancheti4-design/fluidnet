// fluidnet for VS Code / Cursor / Windsurf. Plain JavaScript, no build step.
// Everything shown comes from `fluidnet locate --json` and the walk it writes; nothing is animated
// that did not happen. The crawl walks the lines the failing test executed and stops where the law ruled.
const vscode = require("vscode");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

let status, out, diags, ctx, last = null, twitch = null, crawling = null;
const FRAMES = ["$(bug)", "$(bug) "];

function cfg(k) { return vscode.workspace.getConfiguration("fluidnet").get(k); }

function setStatus(text, tone, tip) {
  status.text = text; status.tooltip = tip || "";
  status.backgroundColor = tone === "red" ? new vscode.ThemeColor("statusBarItem.errorBackground")
                         : tone === "busy" ? new vscode.ThemeColor("statusBarItem.warningBackground") : undefined;
  clearInterval(twitch); twitch = null;
  if (tone === "red") { let i = 0; twitch = setInterval(() => { status.text = FRAMES[i ^= 1] + text.slice(text.indexOf(")") + 1); }, 480); }
}

function run(args, cwd) {
  return new Promise((resolve) => {
    const p = spawn(cfg("path"), args, { cwd, shell: process.platform === "win32" });
    let so = "", se = "";
    p.stdout.on("data", d => so += d); p.stderr.on("data", d => se += d);
    p.on("error", e => resolve({ code: -1, so, se: String(e) }));
    p.on("close", code => resolve({ code, so, se }));
  });
}

async function locate(folder, quiet) {
  const root = folder.uri.fsPath;
  setStatus("$(bug) locating…", "busy", root);
  const args = ["locate", root, "--json"]; if (!cfg("bisect")) args.push("--no-bisect");
  if (cfg("python")) args.push("--python", cfg("python"));
  const r = await run(args, root);
  let L = null; try { L = JSON.parse(r.so.slice(r.so.indexOf("{"))); } catch (e) {}
  if (!L) {
    setStatus("$(bug) fluidnet", undefined, "could not run fluidnet — set fluidnet.path");
    if (!quiet) { out.appendLine(r.se || r.so); vscode.window.showErrorMessage("fluidnet: could not run `" + cfg("path") + " locate` — set fluidnet.path (a venv's bin/fluidnet works)."); }
    return null;
  }
  let walk = null; try { walk = JSON.parse(fs.readFileSync(path.join(root, ".fluidfix", "locate.json"), "utf8")).walk; } catch (e) {}
  last = { root, L, walk };
  diags.clear();
  if (L.status === "green") { setStatus("$(bug) green", undefined, root); out.appendLine(`[${folder.name}] suite green — nothing to locate`); return last; }
  if (L.status !== "red") { setStatus("$(bug) ?", undefined, (L.notes || []).join("; ")); out.appendLine(`[${folder.name}] ${(L.notes || []).join("; ")}`); return last; }
  const top = L.where[0];
  const label = top ? `${path.basename(top.file)}:${top.line} · cause ${top.rank}/15` : "no candidate";
  setStatus(`$(bug) ${L.failing.length} failing · ${label}`, "red", "click: crawl to the bug");
  out.appendLine(`[${folder.name}] RED — ${L.failing.join(", ")}`);
  const dl = [];
  L.where.slice(0, 5).forEach((f, i) => {
    out.appendLine(`  ${i + 1}. ${f.file}:${f.line}  cause ${f.rank}/15  [${f.lanes.join(", ")}]`);
    if (i === 0) {
      const uri = vscode.Uri.file(path.join(root, f.file));
      const d = new vscode.Diagnostic(new vscode.Range(f.line - 1, 0, f.line - 1, 999),
        `root cause by the cause law: ${f.rank}/15 — ${f.lanes.join(", ")}` + (L.when ? ` — introduced by ${L.when.commit.slice(0, 8)} "${L.when.subject}"` : ""),
        vscode.DiagnosticSeverity.Error);
      d.source = "fluidnet"; dl.push([uri, [d]]);
    }
  });
  if (L.vetoed) out.appendLine(`  (${L.vetoed} candidates vetoed by the law)`);
  if (L.why) out.appendLine(`  why: ${L.why.note || (L.why.diverges_at ? `parts at ${L.why.diverges_at.file}:${L.why.diverges_at.line}` : "")}`);
  diags.set(dl.length ? dl : []);
  if (!quiet) await crawl();
  return last;
}

const curDeco = vscode.window.createTextEditorDecorationType({ backgroundColor: "rgba(249,226,175,0.18)", isWholeLine: true });
let winDeco = null;

async function crawl() {
  if (!last || last.L.status !== "red" || !last.walk) { vscode.window.showInformationMessage("fluidnet: nothing to crawl to — locate first, on a red suite."); return; }
  if (crawling) return;
  const { root, L, walk } = last;
  const doc = await vscode.workspace.openTextDocument(path.join(root, walk.file));
  const ed = await vscode.window.showTextDocument(doc, { preview: false });
  if (winDeco) winDeco.dispose();
  winDeco = vscode.window.createTextEditorDecorationType({
    backgroundColor: "rgba(243,139,168,0.22)", isWholeLine: true,
    gutterIconPath: ctx.asAbsolutePath("media/bug.svg"), gutterIconSize: "contain",
    after: { margin: "0 0 0 2em", color: "#f38ba8" }
  });
  const lines = (walk.lines || []).map(l => l.line); if (!lines.includes(walk.winner)) lines.push(walk.winner);
  const step = Math.max(70, Math.min(240, Math.floor(5000 / Math.max(1, lines.length))));
  const top = L.where.find(f => f.file === walk.file && f.line === walk.winner) || L.where[0];
  const strong = [], weak = []; const b = (top && top.bits) || {};
  (b.BISECT ? strong : b.RECENT ? weak : []).push("TIME");
  (b.EF_ALL && b.EP_NONE ? strong : (b.EF_ALL || b.IMPORT) ? weak : []).push("SPECTRUM");
  if (b.DIVERGE) strong.push("WHY");
  (b.FRAME && b.LITERAL ? strong : (b.FRAME || b.LITERAL) ? weak : []).push("SYMPTOM");
  crawling = true;
  for (const ln of lines) {
    const r = new vscode.Range(ln - 1, 0, ln - 1, 0);
    ed.setDecorations(curDeco, [r]); ed.revealRange(r, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    await new Promise(res => setTimeout(res, step));
  }
  ed.setDecorations(curDeco, []);
  const w = new vscode.Range(walk.winner - 1, 0, walk.winner - 1, 0);
  const hover = new vscode.MarkdownString(
    `**fluidnet — root cause by the cause law**  \n\`${walk.file}:${walk.winner}\` · **cause ${top ? top.rank : "?"}/15**  \n` +
    `strong: ${strong.join(", ") || "—"} · weak: ${weak.join(", ") || "—"}  \nevidence: ${top ? top.lanes.join(", ") : ""}` +
    (L.when ? `  \nwhen: \`${L.when.commit.slice(0, 8)}\` “${L.when.subject}”` : "") +
    (L.why ? `  \nwhy: ${L.why.note || (L.why.diverges_at ? `parts at ${L.why.diverges_at.file}:${L.why.diverges_at.line}` : "")}` : ""));
  ed.setDecorations(winDeco, [{ range: w, hoverMessage: hover,
    renderOptions: { after: { contentText: ` ◀ cause ${top ? top.rank : "?"}/15 · ${strong.length ? "strong " + strong.join("+") : "no strong lane"}` } } }]);
  ed.revealRange(w, vscode.TextEditorRevealType.InCenter);
  crawling = false;
}

async function scan() {
  const folders = vscode.workspace.workspaceFolders || [];
  if (!folders.length) return vscode.window.showInformationMessage("fluidnet: open a folder first.");
  out.show(true);
  for (const f of folders) await locate(f, folders.length > 1);
}

function activate(c) {
  ctx = c;
  out = vscode.window.createOutputChannel("fluidnet");
  diags = vscode.languages.createDiagnosticCollection("fluidnet");
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
  status.command = "fluidnet.crawl"; setStatus("$(bug) fluidnet", undefined, "fluidnet: locate the bug"); status.show();
  c.subscriptions.push(status, out, diags,
    vscode.commands.registerCommand("fluidnet.locate", async () => {
      const f = (vscode.workspace.workspaceFolders || [])[0]; if (!f) return vscode.window.showInformationMessage("fluidnet: open a folder first.");
      await locate(f, false);
    }),
    vscode.commands.registerCommand("fluidnet.crawl", async () => { if (!last) { const f = (vscode.workspace.workspaceFolders || [])[0]; if (f) await locate(f, false); } else await crawl(); }),
    vscode.commands.registerCommand("fluidnet.scan", scan));
  // the last known result, at once and without running anything: a repo whose suite was red when you
  // left it is red when you come back; a click crawls; the next save locates again
  for (const f of (vscode.workspace.workspaceFolders || [])) {
    try {
      const j = JSON.parse(fs.readFileSync(path.join(f.uri.fsPath, ".fluidfix", "locate.json"), "utf8"));
      if (j.status === "red" && j.where && j.where.length) {
        last = { root: f.uri.fsPath, L: j, walk: j.walk };
        const top = j.where[0];
        setStatus(`$(bug) ${j.failing.length} failing · ${path.basename(top.file)}:${top.line} · cause ${top.rank}/15`, "red",
                  `last locate at ${j.at || "?"} — click: crawl to the bug`);
        break;
      }
    } catch (e) {}
  }
  let t = null;
  c.subscriptions.push(vscode.workspace.onDidSaveTextDocument(d => {
    if (!cfg("onSave") || !d.fileName.endsWith(".py")) return;
    const f = vscode.workspace.getWorkspaceFolder(d.uri); if (!f) return;
    clearTimeout(t); t = setTimeout(() => locate(f, true), 1500);
  }));
}
function deactivate() { clearInterval(twitch); }
module.exports = { activate, deactivate };
