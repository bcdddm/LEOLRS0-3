# UI 重构发展计划 v3

状态：Ready for Kickoff  
生成时间：2026-05-17  
进度更新：2026-05-17（Phase 1 & Phase 2 前半段已完成）

## 1. 计划目标

本计划用于指导 `bcdddm/LEOLRS0-3` 的 Streamlit UI 重构。

目标不是"顺手修几个 UI bug"，而是：

1. 保持 GitHub `main` 作为稳定产品主线
2. 在不切换技术栈的前提下，重构 UI 结构
3. 建立可治理的主题、组件、状态和样式体系
4. 以小步、可验证、可回滚的方式推进

## 2. 采用的基线

- GitHub 仓库：`bcdddm/LEOLRS0-3`
- 稳定基线分支：`main`
- 审计提交：`7495af7316d1ef93f1f35eb53cff536356ef262b`
- 工作树路径：`/Users/leolinum/Documents/LEOLRS0-3-ui-rebuild`
- 工作树分支：`codex/ui-rebuild-baseline`

这条基线是唯一产品主线。

当前 `risk_tool_complete` 中的：

- `simple_web_now`
- `tauri_risk_web`

只作为：

1. 审计样本
2. 风险案例
3. 原型参考

不作为正式重构主线。

## 3. 明确的终态

### 3.1 技术终态

本轮重构后仍然采用：

- `Streamlit`
- `app.py -> trend_system.gui.main()`

不在本轮中迁出到 React / Tauri / 独立 web 前端。

### 3.2 结构终态

终态 UI 结构应为：

- `app.py`
- `trend_system/gui.py`
- `trend_system/interfaces/streamlit/app_shell.py`
- `trend_system/interfaces/streamlit/page_registry.py`
- `trend_system/interfaces/streamlit/page_contracts.py`
- `trend_system/interfaces/streamlit/pages/*`
- `trend_system/interfaces/streamlit/components/*`
- `trend_system/interfaces/streamlit/shared/*`
- `trend_system/interfaces/streamlit/styles/*`

### 3.3 视觉终态

视觉终态以 [docs/audit/03-visual-spec.md](./03-visual-spec.md) 为准。

必须满足：

1. light / dark 两套主题完整成立
2. token 唯一来源
3. 描边体系统一
4. 页面以下引入组件层
5. 关键页面通过视觉等价性验证

## 4. 关键设计决策

### 决策 1：继续 Streamlit

本轮不迁技术栈。

原因：

1. `main` 已稳定运行
2. 已有壳层、页面注册、共享层和服务解耦骨架
3. 当前问题主要是 UI 治理，不是框架不可用

### 决策 2：继续沿用双语双写 helper

继续使用：

- `shared/text.py`
- `tr(language, zh, en)`

本轮不迁移到独立 translations JSON/资源层。

原因：

1. 稳定基线已采用这一模式
2. 行为明确
3. 避免结构重构和文案系统迁移同时发生

### 决策 3：废弃动态主题注入主模式

本轮必须逐步终止：

- 在 Python 中动态拼接整段主题 CSS
- 通过 `_render_theme_override` 一类函数注入变量和颜色

替代为：

1. 静态 CSS 文件定义 token
2. Python 只负责设置 `data-theme`

**状态：** ✅ 已完成（2026-05-17）

### 决策 4：页面不是最小治理单位

必须建立组件层。

第一批治理对象：

1. `MetricCard`
2. `SectionHead` — ✅ 已完成
3. `Timeline`
4. `SidebarSectionPlate` — ✅ 已完成
5. `SidebarControlCluster` — ✅ 已完成
6. `StatusBanner`
7. `PreparingPanel` — ✅ 已完成
8. `ShellTitleBand` — ✅ 已完成

## 5. 现存核心问题

当前重构前的主要风险不是"单点 bug"，而是系统性治理缺失：

1. `gui.py` 过重 — ⚠️ 改善中，参数扫描逻辑仍在内
2. 样式与 Python 逻辑强耦合 — ✅ 主要路径已解耦
3. token 定义分散 — ✅ 已收口到 `tokens.css`
4. `session_state` 全局散布 — ✅ `SessionKeys` 已建立，27 个 key 集中管理
5. 组件边界缺失 — ⚠️ 第一批已建，更多待续
6. 回滚和验证机制缺失 — ⚠️ 静态断言已加，浏览器 QA 未完整

## 6. 发展阶段

### Phase 0：视觉冻结

目标：

- 不主动改变视觉结果
- 固定视觉规范和截图基线
- 为结构重构建立验证边界

产出：

1. `docs/audit/03-visual-spec.md` ✅
2. 关键页面截图基线 🔲
3. 样式提取方案 ✅

完成标准：

1. 关键页面有截图基线 🔲
2. 视觉规范文档可作为 review 标准 ✅

**整体状态：** ⚠️ 规范已建，截图基线缺失

---

### Phase 1：样式与主题收口

目标：

- 建立 `styles/` 目录
- 确立 token 唯一来源
- 建立统一注入入口

产出：

1. `styles/tokens.css` ✅
2. `styles/base.css` ✅
3. `styles/shell.css` ✅
4. `styles/components.css` ✅
5. `shared/theme.py` ✅
6. `inject_styles()` 统一入口 ✅

完成标准：

1. 关键 token 不再散落在多个 Python 字符串中 ✅
2. `gui.py` 中大段 CSS 开始显著减少 ✅

**整体状态：** ✅ 完成

---

### Phase 2：Session State 治理

目标：

- 给 session key 划分所有权
- 建立 key 命名规范
- 把壳层状态、页面状态、缓存状态分层

产出：

1. `shared/session_state.py` ✅（含 `SessionKeys` 和 `migrate_legacy_keys()`）
2. 统一 key 常量 ✅（27 个）
3. 初始化与 helper ✅

待完成：

- 参数扫描逻辑从 `gui.py` 迁出 🔲
- `settings_pending_delete` 语义收窄 🔲
- 浏览器 QA：主题切换全流程、参数扫描 end-to-end 🔲

完成标准：

1. 不再随意新增无前缀 key ✅
2. 页面状态与壳层状态边界清晰 ⚠️

**整体状态：** ⚠️ 前半段完成，参数扫描提取待做

---

### Phase 3：组件层建立

目标：

- 抽出页面内重复视觉片段
- 让页面模块只承担装配职责

产出：

1. `components/section_head.py` ✅
2. `components/sidebar_panels.py` ✅
3. 组件专属样式归档 ⚠️（部分仍在 `components.css`）

完成标准：

1. Metric / Timeline / Section Head / Sidebar blocks 脱离页面文件 ⚠️
2. 页面文件显著缩短 ⚠️

**整体状态：** 🔲 尚未正式开始

---

### Phase 4：`gui.py` 瘦身

目标：

- 让 `gui.py` 回到协调器角色

职责保留：

1. 启动
2. page config
3. 全局初始化
4. 样式加载
5. 壳层装配
6. 页面依赖注入

完成标准：

1. `gui.py` 不再承载巨量 CSS ✅（已完成）
2. `gui.py` 不再直接管理大量页面内部视觉细节 ⚠️（参数扫描仍在内）

**整体状态：** 🔲 依赖 Phase 3 完成

---

### Phase 5：视觉与交互精修

目标：

- 修复此前审计中确认的 UI 风险
- 补齐主题一致性
- 优化导航和复杂组件

完成标准：

1. dark/light 完整成立 ⚠️（基本成立，主题切换全链路待验证）
2. 关键页面视觉一致 🔲
3. 旧技术债显著减少 ⚠️

**整体状态：** 🔲 尚未开始

---

## 7. Session State 策略

### 7.1 Shell 持有

由 shell 持有：

- `ui_theme`
- `ui_language`
- `app_shell_active_page`
- 全局 UI 偏好

### 7.2 页面持有

页面内状态必须加前缀：

- `daily_*`
- `market_health_*`
- `backtest_*`
- `settings_*`

### 7.3 缓存持有

缓存逻辑必须单独治理，不混入任意页面状态语义。

## 8. Leo Token 治理

### 8.1 唯一定义位置

最终仅允许：

- `styles/tokens.css`

作为 token 权威来源。✅

### 8.2 允许覆盖位置

只允许：

1. `:root`
2. `[data-theme="light"]`
3. `[data-theme="dark"]`

### 8.3 禁止事项

禁止新增：

1. 页面级硬编码主题主色
2. 组件内直接绕过 token
3. Python 动态生成新的主题 token 名

## 9. 回滚策略

### 9.1 分支策略

所有重构必须在独立分支上完成，不直接推 `main`。

### 9.2 阶段回滚

每个 phase 都必须能独立回退。

### 9.3 渐进替换

优先采用：

- 旧壳层保留
- 新样式先接入
- 新组件逐步替换

而不是一次性全站重写。

## 10. 视觉等价性验证

必须为以下页面建立截图基线：

1. Daily
2. Market Health
3. Backtest
4. Settings

要求固定：

1. 窗口尺寸
2. 主题
3. 语言
4. 数据状态

结构重构阶段以"与基线等价"为合格标准。

**当前状态：** 🔲 截图基线尚未建立，为 Phase 5 必要前置

## 11. 缓存策略

在重构期间，必须审计所有 `st.cache_*` 或等价缓存逻辑。

原则：

1. 尽量不改缓存函数语义
2. 如需改签名，要记录影响
3. 每次相关改动后验证加载性能

已知风险（2026-05-17 识别）：

- `_cached_parameter_sweep` 以 `dict`（含嵌套 `list`）作为参数，存在 `@st.cache_data` hash 不稳定风险（Streamlit Issue #10957）

## 12. 启动顺序

真正开工的顺序固定为：

1. 固定视觉规范 ✅
2. 固定截图基线 🔲
3. 提取 styles 目录 ✅
4. 建立 theme 加载入口 ✅
5. 治理 session state ✅
6. 抽第一批组件 ⚠️
7. 瘦身 `gui.py` ⚠️

## 13. 当前开工判断

现在已经具备开工前提：

1. 稳定基线已确认 ✅
2. UI 结构审计已完成 ✅
3. 视觉规范已建立 ✅
4. 重构计划已收敛为可执行路径 ✅

Phase 1 和 Phase 2 前半段均已完成。当前工作节点在 Phase 2 后半段（参数扫描提取）。

## 14. 下一步执行任务（2026-05-17 更新）

优先顺序：

1. **S1（紧急）** 浏览器验证参数扫描工作流全链路，确认结果表格是否在 expander 内不可见
2. **S1** 将参数扫描结果渲染移出 `st.expander` 上下文，改用 `st.status()` 展示进度
3. **S1** 补充 `--leo-sidebar-bg` token，显式控制侧边栏背景色
4. **S2** 修复语言切换控件（segmented control）的圆角意图被全局 reset 块覆盖问题
5. **S2** 建立首批关键页面截图基线（light + dark 各一套）
6. **S3** 将参数扫描逻辑从 `gui.py` 提取到 `backtest_page.py`
7. **S3** 继续缩减 `gui.py` 至协调器角色
