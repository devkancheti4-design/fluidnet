"""fluidnet scan: a workspace of project folders is found, scanned one after another, and served."""
import json, threading, time, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from fluidnet import scan


def test_projects_under_a_workspace(repo_factory, tmp_path):
    root = repo_factory("def f():\n    return 1\n", "from pkg.mod import f\n\ndef test_f():\n    assert f() == 1\n")
    (tmp_path / "not_a_project").mkdir()
    found = scan.projects(tmp_path)
    assert [p["name"] for p in found] == ["repo"] and found[0]["tests"] is True


def test_scan_all_and_status(repo_factory, tmp_path):
    root = repo_factory("def f():\n    return 2\n", "from pkg.mod import f\n\ndef test_f():\n    assert f() == 1\n")
    scan.STATE.update(projects=scan.projects(tmp_path), queue=[], results={}, current=None, log=[])
    threading.Thread(target=scan.worker, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), scan.H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/scan?all=1", method="POST")
        assert urllib.request.urlopen(req).status == 202
        for _ in range(120):
            s = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status"))
            if "repo" in s["results"]:
                break
            time.sleep(0.5)
        r = s["results"]["repo"]
        assert r["status"] == "red" and r["where"][0]["file"] == "pkg/mod.py" and r["where"][0]["rank"] > 0
        assert any("suite" in l for l in s["log"]) and r["files"]           # real events, and the grid's files
        src = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/source?project=repo&file=pkg/mod.py&line=2"))
        assert "return 2" in "\n".join(src["lines"])
        assert urllib.request.urlopen(f"http://127.0.0.1:{port}/").status == 200
    finally:
        srv.shutdown()
