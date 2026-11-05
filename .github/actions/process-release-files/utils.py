# Copyright 2026 The MathWorks, Inc.
import os
import json
import copy
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from itertools import chain
from typing import List, Dict
from pathlib import Path

PERMISSION_POLICIES = ["provisioning_policy", "execution_policy", "execution_policy_trust"]

def deserialize_target_versions(target_versions_string:str ) -> List[str]:
    try:
        return json.loads(target_versions_string)
    except json.JSONDecodeError:
        print(f"Error: --target-versions must be a valid JSON list. Got: {target_versions_string}")
        sys.exit(1)

def removal_date(release: str, releases_supported: int):
    """
    Month and year in which a release's prebuilt artifacts are removed, given
    how many releases are supported. Same rule as refarch-utils.
    """
    year, letter = re.search(r"[Rr](\d{4})([ab])", release).groups()
    if letter == "a":
        month = "March" if releases_supported % 2 == 0 else "September"
    else:
        month = "September" if releases_supported % 2 == 0 else "March"
    removal_year = int(year) + releases_supported // 2
    if letter == "b" and releases_supported % 2 == 1:
        removal_year += 1
    return month, str(removal_year)

def github_get(url: str):
    """GET a GitHub API URL and return the decoded JSON, retrying transient failures."""
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise
            print(f"GitHub API request failed ({e}), retrying...")
            time.sleep(5 * attempt)

def list_dual_releases(dual_repo_url: str):
    """
    The release folders of the sister repository, as (releases, releases_url).
    Each release is {'label', 'dual_url'}; releases_url is the URL of its releases folder.
    """
    owner, repo = dual_repo_url.rstrip('/').split('/')[-2:]
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    contents = github_get(f"{api}/repos/{owner}/{repo}/contents/releases")
    releases = [
        {"label": item["name"].replace("_", "\\_"), "dual_url": item["html_url"]}
        for item in contents
    ]
    releases_url = next(
        item["html_url"]
        for item in github_get(f"{api}/repos/{owner}/{repo}/contents/")
        if item["name"] == "releases"
    )
    return releases, releases_url

def create_release_object(releases_dir: str, target_releases: List[str], dual_repo_url: str, releases_supported: int) -> List[Dict[str, str]]:
    """
    The rows of the top-level release table: the release folders of this
    repository (including the releases being written now) merged with those of
    the sister repository, newest first, limited to the supported releases.
    Same table as refarch-utils renders.
    """
    names = {p.name for p in Path(releases_dir).iterdir() if p.is_dir() and not p.name.startswith(".")} if Path(releases_dir).is_dir() else set()
    names.update(target_releases)
    main_releases = [{"label": name.replace("_", "\\_"), "dir": name} for name in names]

    dual_releases, dual_releases_url = list_dual_releases(dual_repo_url)
    newest_dual = max((r["label"] for r in dual_releases), default="")
    for release in target_releases:
        # Link a release the sister repository hasn't published yet.
        if release > newest_dual:
            dual_releases.append({"label": release, "dual_url": f"{dual_releases_url}/{release}"})

    rows = defaultdict(lambda: {"label": None, "dir": None, "dual_url": None, "removal_month": None, "removal_year": None})
    for release in chain(main_releases, dual_releases):
        rows[release["label"]].update(release)
    releases = [rows[label] for label in sorted(rows, reverse=True)]

    if releases_supported > 0:
        releases = releases[:releases_supported]
        for release in releases:
            release["removal_month"], release["removal_year"] = removal_date(release["label"], releases_supported)

    return releases

def create_permissions_object(permissions_path):
    """
    The permission policies under permissions_path, keyed by name, or an empty
    dict when the repository publishes no permission policies.
    """
    path_obj = Path(permissions_path)
    if not path_obj.is_dir():
        return {}

    permissions_object = {}
    for name in PERMISSION_POLICIES:
        file_path = path_obj / f"{name}.json"
        with open(file_path, "r", encoding="utf-8") as f:
            permissions_object[name] = json.load(f)
    return permissions_object

def remove_action_from_policy(policy: dict, action_to_remove: str) -> dict:
    """Remove single action from policy. """

    policy_copy = copy.deepcopy(policy)

    if "Statement" not in policy_copy:
        return policy_copy

    filtered_statements = []
    for statement in policy_copy["Statement"]:
        if "Action" in statement:
            if isinstance(statement["Action"], list):
                statement["Action"] = [
                    action
                    for action in statement["Action"]
                    if action.lower() != action_to_remove.lower()
                ]
                if statement["Action"]:
                    filtered_statements.append(statement)
            elif isinstance(statement["Action"], str):
                if statement["Action"] != action_to_remove:
                    filtered_statements.append(statement)
        else:
            filtered_statements.append(statement)

    policy_copy["Statement"] = filtered_statements
    return policy_copy

def remove_actions_from_policy(policy: dict, actions_to_remove: list) -> dict:
    """Remove actions from policy without modifying the original."""
    policy_copy = copy.deepcopy(policy)

    for action in actions_to_remove:
        policy_copy = remove_action_from_policy(policy_copy, action)
    return policy_copy

def write_to_disk(base_dir: str, structure: dict) -> List[str]:
    """
    Write the virtual filesystem to disk and return the paths written,
    relative to base_dir. Keys may contain slashes.
    """
    base_path = Path(base_dir).resolve()
    base_path.mkdir(parents=True, exist_ok=True)
    written = []

    def _write_recursive(current_path: Path, current_struct: dict):
        for name, content in current_struct.items():
            target_path = current_path / name
            if isinstance(content, dict):
                _write_recursive(target_path, content)
            elif content is not None:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                written.append(str(target_path.relative_to(base_path)))
                print(f"   Created: {written[-1]}")

    print(f"Writing files to: {base_path}...")
    _write_recursive(base_path, structure)
    return written
