from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubRepoConfig:
    token: str
    repo: str
    branch: str = "main"


def push_text_file(config: GitHubRepoConfig, relative_path: str, content: str) -> tuple[bool, str]:
    try:
        _validate_config(config)
        api_url = f"https://api.github.com/repos/{config.repo}/contents/{relative_path}"
        headers = _headers(config)
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                current = json.loads(resp.read())
            sha = current.get("sha", "")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                sha = ""
            else:
                raise
        body: dict[str, str] = {
            "message": f"chore: update {relative_path} via Streamlit UI",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": config.branch,
        }
        if sha:
            body["sha"] = sha
        put_req = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="PUT",
        )
        with urllib.request.urlopen(put_req):
            pass
        return True, "已推送到 GitHub"
    except Exception as exc:
        return False, f"GitHub 推送失败: {exc}"


def delete_file(config: GitHubRepoConfig, relative_path: str) -> tuple[bool, str]:
    try:
        _validate_config(config)
        api_url = f"https://api.github.com/repos/{config.repo}/contents/{relative_path}"
        headers = _headers(config)
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                current = json.loads(resp.read())
            sha = current.get("sha", "")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return True, "GitHub 上不存在该文件（已跳过）"
            raise
        body: dict[str, str] = {
            "message": f"chore: delete {relative_path} via Streamlit UI",
            "sha": sha,
            "branch": config.branch,
        }
        del_req = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="DELETE",
        )
        with urllib.request.urlopen(del_req):
            pass
        return True, "已从 GitHub 删除"
    except Exception as exc:
        return False, f"GitHub 删除失败: {exc}"


def _headers(config: GitHubRepoConfig) -> dict[str, str]:
    return {
        "Authorization": f"token {config.token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }


def _validate_config(config: GitHubRepoConfig) -> None:
    if not config.token or not config.repo:
        raise RuntimeError("未配置 GITHUB_TOKEN / GITHUB_REPO secrets")
