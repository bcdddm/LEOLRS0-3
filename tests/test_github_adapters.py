from __future__ import annotations

from trend_system.adapters.github.workflow_store import (
    DEFAULT_NZ_TIME,
    DEFAULT_PUSH_CONFIG,
    DEFAULT_US_TIME,
    parse_push_config,
    replace_push_config,
)


def test_parse_push_config_reads_times_and_config_path():
    content = """
workflow_config_path="config/profiles/Leo.toml"
target_nz_time="15:45"
target_ny_time="15:00"
"""

    config_path, nz_time, us_time = parse_push_config(content)

    assert config_path == "config/profiles/Leo.toml"
    assert nz_time == "15:45"
    assert us_time == "15:00"


def test_parse_push_config_falls_back_to_defaults():
    config_path, nz_time, us_time = parse_push_config("no matching workflow content")

    assert config_path == DEFAULT_PUSH_CONFIG
    assert nz_time == DEFAULT_NZ_TIME
    assert us_time == DEFAULT_US_TIME


def test_replace_push_config_updates_times_and_config_path():
    original = """
workflow_config_path="config/profiles/Leo.toml"
target_nz_time="15:45"
target_ny_time="15:00"
"""

    updated = replace_push_config(original, "config/settings.toml", "16:10", "14:55")

    assert 'target_nz_time="16:10"' in updated
    assert 'target_ny_time="14:55"' in updated
    assert 'workflow_config_path="config/settings.toml"' in updated
