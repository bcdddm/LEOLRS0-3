# UI Visual Spec

状态：Draft v1  
生成时间：2026-05-17  
适用范围：`bcdddm/LEOLRS0-3` Streamlit UI 重构

## 1. 目的

这份文档定义 UI 重构的终态视觉标准。

它回答三个问题：

1. 什么叫"视觉完成"
2. 哪些视觉 token 必须被主题完整覆盖
3. 哪些元素属于同一视觉体系，不能各自为政

这份文档是后续以下工作的参考基线：

- CSS 提取
- Leo token 治理
- 组件抽离
- dark/light 主题修复
- 视觉等价性验证

## 2. 总体视觉语言

### 2.1 风格关键词

终态视觉语言采用以下关键词：

- 精密
- 冷静
- 有策略感
- 金属质感
- 数据驱动
- 稳定而非花哨

### 2.2 不追求的方向

不追求：

- 通用 SaaS 白板风
- 过度圆润的消费级卡片风
- 大量随机渐变和装饰性玻璃效果
- 页面之间视觉人格不一致

### 2.3 视觉核心

UI 的核心应体现为：

1. 信息分层清晰
2. 指标与状态有明确等级
3. 导航、控制、结果三大区域具有一致语言
4. light / dark 都完整成立，不允许只改文字不改背景

## 3. 主题模式

当前终态要求支持两套主题：

1. `light`
2. `dark`

## 4. 主题完整性要求

每个主题都必须完整覆盖以下视觉维度：

1. 页面背景
2. 主文字
3. 次级文字
4. 标题/overline/kicker
5. 面板背景
6. 控件背景
7. 描边颜色
8. accent 色
9. success / warning / error 状态色
10. hover / focus / active 状态
11. metric 卡片
12. timeline 区域

不允许出现：

- 浅色文字叠浅色背景
- 深色面板孤立漂浮在白页中
- token 切换后仅部分组件随主题变化

## 5. Token 体系

### 5.1 Token 分类

终态 token 至少分为以下五组：

1. Text
2. Surface
3. Border
4. Accent
5. Feedback

### 5.2 推荐命名

#### Text

- `--leo-text-primary`
- `--leo-text-secondary`
- `--leo-text-kicker`
- `--leo-text-inverse`

#### Surface

- `--leo-surface-page`
- `--leo-surface-panel`
- `--leo-surface-panel-elevated`
- `--leo-surface-control`
- `--leo-surface-chip`
- `--leo-surface-overlay`

#### Border

- `--leo-border-subtle`
- `--leo-border-default`
- `--leo-border-strong`
- `--leo-border-focus`

#### Accent

- `--leo-accent-primary`
- `--leo-accent-primary-hover`
- `--leo-accent-secondary`
- `--leo-accent-glow`

#### Feedback

- `--leo-feedback-success`
- `--leo-feedback-warning`
- `--leo-feedback-error`
- `--leo-feedback-neutral`

### 5.3 旧 token 兼容策略

历史 token 如：

- `--leo-ink`
- `--leo-ink-sub`
- `--leo-kicker`
- `--leo-surface-a`
- `--leo-surface-b`
- `--leo-surface-rim`

可以在过渡阶段保留映射，但不应继续扩散。

终态应逐步收敛到语义明确的 token 体系。

### 5.4 当前已实施 token（2026-05-17 进度）

| Token | 用途 | 状态 |
|-------|------|------|
| `--leo-page-bg` | 页面背景 | ✅ 已实施 |
| `--leo-ink` | 主文字 | ✅ 已实施 |
| `--leo-ink-sub` | 次级文字 | ✅ 已实施 |
| `--leo-kicker` | Overline 颜色 | ✅ 已实施 |
| `--leo-surface-a/b` | 面板渐变层 | ✅ 已实施 |
| `--leo-surface-rim` | 面板描边 | ✅ 已实施 |
| `--leo-racing-green` | 主 accent（赛车绿） | ✅ 已实施 |
| `--leo-metallic-gold` | 金属边框高光端 | ✅ 已实施（2026-05-17） |
| `--leo-metallic-green` | 金属边框主体色 | ✅ 已实施（2026-05-17） |
| `--leo-prussian-mineral` | 普鲁士蓝 accent | ✅ 已实施 |
| `--leo-palace-red` | 宫廷红 accent | ✅ 已实施 |

## 6. 描边体系

### 6.1 属于描边体系的元素

以下元素必须被视作同一描边体系成员：

1. 顶层 panel
2. Sidebar section plate
3. Sidebar control cluster
4. Metric card
5. Button
6. Input / select / text input
7. Timeline 容器
8. Status banner
9. Expander / module container
10. Section head 容器或其 rule 线

### 6.2 描边层级

描边至少分三级：

1. `subtle`
2. `default`
3. `strong`

#### `subtle`

用于：

- 次要分隔
- 柔性结构线

#### `default`

用于：

- 常规 panel
- 常规 input
- 常规状态块

#### `strong`

用于：

- active
- selected
- warning emphasis
- focus

### 6.3 输入框金属边框（2026-05-17 新增）

所有输入框、选择框、文本域采用两端式金属渐变描边：

```css
border-image: linear-gradient(
  135deg,
  var(--leo-metallic-gold) 0%,   /* 左上角金色高光 */
  var(--leo-metallic-green) 50%, /* 中段赛车绿主体 */
  var(--leo-metallic-gold) 100%  /* 右下角金色阴影 */
) 1;
```

聚焦时两色同步加深，并附加柔性绿色外发光。

适用范围：
- `[data-baseweb="input"]`
- `[data-baseweb="base-input"]`
- `[data-baseweb="select"] > div[data-baseweb="control"]`
- `[data-testid="stTextArea"] textarea`

不适用（圆角控件，改用纯色描边）：
- `[role="switch"]`
- `[data-baseweb="radio"] label`
- `div[data-testid="stSegmentedControl"]`

### 6.4 禁止事项

不允许出现：

1. 输入框有边框但按钮完全无边框，且无明确文档说明
2. 某个状态块完全游离于描边体系之外
3. 同一页面同等级 panel 使用不同描边逻辑

## 7. 文字体系

### 7.1 层级

文字至少分四层：

1. Page title
2. Section title / subheader
3. Kicker / overline
4. Body / caption / metadata

### 7.2 文案语言规则

在当前重构阶段，沿用：

- `shared/text.py` 的 `tr(language, zh, en)` 双语双写模式

因此终态要求：

1. 同一组件内不要混用"部分中文、部分英文硬编码"
2. 页面标题、section head、metric label、button label 必须走统一语言 helper
3. 不允许新增未经 `tr(...)` 包装的正式 UI 文案

### 7.3 可读性标准

任何主题下：

- 主文字与背景必须达到可读性要求
- 次级文字也必须可辨识
- caption 允许更轻，但不能"接近不可见"

## 8. 组件规范

### 8.1 Shell

Shell 包括：

- 页面标题带
- 导航区
- 页面整体节奏

要求：

1. 页面标题带应稳定、简洁、信息密度高
2. 导航必须表现为"主壳层"，不是普通按钮堆叠
3. 壳层不应与页面内容争抢视觉主导权

### 8.2 Section Head

Section head 是一个正式组件，不只是临时 `<div>`。

必须包含明确规则：

1. overline 文案
2. 点/标记
3. 分隔 rule
4. 主题适配

不允许：

- 只有极淡的一条线，起不到分段作用

### 8.3 Metric Card

Metric card 需要是独立组件。

必须统一：

1. 背景
2. 边框
3. 数值文字层级
4. label 文字层级
5. delta / badge / state 样式

不允许：

- metric 卡片在页面里形成无解释的视觉孤岛

### 8.4 Timeline

Timeline 需要作为独立组件治理。

必须统一：

1. 外层容器
2. track
3. segment
4. legend
5. countdown / action item

要求：

1. 不允许轻微超宽后靠 `overflow: visible` 装作没事
2. 边界和内容宽度关系必须明确

### 8.5 Sidebar Block

Sidebar 里的：

- section plate
- control cluster
- chip row

都属于组件，而不是散落 CSS。

要求：

1. 它们共享同一视觉家族
2. tone 变化只通过 token 或修饰符类表达

### 8.6 Button

Button 必须有明确层级：

1. primary
2. secondary
3. destructive
4. disabled

每种状态都要定义：

- background
- border
- text
- hover
- focus

### 8.7 Status Banner

Status banner 需要是独立视觉类型。

必须支持：

1. neutral
2. success
3. warning
4. error

并且属于描边体系，不允许只靠底色孤立存在。

## 9. 布局规范

### 9.1 页面层

页面布局遵循：

- shell
- controls
- metrics
- primary content
- secondary content

#### 原则

布局优先体现：

1. 策略操作顺序
2. 信息层次
3. 可扫描性

### 9.2 网格规范

网格类不能跨容器无约束复用。

必须区分：

1. 页面级网格
2. 面板级网格
3. 表单级网格
4. 子模块级网格

不允许：

- 同一个通用 `.two-col` 类在不同 padding 容器里直接复用，导致基线错位

## 10. CSS 组织规范

终态 CSS 目录（已实施）：

- `styles/tokens.css` ✅
- `styles/base.css` ✅
- `styles/shell.css` ✅
- `styles/components.css` ✅
- `styles/preparing.css` ✅

待建：

- `styles/pages/daily.css`
- `styles/pages/backtest.css`
- `styles/pages/market_health.css`
- `styles/pages/settings.css`

要求：

1. token 只在 `tokens.css`
2. 壳层规则只在 `shell.css`
3. 通用组件规则只在 `components.css`
4. 页面差异只在各自 page CSS

## 11. 主题切换机制

终态主题切换采用：

- 静态 CSS
- `data-theme` 属性切换

不采用：

- Python 内动态拼接整段主题 CSS 再注入

**当前状态（2026-05-17）：** ✅ 已实施。`inject_styles(theme)` 为纯渲染函数，`gui.py` 负责写 `data-theme`，不再动态生成 CSS 字符串。

## 12. 视觉等价性验证

在结构重构阶段，必须保留以下基线截图：

1. Daily 页面
2. Market Health 页面
3. Backtest 页面
4. Settings 页面

每张截图固定：

1. 语言
2. 主题
3. 窗口尺寸
4. 数据状态

**当前状态（2026-05-17）：** 🔲 截图基线尚未建立，为 Phase 5 精修前的必要前置工作。

## 13. 完成标准

终态视觉规范达标的最低标准：

1. light / dark 两个主题完整成立 — ✅ 已基本实施
2. 所有正式 UI 文案走统一语言 helper — ✅ 已实施
3. token 有唯一权威来源 — ✅ `tokens.css` 已建立
4. 描边体系统一 — ⚠️ 大部分已统一，Section head 边框强度待调整
5. Metric / Timeline / Section head / Sidebar block 成为独立治理对象 — ⚠️ 部分完成
6. 结构重构阶段与基线视觉等价 — 🔲 基线截图尚未建立
7. 不再依赖巨量 Python 内联 CSS 维持整体外观 — ✅ 已实施

## 14. 本文档后续更新项

后续还需要补充：

1. token 对照表（旧名 → 新名映射）
2. 组件示意图
3. 关键页面截图引用
4. light / dark 主题差异表
