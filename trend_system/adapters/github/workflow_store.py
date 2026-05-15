from __future__ import annotations

import base64
import json
import re
import urllib.request

from trend_system.adapters.github.content_store import GitHubRepoConfig


WORKFLOW_PATH = ".github/workflows/daily-signal.yml"
DEFAULT_PUSH_CONFIG = "config/settings.toml"
DEFAULT_NZ_TIME = "15:45"
DEFAULT_US_TIME = "15:00"


def read_push_config(config: GitHubRepoConfig) -> tuple[str, str, str]:
    try:
        if not config.token or not config.repo:
            return DEFAULT_PUSH_CONFIG, DEFAULT_NZ_TIME, DEFAULT_US_TIME
        api_url = f"https://api.github.com/repos/{config.repo}/contents/{WORKFLOW_PATH}?ref={config.branch}"
        req = urllib.request.Request(api_url, headers=_headers(config))
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        content = base64.b64decode(data["content"]).decode()
        return parse_push_config(content)
    except Exception:
        return DEFAULT_PUSH_CONFIG, DEFAULT_NZ_TIME, DEFAULT_US_TIME


def update_push_config(
    config: GitHubRepoConfig,
    workflow_config_path: str,
    nz_time: str,
    us_time: str,
) -> tuple[bool, str]:
    try:
        if not config.token or not config.repo:
            return False, "未配置 GITHUB_TOKEN / GITHUB_REPO secrets"
        api_url = f"https://api.github.com/repos/{config.repo}/contents/{WORKFLOW_PATH}"
        req = urllib.request.Request(api_url, headers=_headers(config))
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        content = base64.b64decode(data["content"]).decode()
        sha = data["sha"]
        updated = replace_push_config(content, workflow_config_path, nz_time, us_time)
        body: dict[str, str] = {
            "message": f"chore: update push config to {workflow_config_path} ({nz_time} NZ / {us_time} US) via Streamlit UI",
            "content": base64.b64encode(updated.encode()).decode(),
            "sha": sha,
            "branch": config.branch,
        }
        put_req = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode(),
            headers=_headers(config),
            method="PUT",
        )
        with urllib.request.urlopen(put_req):
            pass
        return True, "Workflow 已更新并推送到 GitHub"
    except Exception as exc:
        return False, f"Workflow 更新失败: {exc}"


def parse_push_config(content: str) -> tuple[str, str, str]:
    nz = re.search(r'target_nz_time="(\d{2}:\d{2})"', content)
    us = re.search(r'target_ny_time="(\d{2}:\d{2})"', content)
    cfg = re.search(r'workflow_config_path="(config/\S+\.toml)"', content)
    return (
        cfg.group(1) if cfg else DEFAULT_PUSH_CONFIG,
        nz.group(1) if nz else DEFAULT_NZ_TIME,
        us.group(1) if us else DEFAULT_US_TIME,
    )


def replace_push_config(content: str, workflow_config_path: str, nz_time: str, us_time: str) -> str:
    content = re.sub(r'target_nz_time="\d{2}:\d{2}"', f'target_nz_time="{nz_time}"', content)
    content = re.sub(r'target_ny_time="\d{2}:\d{2}"', f'target_ny_time="{us_time}"', content)
    return re.sub(r'workflow_config_path="config/\S+\.toml"', f'workflow_config_path="{workflow_config_path}"', content)


def _headers(config: GitHubRepoConfig) -> dict[str, str]:
    return {
        "Authorization": f"token {config.token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
