# UI 审查交叉比对报告

生成时间：2026-05-17  
比对对象 A：`LEOLRS0-3`（Streamlit + Python 动态 CSS 注入）  
比对对象 B：`risk_tool_complete`（静态 HTML/CSS/JS + React/TypeScript）

---

## 总览

两份报告覆盖完全不同的技术栈，但四个审查维度出现了高度结构性一致的根因模式。
问题不是偶发的渲染错误，而是**设计层和结构层的静态缺陷**，在两个项目中以不同形式重复出现。

---

## 维度 1：文字与颜色错误

### 对比

| | `risk_tool_complete` | `LEOLRS0-3` |
|---|---|---|
| 现象 | 中英混排，部分模块保留英文原型文案 | 奶油色文字叠白底，对比度约 1.09:1，文字几乎不可见 |
| 根因 | 无统一 i18n 层，文案直接硬编码在模板和脚本里 | `_ui_theme()` 默认值硬编码为 `"dark"`，但背景色从未设为暗色 |

### 共同模式

**系统级默认值或初始值设计不完整。**

两个项目都在系统层埋下错误，而不是某一个控件写错了颜色或文字。

- `risk_tool_complete` 缺少的是 i18n 系统。没有这一层，每次本地化都是手工覆盖，部分模块自然漏掉。
- `LEOLRS0-3` 缺少的是 theme 系统的另一半。token 系统（文字色）被实现了，但 background 系统没有配套，导致文字 token 有值、背景是空洞。

### 修复思路

不是改一个值，是**补全一个系统**。

- `risk_tool_complete`：建立统一语言资源层，将文案从模板和脚本中剥离。
- `LEOLRS0-3`：在 `_render_theme_override`（`gui.py:1223`）中同时设置 `background-color`，让 token 和 background 成对出现。

---

## 维度 2：内容溢出

### 对比

| | `risk_tool_complete` | `LEOLRS0-3` |
|---|---|---|
| 现象 | 当前未触发溢出，`min-width: 220px` 的状态块被响应式断点「兜住」 | `trade-timeline-wrap` 实际溢出 10px，`overflow: visible` 使内容出界 |
| 根因 | 固定 `min-width` 在窄屏依赖外层媒体查询保护，组件本身不稳健 | Timeline 内部百分比定位精度造成轻微累积误差 |

### 共同模式

**溢出靠外部机制托底，组件本身不自持边界。**

两个项目都指向同一个设计问题：组件的边界不由组件自己管理。

- `risk_tool_complete`：状态块靠媒体查询救场，换一个断点策略就会暴露。
- `LEOLRS0-3`：timeline 靠 `overflow: visible` 放任内容出界，不裁切也不滚动。

### 严重程度差异

`LEOLRS0-3` 的问题更紧迫，溢出已真实发生。`risk_tool_complete` 是潜在风险，当前内容较短因此未触发。

---

## 维度 3：排版不符合网格规范

### 对比

| | `risk_tool_complete` | `LEOLRS0-3` |
|---|---|---|
| 现象 | `.two-col` 在主表单和 `.advanced` 两个层级复用，因内边距不同导致列线错位 | `.app-shell-nav` CSS 靶向未注入 DOM 的类，导航 flex 布局完全失效 |
| 根因 | 网格工具类被用在不同可用宽度的容器里，隐性假设容器等宽 | CSS 选择器和 DOM 结构脱节，`st.columns()` 不输出 `.app-shell-nav` |

### 共同模式

**CSS 与 DOM 结构之间存在隐性假设，假设被违反时布局静默失效，没有报错。**

- `risk_tool_complete`：`.two-col` 隐式假设「可用宽度一致」，`.advanced` 引入额外 padding 破坏了这个假设。
- `LEOLRS0-3`：CSS 隐式假设「导航容器会有 `.app-shell-nav` class」，Streamlit 的 `st.columns()` 不输出这个类，规则命中空集。

两者都属于**隐性契约被静默违反**，没有错误提示，只有样式默默失效。

---

## 维度 4：边框缺失

### 对比

| | `risk_tool_complete` | `LEOLRS0-3` |
|---|---|---|
| 现象 | 主按钮先被通用规则赋予边框，再被后置规则覆盖为 `border: none`；状态块不在任何边框体系内 | `.app-shell-nav` 边框规则靶向空 DOM；Metric 和 section head 边框透明度仅 18%，视觉上等同无边框 |
| 根因 | 通用控件和按钮样式优先级冲突；状态块游离于视觉体系之外 | 边框选择器孤立；边框存在但不透明度过低 |

### 共同模式

**视觉规范没有决定「哪些元素属于描边体系」，导致各组件自行决策，边框策略分裂。**

两个项目的边框问题形式不同：

- `risk_tool_complete`：**显式去边框**，`border: none` 覆盖通用规则。
- `LEOLRS0-3`：**隐式消失边框**，18% 透明度在视觉效果上等同于无边框。

但根因相同：没有一份规范明确定义「描边体系的成员资格」。

---

## 四个跨项目共同模式汇总

| 模式 | `risk_tool_complete` 表现 | `LEOLRS0-3` 表现 |
|------|--------------------------|-----------------|
| 系统默认值不完整 | 无 i18n 层，文案手工维护导致部分漏译 | theme 系统只实现 token，background 无配套 |
| 组件游离于视觉体系 | `.status` 不属于卡片也不属于控件 | `.app-shell-nav` CSS 与 DOM 脱节 |
| 隐性假设静默失效 | `.two-col` 假设容器等宽 | CSS 假设 DOM 有某个类 |
| 边框策略无统一规范 | 按钮先有边框再被覆盖去掉 | 边框透明度过低，视觉上不存在 |

---

## 严重程度对比

两份报告在当前可用性上有明显差距：

| | `risk_tool_complete` | `LEOLRS0-3` |
|---|---|---|
| 整体状态 | 当前大多可用，存在风险但未触发 | 当前已损坏，主要问题用户可直接感知 |
| 文字颜色 | 中英混排，文字可读 | 白底奶油字，文字几乎不可见 |
| 溢出 | 未触发，靠外层保护 | 已发生 10px 实际溢出 |
| 导航布局 | 尚无类似问题 | 导航 CSS 完全失效，按钮从零散规则继承样式 |
| 边框 | 视觉语言不一致，尚可辨识 | 边框透明度极低，视觉分层几乎消失 |

**结论：**
- `LEOLRS0-3` 需要立即修复，当前界面状态已影响基本可用性。
- `risk_tool_complete` 需要系统性重构，可以分阶段推进，不影响当前使用。

---

## 相关文件速查

### LEOLRS0-3

| 文件 | 问题 |
|------|------|
| `trend_system/gui.py:107–109` | `_ui_theme()` 默认值为 `"dark"` |
| `trend_system/gui.py:1223–1309` | `_render_theme_override` 注入暗色 token 但从未设置背景色 |
| `trend_system/gui.py:1286–1288` | Metric 背景覆盖使用暗色 fill |
| `trend_system/interfaces/streamlit/app_shell.py:43–96` | `.app-shell-nav` class 从未注入 DOM |
| `trend_system/interfaces/streamlit/shared/tradingview_chart.py` | 图表颜色硬编码，无 token 引用 |

### risk_tool_complete

| 文件 | 问题 |
|------|------|
| `simple_web_now/index.html:13,14,33` | 标题、方向选项硬编码英文 |
| `simple_web_now/app.js:55,59` | 结果标签硬编码英文 |
| `simple_web_now/styles.css:67` | 状态块无边框，游离于描边体系 |
| `simple_web_now/styles.css:104,139` | 按钮边框先定义后覆盖为 `none` |
| `simple_web_now/styles.css:115,121` | `.two-col` 跨层级复用导致列线错位 |
| `tauri_risk_web/src/App.tsx:28,31` | 整页仍为英文原型文案 |
| `tauri_risk_web/src/styles.css:91` | 长路径强制断字，牺牲可读性换溢出防护 |
