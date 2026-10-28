"""
Pulls the newest studieplus-mcp and studieplus-api from GitHub when the server starts.

It must run before fastmcp, api and studieplus_api are imported, so the new code is
the code that gets loaded. Every failure (offline, local changes, no git) is logged
to stderr and skipped, so the server always starts.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

REPO_DIR = Path(__file__).resolve().parent.parent.parent
SERVER_FILE = "src/mcp_server/server.py"
API_DIST = "studieplus-api"

GIT_TIMEOUT = 20
INSTALL_TIMEOUT = 90

# Nobody can answer a credential prompt when Claude Desktop starts the server
CHILD_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}

_has_run = False


def _log(message):
    print(f"[updater] {message}", file=sys.stderr)


def _run(args, cwd=None, timeout=GIT_TIMEOUT):
    # stdin and stdout belong to the MCP protocol, and a child must not open a console window
    return subprocess.run(
        args,
        cwd=cwd,
        env=CHILD_ENV,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()


def _git_pull(repo):
    """Fast-forward repo to its upstream. Returns (old, new) HEAD, or None when nothing changed."""
    before = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    _run(["git", "pull", "--ff-only", "--quiet"], cwd=repo)
    after = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if before == after:
        return None
    _log(f"{repo.name} updated {before[:7]} -> {after[:7]}")
    return before, after


def _changed(repo, commits, path):
    return bool(_run(["git", "diff", "--name-only", *commits, "--", path], cwd=repo))


def _pip_install(*args):
    # Venvs made by uv have no pip
    if importlib.util.find_spec("pip"):
        command = [sys.executable, "-m", "pip", "install", "--quiet", *args]
    elif shutil.which("uv"):
        command = ["uv", "pip", "install", "--quiet", "--python", sys.executable, *args]
    else:
        raise RuntimeError("neither pip nor uv is available")
    _run(command, timeout=INSTALL_TIMEOUT)


def _install_requirements():
    """Install requirements.txt, except studieplus-api, which _update_api handles and may be an editable checkout."""
    lines = (REPO_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
    requirements = [line.split("#")[0].strip() for line in lines]
    requirements = [r for r in requirements if r and not r.startswith(API_DIST)]
    _pip_install(*requirements)
    _log("requirements.txt changed, dependencies installed")


def _update_server():
    """Returns True when server.py itself changed."""
    commits = _git_pull(REPO_DIR)
    if not commits:
        return False
    if _changed(REPO_DIR, commits, "requirements.txt"):
        _install_requirements()
    return _changed(REPO_DIR, commits, SERVER_FILE)


def _update_api():
    # direct_url.json (PEP 610) tells how pip installed the package, without importing it
    direct_url = json.loads(metadata.distribution(API_DIST).read_text("direct_url.json") or "{}")
    url = direct_url.get("url", "")

    if direct_url.get("dir_info", {}).get("editable"):
        repo = Path(url2pathname(urlparse(url).path))
        commits = _git_pull(repo)
        if commits and _changed(repo, commits, "pyproject.toml"):
            _pip_install("-e", str(repo))
    elif "vcs_info" in direct_url:
        installed = direct_url["vcs_info"]["commit_id"]
        ref = direct_url["vcs_info"].get("requested_revision", "HEAD")
        remote = _run(["git", "ls-remote", url, ref]).split()
        if remote and remote[0] != installed:
            _pip_install("--force-reinstall", "--no-deps", f"{API_DIST} @ git+{url}")
            _log(f"{API_DIST} updated {installed[:7]} -> {remote[0][:7]}")


def update():
    """Update both projects once per process. Returns True when server.py changed and must be run again."""
    global _has_run
    if _has_run or os.getenv("STUDIEPLUS_AUTO_UPDATE", "1") == "0":
        return False
    _has_run = True

    if not shutil.which("git"):
        _log("git not found, skipping update")
        return False

    server_changed = False
    try:
        server_changed = _update_server()
    except Exception as e:
        _log(f"studieplus-mcp not updated: {_reason(e)}")
    try:
        _update_api()
    except Exception as e:
        _log(f"{API_DIST} not updated: {_reason(e)}")
    return server_changed


def _reason(error):
    stderr = getattr(error, "stderr", None)
    return stderr.strip() if isinstance(stderr, str) and stderr.strip() else str(error)
