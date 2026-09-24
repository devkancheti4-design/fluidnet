"""buggy scan listens on localhost only, serves only .py files inside the listed projects, refuses foreign
Host headers (DNS rebinding), and runs nothing on a POST that a browser could have made cross-origin."""
import json, os, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from fluidnet import scan


def serve(tmp_path, repo_factory):
    root = repo_factory("def f():\n    return 1\n", "from pkg.mod import f\n\ndef test_f():\n    assert f() == 1\n")
    scan.STATE.update(projects=scan.projects(tmp_path), queue=[], results={}, current=None, log=[])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), scan.H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return root, srv.server_address[1]


def get(url, headers=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers or {})); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_the_server_binds_to_localhost_only():
    src = Path(scan.__file__).read_text()
    assert 'ThreadingHTTPServer(("127.0.0.1", port), H)' in src


def test_only_py_files_inside_the_project(tmp_path, repo_factory):
    root, port = serve(tmp_path, repo_factory)
    (root / "secret.txt").write_text("hunter2")
    outside = tmp_path / "outside.py"; outside.write_text("x = 1\n")
    (root / "pkg" / "link.py").symlink_to(outside)
    ok = get(f"http://127.0.0.1:{port}/api/source?project=repo&file=pkg/mod.py&line=1")
    assert ok[0] == 200 and "def f" in "".join(ok[1]["lines"])
    for bad in ("/etc/passwd", "../outside.py", "pkg/../../outside.py", "secret.txt", "pkg/link.py", str(outside), ""):
        code, body = get(f"http://127.0.0.1:{port}/api/source?project=repo&file={urllib.request.quote(bad, safe='')}&line=1")
        assert code == 404 and "lines" not in body, (bad, code, body)


def test_a_foreign_host_header_is_refused(tmp_path, repo_factory):
    root, port = serve(tmp_path, repo_factory)
    assert get(f"http://127.0.0.1:{port}/api/projects", {"Host": "evil.example"})[0] == 403
    assert get(f"http://127.0.0.1:{port}/api/projects", {"Host": f"localhost:{port}"})[0] == 200


def test_a_post_without_the_header_runs_nothing(tmp_path, repo_factory):
    root, port = serve(tmp_path, repo_factory)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/scan?all=1", method="POST")
    try:
        urllib.request.urlopen(req); assert False, "accepted"
    except urllib.error.HTTPError as e:
        assert e.code == 403
    assert scan.STATE["queue"] == []
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/scan?all=1", method="POST", headers={"X-Buggy": "scan"})
    assert urllib.request.urlopen(req).status == 202 and scan.STATE["queue"] == ["repo"]
