# UI 系统级审查报告

> 审查时间：2026-05-17  
> 审查应用：localhost:8501（`/Users/leolinum/Documents/LEOLRS0-3`）  
> 框架：Streamlit + 自定义 Leo 设计系统

---

## 先行报告（快速摘要）

| 等级 | 问题 | 文件 | 行号 |
|------|------|------|------|
| 🔴 严重 | 暗色文字 token 叠白色背景 — 文字几乎不可见 | `gui.py` | 107–109, 1223–1309 |
| 🔴 严重 | Metric 卡片背景极黑叠白页面 — 形成深色孤岛 | `gui.py` | 1286–1288 |
| 🟠 高 | `.app-shell-nav` CSS 靶向不存在的 class — 导航样式完全孤立 | `app_shell.py` + `gui.py` | 43–91 / 1293–1305 |
| 🟠 高 | 暗模式无背景色 — `body` 始终白色，token 无处覆盖 | `gui.py` | 1253–1276 |
| 🟡 中 | Timeline 溢出：`trade-timeline-wrap` scrollWidth 超出 10px | `gui.py` | ~3081 |
| 🟡 中 | Section head 边框极淡：`rgba(18,57,91,0.18)` | `gui.py` | 630–667 |
| 🟢 低 | 混用 rem/px、颜色值硬编码绕过 CSS 变量 | 多文件 | — |

---

## 详细报告

### 1. 🔴 文字颜色错误（严重）

**现象：** 全局文字颜色 `rgba(244, 240, 232, 0.92)`（奶油白）叠在白色背景 `rgb(255, 255, 255)` 上，WCAG 对比度约 1.09:1，远低于 AA 最低要求 4.5:1，文字几乎不可见。

**根因链路：**

```
gui.py:108   _ui_theme() → 默认返回 "dark"（未设置时硬编码兜底）
                ↓
gui.py:1209  _render_theme_override("dark") 被调用
                ↓
gui.py:1224  theme == "dark" 分支注入：
               --leo-ink:      rgba(244, 240, 232, 0.92)  ← 奶油白文字
               --text-color:   rgba(244, 240, 232, 0.92)
               --panel-fill-a: rgba(26, 29, 31, 0.74)     ← 极深背景 fill
                ↓
  ❌ body { background-color: rgb(255,255,255) }  ← Streamlit 默认白底，从未被覆盖
```

**实测计算样式（浏览器 DevTools 确认）：**

```
body.backgroundColor  = rgb(255, 255, 255)          ← 白底
body.color            = rgba(244, 240, 232, 0.92)   ← 奶油字 → 不可见
stApp.backgroundColor = rgb(255, 255, 255)          ← 同上
```

**关键代码（`gui.py:107–109`）：**

```python
def _ui_theme(settings: dict[str, Any]) -> str:
    selected = st.session_state.get("ui_theme") or settings.get("ui", {}).get("theme", "dark")
    return selected if selected in {"dark", "light"} else "dark"
    #                                                           ^^^^ 默认值是 "dark"
```

---

### 2. 🔴 Metric 卡片深色孤岛（严重）

**现象：** Metric 卡片实际背景为：

```css
linear-gradient(145deg, rgba(26,29,31,0.74) 0%, rgba(0,0,0,0.22) 55%, rgba(174,143,84,0.025) 100%)
```

极深色渐变叠在白色页面上，形成明显的「深色孤岛」，视觉严重割裂。

**根因：** 同上。`_render_theme_override("dark")` 将 `--panel-fill-a` 设为 `rgba(26,29,31,0.74)`，`gui.py:1287` 的 Metric 背景覆盖规则强制使用该值并带 `!important`。

---

### 3. 🟠 `.app-shell-nav` CSS 孤立（高）

**现象：** `app_shell.py`（第 52 行起）及 `gui.py:1293` 的覆盖规则均选择 `.app-shell-nav .stButton > button`，但此类名**从未注入 DOM**。

**根因：**

```python
# app_shell.py:96
nav_cols = st.columns(len(page_labels))
# Streamlit 渲染为 [data-testid="stHorizontalBlock"]，没有 .app-shell-nav
```

`document.querySelector('.app-shell-nav')` → `null`

导航 flex 布局（`flex-wrap`, `gap: 0.5rem`）、悬停、激活态渐变背景样式**全部失效**。按钮从其他零散规则中继承了透明背景 + 金色边框，但并非预期行为。

---

### 4. 🟠 暗模式缺少背景色（高）

**现象：** `_render_theme_override` 的 CSS 块（`gui.py:1256–1276`）对 `:root, html, body, .stApp` 设置了 token 变量，但**从未设置 `background-color`**，导致 Streamlit 默认白底始终生效。

**在 `gui.py:1256–1276` 的选择器块中缺少：**

```css
/* 暗模式应补充 */
background-color: #1A1D1F;
color: var(--text-color);
```

---

### 5. 🟡 Timeline 内容溢出（中）

**实测数据：**

| 元素 | actualWidth | scrollWidth | 溢出 |
|------|------------|-------------|------|
| `trade-timeline-wrap` | 980px | 990px | **10px** |
| `trade-timeline-head` | 948px | 948px | 无 |
| `trade-timeline-row` | 948px | 948px | 无 |

`overflow: visible` 使溢出内容可见但不可滚动，右侧 deadline marker 或 segment 可能被父容器 `overflow-x: hidden` 截断。

---

### 6. 🟡 Section Head 边框极淡（中）

**现状：**

```css
.leo-section-head--prussian { border-bottom: 1px solid rgba(18,57,91,0.18); }
```

18% 不透明度在任何背景（白底或深底）下均几乎不起分隔作用，视觉层次缺失。

---

### 7. 🟢 其他低优先级

- **`tradingview_chart.py`：** 图表调色板硬编码 8 色 hex（`#2563eb`, `#dc2626` 等），不跟随 Leo token，无暗模式适配
- **`app_shell.py`：** 导航按钮颜色直接写 `rgba(...)` 而非引用 `var(--leo-surface-rim)` 等 token
- **`preparing.py`：** 同时使用 `rem` 和 `px`，无统一间距尺度（如 `gap: 0.9rem` 和 `margin: 8px` 混用）

---

## 排版与网格问题

- 导航区无 `.app-shell-nav` flex 容器，按钮间距继承 Streamlit 默认列间距（`16px gap`）而非设计稿的 `0.5rem`
- 所有页面 metric 行均用 `st.columns(4)` 均匀布局，缺乏响应式断点，窄屏会挤压内容
- `ctrl_cols = st.columns([2, 1.2, 2, 0.8])` 中第 4 列（PDF 按钮）在窄布局下可能溢出

---

## 边框状态一览

| 元素 | 边框现状 | 问题 |
|------|---------|------|
| `[data-testid="stMetric"]` | `2px solid rgba(174,143,84,0.18)` | 存在但极淡（18% 透明度） |
| `.leo-section-head--prussian` | `border-bottom: 1px solid rgba(18,57,91,0.18)` | 存在但极淡 |
| `.app-shell-nav button` | `1px solid rgba(174,143,84,0.30)` | 选择器孤立，规则实际未命中 |
| `.strategy-console-intro` | `2px solid var(--leo-surface-rim)` | 正常 |
| `trade-timeline-wrap` | 无边框 | 符合设计意图 |

---

## 涉及文件速查

| 文件路径 | 主要问题 |
|---------|---------|
| `trend_system/gui.py:107–109` | `_ui_theme()` 默认值为 "dark" |
| `trend_system/gui.py:1223–1309` | `_render_theme_override` 注入暗色 token 但从未设置背景色 |
| `trend_system/gui.py:1286–1288` | Metric 背景覆盖规则使用暗色 fill |
| `trend_system/interfaces/streamlit/app_shell.py:43–96` | `.app-shell-nav` class 从未注入 DOM |
| `trend_system/interfaces/streamlit/shared/tradingview_chart.py` | 图表颜色硬编码，无 token 引用 |
| `trend_system/interfaces/streamlit/shared/preparing.py` | rem/px 混用 |
