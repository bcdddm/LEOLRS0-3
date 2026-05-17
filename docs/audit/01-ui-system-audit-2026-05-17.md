# UI 系统级审查报告

日期：2026-05-17  
状态：已归档（问题已在 `codex/ui-rebuild-baseline` 分支修复）

## 被审查的应用

- **运行端口：** localhost:8501（主目录 `/Users/leolinum/Documents/LEOLRS0-3`）
- **框架：** Streamlit + 自定义 Leo 设计系统
- **CSS 注入方式：** Python 内 `st.markdown(unsafe_allow_html=True)` 多点注入
- **审计提交：** `7495af7316d1ef93f1f35eb53cff536356ef262b`

---

## 先行报告（快速摘要）

| 等级 | 问题 | 文件 | 行号 | 修复状态 |
|------|------|------|------|----------|
| 🔴 **严重** | 暗色文字 token 叠白色背景 — 文字几乎不可见 | `gui.py` | 107–109, 1223–1309 | ✅ 已修复：`--leo-page-bg` + `base.css` 背景锚定 |
| 🔴 **严重** | Metric 卡片背景极黑（dark fill）叠白页面 — 形成孤岛 | `gui.py` | 1286–1288 | ✅ 已修复：token 系统统一后卡片背景跟随主题 |
| 🟠 **高** | `.app-shell-nav` CSS 靶向不存在的 class — 导航样式完全孤立 | `app_shell.py` + `gui.py` | 43–91 / 1293–1305 | ✅ 已修复：改写为 `:has([class*="st-key-app_shell_nav"])` 选择器 |
| 🟠 **高** | 暗模式无背景色 — body 始终白色，token 无处可覆盖 | `gui.py` | 1253–1276 | ✅ 已修复：`base.css` 补全 `.stApp` + `body` 背景色绑定 |
| 🟡 **中** | Timeline 溢出：`trade-timeline-wrap` scrollWidth 超出 10px | `gui.py` | ~3081 区域 | ⚠️ 未最终验证 |
| 🟡 **中** | Section head 边框极淡：`rgba(18,57,91,0.18)` | `gui.py` | 630–667 | ⚠️ 待后续提升可见度 |
| 🟢 **低** | 混用 rem/px 无统一尺度，部分颜色值绕过 CSS 变量硬编码 | 多文件 | — | 🔲 待后续统一 |

---

## 详细报告

### 1. 🔴 文字与颜色错误（严重）

**现象：** 全局文字颜色 `rgba(244, 240, 232, 0.92)`（奶油白）叠在白色背景 `rgb(255, 255, 255)` 上，WCAG 对比度 ≈ 1.09:1，远低于 AA 最低要求 4.5:1。文字几乎不可见。

**根因追踪：**
```
gui.py:108  _ui_theme() → 默认返回 "dark"
                ↓
gui.py:1209 _render_theme_override("dark") 被调用
                ↓
gui.py:1224 theme == "dark" 分支：
              text_color = "rgba(244, 240, 232, 0.92)"  ← 奶油白文字 token
              panel_fill_a = "rgba(26, 29, 31, 0.74)"   ← 极深背景 token
                ↓
gui.py:1253 st.markdown 注入：
              :root, html, body, .stApp {
                --leo-ink: rgba(244, 240, 232, 0.92);   ← 覆盖全局
                --text-color: rgba(244, 240, 232, 0.92);
              }
                ↓
  ❌ 但 body { background-color: rgb(255,255,255) }     ← Streamlit 默认白底从未被覆盖
```

**计算样式确认：**
- `body.backgroundColor = rgb(255, 255, 255)` ← 白底
- `body.color = rgba(244, 240, 232, 0.92)` ← 奶油字 → 不可见

**修复方式（已实施）：**
- `styles/tokens.css` 引入 `--leo-page-bg` 语义 token（light: `#F5F1EB`，dark: `#1A1D1F`）
- `styles/base.css` 为 `.stApp`、`body`、`[data-testid="stMain"]` 等全部容器绑定 `background-color: var(--leo-page-bg) !important`
- 移除了 Python 内 `_render_theme_override()` 的动态主题注入路径

---

### 2. 🔴 Metric 卡片深色孤岛（严重）

**现象：** Metric 卡片实际背景：
```css
linear-gradient(145deg, rgba(26,29,31,0.74) 0%, rgba(0,0,0,0.22) 55%, ...)
```
极深色渐变叠在白色页面上，形成明显的"深色孤岛"，与整体白底格格不入。

**根因：** `_render_theme_override("dark")` 将 `--panel-fill-a` 设为 `rgba(26,29,31,0.74)` 后，`gui.py:1287` 的 `[data-testid="stMetric"]` 背景覆盖规则强制使用该值；但页面背景从未被设置为深色，导致对比失调。

**修复方式（已实施）：**
- Metric 卡片背景改为引用 `var(--leo-surface-a)` / `var(--leo-surface-b)` — 这两个 token 在 light 主题下为半透明奶油白，在 dark 主题下为半透明深灰，均与页面背景协调
- 完整的深色背景补全后，深色孤岛问题自然消解

---

### 3. 🟠 `.app-shell-nav` CSS 孤立（高）

**现象：** `app_shell.py` 中的导航 CSS 选择器 `.app-shell-nav .stButton > button` 以及 `gui.py` 中的导航覆盖规则均靶向类名 `.app-shell-nav`，但此类名**从未被注入到 DOM**。

**根因：**
```python
# app_shell.py:96 — 使用 st.columns() 生成列，Streamlit 只输出 [data-testid="stHorizontalBlock"]
nav_cols = st.columns(len(page_labels))
# ← 没有任何代码将 .app-shell-nav class 添加到这个 div
```

`document.querySelector('.app-shell-nav')` → `null`

导航按钮实际样式来自其他规则（透明背景 + 金色边框），但专为导航设计的 flex 布局、间距、悬停、激活态样式全部失效。

**修复方式（已实施）：**
- `shell.css` 改写选择器为 `[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"])` — 靶向 Streamlit 实际生成的 widget key class，无需手动注入 DOM class
- 导航 flex 容器、按钮样式、active 状态、dark 模式覆盖全部已正常命中

---

### 4. 🟠 暗模式缺少背景色（高）

**现象：** `_render_theme_override` 的 CSS 块从未为 `body` 或 `.stApp` 设置 `background-color`，导致 Streamlit 默认白底始终生效。

**直接证据：** 对 `gui.py` 中所有 CSS 搜索 `background-color` + `body/stApp`，无任何深色背景规则。

**修复方式（已实施）：** 见问题 1 修复 — `base.css` 内统一补全，不再依赖 Python 端注入。

---

### 5. 🟡 Timeline 内容溢出（中）

**现象：**
- `trade-timeline-wrap`：actualWidth = 980px，scrollWidth = 990px → **溢出 10px**
- `overflow: visible` → 内容超出边界可见但不可滚动

**根因：** Timeline 内部元素（deadline markers、segment divs）使用百分比定位，但计算精度导致轻微超出宽度。

**当前状态：** ⚠️ 尚未验证修复。后续 Phase 5 精修阶段再处理。

---

### 6. 🟡 Section Head 边框极淡（中）

**现象：** `.leo-section-head--prussian { border-bottom: 1px solid rgba(18,57,91,0.18) }` — 18% 不透明度，在白底或深色背景下几乎不可见，起不到视觉分隔作用。

**当前状态：** ⚠️ 边框已存在，不透明度过低。待 Phase 5 精修阶段与整体 Section Head 组件治理一并解决。

---

### 7. 🟢 混合单位 + 硬编码颜色（低）

- `preparing.py` 同时使用 `rem` 和 `px`，无统一间距尺度
- `tradingview_chart.py` 的图表颜色调色板硬编码 8 色 hex，不跟随 Leo token，无暗色模式适配
- `app_shell.py` 的导航按钮颜色直接写 `rgba(...)` 而非引用 `var(--leo-*)` token

**当前状态：** 🔲 低优先级技术债，待后续 token 收口阶段处理。

---

## 排版与网格问题

- 导航区无 `.app-shell-nav` flex 容器，按钮继承 Streamlit 默认网格，间距 `16px`（来自 `st.columns gap`）→ **已修复**
- 所有页面 metric 行均用 `st.columns(4)` 均匀布局，但缺少响应式断点，窄屏会挤压 → **`components.css` 已补 `@media (max-width: 1024px)` 和 `(max-width: 480px)` 断点**
- `ctrl_cols = st.columns([2, 1.2, 2, 0.8])` 第4列（PDF按钮）在窄布局下会溢出 → **待处理**

---

## 边框状态一览

| 元素 | 边框现状 | 状态 |
|------|---------|------|
| `[data-testid="stMetric"]` | `2px solid var(--leo-surface-rim)` | ✅ 跟随 token |
| `.leo-section-head--prussian` | `border-bottom: 1px solid rgba(18,57,91,0.18)` | ⚠️ 极淡，待提升 |
| 导航按钮 | `1px solid rgba(174,143,84,0.30)` via `:has()` selector | ✅ 已正常命中 |
| `trade-timeline-wrap` | 无边框 | — 设计如此 |
| `.strategy-console-intro` | `2px solid var(--leo-surface-rim)` | ✅ 正常 |
| 所有输入框 / 选择框 | `border-image: metallic gold→green gradient` | ✅ 已实施（见重构日志 §14） |

---

## 涉及文件（原始）

| 文件 | 问题 |
|------|------|
| `trend_system/gui.py` | 根因：默认 dark、缺背景、token 覆盖 |
| `trend_system/interfaces/streamlit/app_shell.py` | `.app-shell-nav` class 未注入 DOM |
| `trend_system/interfaces/streamlit/shared/tradingview_chart.py` | 图表颜色硬编码，无主题适配 |
| `trend_system/interfaces/streamlit/shared/preparing.py` | rem/px 混用 |
