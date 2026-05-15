from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import streamlit as st
import toml


@dataclass(frozen=True)
class SettingsPageDeps:
    tr: Callable[[str, str, str], str]
    ui_language: Callable[[dict[str, Any]], str]
    option_index: Callable[[list[str], str], int]
    aligned_button: Callable[..., bool]
    save_config: Callable[[Path, dict[str, Any]], None]
    save_config_github: Callable[[str, str], tuple[bool, str]]
    profile_path_for_name: Callable[[str], Path]
    config_options: Callable[[], dict[str, Path]]
    delete_config_github: Callable[[str], tuple[bool, str]]
    read_workflow_push_config: Callable[[], tuple[str, str, str]]
    update_workflow_github: Callable[[str, str, str], tuple[bool, str]]
    default_push_config: str
    default_nz_time: str
    default_us_time: str
    release_notes_renderer: Callable[[str], None]
    version: str
    app_root: Path
    default_config: str


def render_settings_page(
    settings: dict[str, Any],
    config_path: str,
    *,
    deps: SettingsPageDeps,
) -> None:
    language = deps.ui_language(settings)
    tr = deps.tr
    st.subheader(tr(language, "当前设置", "Current Settings"))
    st.caption(f"{tr(language, '来源', 'Source')}: {Path(config_path).resolve()}")

    st.markdown(
        f'<div class="leo-section-head leo-section-head--prussian"><span class="leo-section-dot"></span><span class="leo-section-overline">{tr(language, "个人偏好", "Preferences")}</span><span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    pref_cols = st.columns(3)
    ui = settings.setdefault("ui", {})
    profile = settings.setdefault("profile", {})
    selected_language = pref_cols[0].selectbox(
        tr(language, "界面语言", "Interface language"),
        ["zh", "en"],
        index=deps.option_index(["zh", "en"], ui.get("language", "en")),
        format_func=lambda value: "中文" if value == "zh" else "English",
        key="settings_ui_language",
    )
    timezones = ["Pacific/Auckland", "Australia/Sydney", "Asia/Shanghai", "America/New_York", "UTC"]
    selected_timezone = pref_cols[1].selectbox(
        tr(language, "居住地区", "Home region"),
        timezones,
        index=deps.option_index(timezones, profile.get("home_timezone", "Pacific/Auckland")),
        key="settings_home_timezone",
    )
    currencies = ["NZD", "AUD", "USD", "CNY"]
    selected_currency = pref_cols[2].selectbox(
        tr(language, "基础货币", "Base currency"),
        currencies,
        index=deps.option_index(currencies, profile.get("base_currency", "NZD")),
        key="settings_base_currency",
    )
    ui["language"] = selected_language
    profile["home_timezone"] = selected_timezone
    profile["base_currency"] = selected_currency
    st.session_state["ui_language"] = selected_language
    st.session_state["home_timezone"] = selected_timezone
    st.session_state["base_currency"] = selected_currency
    st.caption(
        tr(
            language,
            "这些偏好会立即影响当前会话；点击保存当前设置后会写入配置文件。",
            "These preferences affect the current session immediately; save current settings to write them to the config file.",
        )
    )

    save_cols = st.columns([1, 1, 2])
    if deps.aligned_button(save_cols[0], tr(language, "保存当前设置", "Save current settings"), type="primary", use_container_width=True):
        try:
            deps.save_config(Path(config_path), settings)
        except Exception as exc:
            st.error(f"{tr(language, '本地写入失败', 'Local write failed')}: {exc}")
        else:
            toml_str = toml.dumps(settings)
            rel = str(Path(config_path).relative_to(deps.app_root))
            ok, msg = deps.save_config_github(rel, toml_str)
            if ok:
                st.success(f"{tr(language, '设置已保存。', 'Settings saved.')} {msg}")
            else:
                st.warning(
                    f"{tr(language, '设置已写入本地，但', 'Settings written locally, but')} {msg}"
                    f"（{tr(language, '重部署后配置将丢失，请手动 git push', 'config will be lost on redeploy — please git push manually')}）"
                )
    new_name = save_cols[1].text_input(tr(language, "新配置名称", "New profile name"), placeholder=tr(language, "例如：保守版", "Example: Conservative"))
    if deps.aligned_button(save_cols[2], tr(language, "另存为配置文件包", "Save as profile"), use_container_width=True):
        if not new_name.strip():
            st.error(tr(language, "请先输入新配置名称。", "Enter a new profile name first."))
        else:
            target = deps.profile_path_for_name(new_name)
            settings.setdefault("profile", {})["name"] = new_name.strip()
            try:
                deps.save_config(target, settings)
            except Exception as exc:
                st.error(f"{tr(language, '本地写入失败', 'Local write failed')}: {exc}")
            else:
                toml_str = toml.dumps(settings)
                rel = str(target.relative_to(deps.app_root))
                ok, msg = deps.save_config_github(rel, toml_str)
                if ok:
                    st.success(f"{tr(language, '已另存为', 'Saved as')}: {target.name}。{msg}")
                else:
                    st.warning(
                        f"{tr(language, '已另存为', 'Saved as')} {target.name}（{tr(language, '本地', 'local')}），"
                        f"{tr(language, '但', 'but')} {msg}"
                        f"（{tr(language, '刷新后配置将消失，请手动 git push', 'config will disappear on refresh — please git push manually')}）"
                    )
    deletable = {
        name: path
        for name, path in deps.config_options().items()
        if path != Path(deps.default_config) and name not in ("默认配置", "自定义路径")
        and path.resolve() != Path(config_path).resolve()
    }
    if deletable:
        st.markdown(
            f'<div class="leo-section-head leo-section-head--red"><span class="leo-section-dot"></span><span class="leo-section-overline">{tr(language, "删除配置文件包", "Delete Profile")}</span><span class="leo-section-rule"></span></div>',
            unsafe_allow_html=True,
        )
        del_cols = st.columns([3, 1])
        del_target_name = del_cols[0].selectbox(
            tr(language, "选择要删除的配置", "Select profile to delete"),
            list(deletable.keys()),
            key="delete_profile_select",
            label_visibility="collapsed",
        )
        if del_cols[1].button(tr(language, "删除", "Delete"), use_container_width=True):
            st.session_state["pending_delete"] = del_target_name
        if st.session_state.get("pending_delete") == del_target_name:
            st.warning(
                f"⚠️ {tr(language, '确认删除配置文件包', 'Confirm delete profile')}"
                f" **{del_target_name}**？{tr(language, '此操作不可撤销。', 'This cannot be undone.')}"
            )
            confirm_cols = st.columns(2)
            if confirm_cols[0].button(tr(language, "确认删除", "Confirm delete"), type="primary", key="confirm_delete_yes"):
                del_path = deletable[del_target_name]
                try:
                    del_path.unlink(missing_ok=True)
                except Exception as exc:
                    st.error(f"{tr(language, '本地删除失败', 'Local delete failed')}: {exc}")
                else:
                    rel = str(del_path.relative_to(deps.app_root))
                    ok, msg = deps.delete_config_github(rel)
                    st.session_state.pop("pending_delete", None)
                    if ok:
                        st.success(f"{tr(language, '已删除', 'Deleted')}: {del_target_name}。{msg}")
                    else:
                        st.warning(
                            f"{tr(language, '本地已删除，但', 'Deleted locally, but')} {msg}"
                            f"（{tr(language, '请手动 git push 同步到 GitHub', 'please git push to sync to GitHub')}）"
                        )
                    st.rerun()
            if confirm_cols[1].button(tr(language, "取消", "Cancel"), key="confirm_delete_no"):
                st.session_state.pop("pending_delete", None)
                st.rerun()

    st.json(settings, expanded=False)
    st.info(tr(language, "保存前，当前修改只影响本次界面运行。", "Until saved, changes only affect the current app session."))
    st.markdown(
        f'<div class="leo-section-head leo-section-head--red"><span class="leo-section-dot"></span><span class="leo-section-overline">{tr(language, "GitHub 推送设置", "GitHub Push Settings")}</span><span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    wf_config, wf_nz_time, wf_us_time = deps.read_workflow_push_config()
    push_config_options = {name: path for name, path in deps.config_options().items() if name != "自定义路径"}
    push_config_names = list(push_config_options.keys())
    wf_config_name = next(
        (name for name, path in push_config_options.items() if str(path.relative_to(deps.app_root)) == wf_config),
        push_config_names[0],
    )
    push_cols = st.columns([2, 1, 1])
    push_selected_name = push_cols[0].selectbox(
        tr(language, "推送配置", "Push config"),
        push_config_names,
        index=deps.option_index(push_config_names, wf_config_name),
        key="push_config_select",
    )
    push_nz_time = push_cols[1].text_input(tr(language, "NZ 推送时间", "NZ push time"), value=wf_nz_time, placeholder="15:45", key="push_nz_time")
    push_us_time = push_cols[2].text_input(tr(language, "US 推送时间", "US push time"), value=wf_us_time, placeholder="15:00", key="push_us_time")
    st.caption(tr(language, "时间格式 HH:MM（本地时间）。NZ 时间对应 Pacific/Auckland，US 时间对应 America/New_York。", "Format HH:MM (local time). NZ uses Pacific/Auckland, US uses America/New_York."))
    push_action_cols = st.columns([1, 1, 2])
    if push_action_cols[0].button(tr(language, "保存推送设置", "Save push settings"), type="primary", use_container_width=True):
        selected_path = push_config_options[push_selected_name]
        rel = str(selected_path.relative_to(deps.app_root)) if push_selected_name != "默认配置" else deps.default_push_config
        ok, msg = deps.update_workflow_github(rel, push_nz_time.strip(), push_us_time.strip())
        if ok:
            st.success(f"{tr(language, '推送设置已保存。', 'Push settings saved.')} {msg}")
        else:
            st.error(f"{tr(language, '保存失败', 'Save failed')}: {msg}")
    if push_action_cols[1].button(tr(language, "恢复默认配置", "Restore defaults"), use_container_width=True):
        ok, msg = deps.update_workflow_github(deps.default_push_config, deps.default_nz_time, deps.default_us_time)
        if ok:
            st.success(f"{tr(language, '已恢复为默认配置。', 'Restored to default config.')} {msg}")
        else:
            st.error(f"{tr(language, '恢复失败', 'Restore failed')}: {msg}")
    st.markdown(
        f'<div class="leo-section-head leo-section-head--green"><span class="leo-section-dot"></span><span class="leo-section-overline">{tr(language, "系统版本", "System Version")}</span><span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    st.metric(tr(language, "当前版本", "Current version"), f"v{deps.version}")
    deps.release_notes_renderer(language)
