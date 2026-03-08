#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publish current directory (after cleanup) to a new GitHub repository using only GitHub REST API.
- No local git needed.
- Excludes heavy/dev folders (node_modules, .git, etc.)
- Creates repo (idempotent if it already exists under the same account).
- Uploads files via "Create or update file contents" API (one commit per file).

Usage (Windows cmd):
  set "GITHUB_TOKEN=<your_token>" && python scripts\publish_to_github.py --repo memory-lancedb-pro --public --branch main --message "chore: initial publish"

Env:
  GITHUB_TOKEN  Personal Access Token with repo scope
"""

import os
import sys
import json
import base64
import argparse
import time
from urllib import request, error, parse
from typing import Dict, Any, Iterable, Tuple

API_BASE = "https://api.github.com"
UA = "memory-lancedb-pro-publisher/1.0 (+https://github.com)"

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    ".vscode",
    ".idea",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".DS_Store",
    # 已按你的确认删除了 test/、examples/、bounty-results/，此处无需再排除
}

EXCLUDE_FILES_SUFFIX = {
    ".pyc",
    ".pyo",
    ".log",
}

def api_request(method: str, url: str, token: str, data: Dict[str, Any] | None = None, accept: str = "application/vnd.github+json") -> Tuple[int, Dict[str, Any] | str]:
    req = request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", UA)
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json; charset=utf-8")
    else:
        payload = None

    try:
        with request.urlopen(req, data=payload, timeout=60) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return resp.status, json.loads(body.decode("utf-8"))
            return resp.status, body.decode("utf-8", errors="ignore")
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            j = json.loads(body)
        except Exception:
            j = {"message": body}
        return e.code, j
    except Exception as e:
        return 0, {"message": str(e)}

def get_authenticated_user(token: str) -> str:
    code, res = api_request("GET", f"{API_BASE}/user", token)
    if code != 200:
        raise RuntimeError(f"GET /user failed: {code} {res}")
    login = res.get("login")
    if not login:
        raise RuntimeError("Unable to get user login from /user")
    return login

def create_repo_if_not_exists(token: str, name: str, private: bool, default_branch: str = "main") -> None:
    payload = {
        "name": name,
        "private": private,
        "auto_init": False,
    }
    code, res = api_request("POST", f"{API_BASE}/user/repos", token, payload)
    if code in (201,):
        print(f"[OK] Repository created: {res.get('full_name')}")
        # optionally set default branch (usually main by default nowadays)
        return
    # If already exists: 422 with specific message
    if code == 422:
        msg = str(res)
        if "name already exists on this account" in msg or "already exists" in msg:
            print("[OK] Repository already exists, will continue to upload files.")
            return
    # If secondary rate limit or other errors
    raise RuntimeError(f"Create repo failed: {code} {res}")

def should_skip_path(relpath: str, is_dir: bool) -> bool:
    parts = relpath.strip("\\/").split("/")
    # Exclude if any ancestor is in EXCLUDE_DIRS
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
    if not is_dir:
        for suf in EXCLUDE_FILES_SUFFIX:
            if relpath.endswith(suf):
                return True
    return False

def iter_files(base_dir: str) -> Iterable[str]:
    base_dir = os.path.abspath(base_dir)
    for root, dirs, files in os.walk(base_dir):
        # mutate dirs in-place to skip excluded dirs
        dirs[:] = [d for d in dirs if not should_skip_path(os.path.relpath(os.path.join(root, d), base_dir).replace("\\", "/"), True)]
        for f in files:
            abs_path = os.path.join(root, f)
            rel_path = os.path.relpath(abs_path, base_dir).replace("\\", "/")
            if should_skip_path(rel_path, False):
                continue
            yield rel_path

def upload_file(token: str, owner: str, repo: str, branch: str, base_dir: str, rel_path: str, message: str) -> None:
    abs_path = os.path.join(base_dir, rel_path)
    with open(abs_path, "rb") as fp:
        data = fp.read()
    content_b64 = base64.b64encode(data).decode("ascii")
    url_path = parse.quote(rel_path)
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{url_path}"
    payload = {
        "message": message,
        "content": content_b64,
        "branch": branch,
    }
    code, res = api_request("PUT", url, token, payload)
    if code not in (201, 200):
        raise RuntimeError(f"Upload {rel_path} failed: {code} {res}")
    # 201 = created, 200 = updated (if rerun)
    status = "created" if code == 201 else "updated"
    print(f"[{status}] {rel_path}")

def ensure_branch_exists(token: str, owner: str, repo: str, branch: str) -> None:
    # Try get the branch; if repo is empty, create an empty commit via git trees API is complex.
    # But since we upload via contents API and specify branch, GitHub will create it on first commit automatically.
    # We'll just verify default branch name for logs.
    code, res = api_request("GET", f"{API_BASE}/repos/{owner}/{repo}", token)
    if code != 200:
        raise RuntimeError(f"Get repo failed: {code} {res}")
    default_branch = res.get("default_branch", "main")
    print(f"[info] repo default branch: {default_branch} (target: {branch})")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Repository name to create/publish to")
    vis = parser.add_mutually_exclusive_group()
    vis.add_argument("--public", action="store_true", help="Create public repository")
    vis.add_argument("--private", action="store_true", help="Create private repository")
    parser.add_argument("--branch", default="main", help="Target branch (default: main)")
    parser.add_argument("--message", default="chore: initial publish (pruned non-runtime, keep skills) + USER_GUIDE_CN", help="Commit message to use for each file")
    parser.add_argument("--base", default=".", help="Base directory to publish (default: current dir)")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("ERROR: GITHUB_TOKEN env not set", file=sys.stderr)
        sys.exit(2)

    private = True
    if args.public:
        private = False
    elif args.private:
        private = True
    else:
        # default to private for safety; CLI can override with --public
        private = True

    base_dir = os.path.abspath(args.base)
    print(f"[start] base_dir={base_dir}")
    print(f"[plan] repo={args.repo} private={private} branch={args.branch}")

    # 1) Who am I
    owner = get_authenticated_user(token)
    print(f"[auth] user={owner}")

    # 2) Create repo (idempotent)
    create_repo_if_not_exists(token, args.repo, private)

    # 3) (Optional) ensure branch logs
    ensure_branch_exists(token, owner, args.repo, args.branch)

    # 4) Walk files
    rel_files = list(iter_files(base_dir))
    print(f"[scan] files to upload: {len(rel_files)}")
    if not rel_files:
        print("WARNING: No files found to upload (after exclusions).")
        return

    # 5) Upload
    failures = []
    for i, rel in enumerate(rel_files, 1):
        try:
            upload_file(token, owner, args.repo, args.branch, base_dir, rel, args.message)
        except Exception as e:
            print(f"[error] {rel}: {e}", file=sys.stderr)
            failures.append((rel, str(e)))
        # polite pacing to avoid secondary rate limits
        if i % 20 == 0:
            time.sleep(0.5)

    print(f"[done] uploaded={len(rel_files) - len(failures)} failed={len(failures)}")
    if failures:
        print("Failed files:")
        for rel, msg in failures:
            print(f" - {rel}: {msg}")
        # Non-zero exit if any failed
        sys.exit(1)

    # 6) Print repo URL
    visibility = "public" if not private else "private"
    print(f"[success] Published to https://github.com/{owner}/{args.repo} (branch {args.branch}, {visibility})")

if __name__ == "__main__":
    main()
