from __future__ import annotations

import streamlit as st

from trend_system.interfaces.streamlit.page_contracts import StreamlitPageContext


def render_future_module_page(context: StreamlitPageContext) -> None:
    """Reserved extension slot for a future standalone module."""
    if context.language == "en":
        st.info(
            "Reserved module slot. Add the future module service and then enable this page in the registry."
        )
    else:
        st.info("预留模块入口。未来新增模块时，先接入 service，再在 registry 中启用此页面。")
