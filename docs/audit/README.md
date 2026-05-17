# docs/audit — 审计报告目录

仓库：`bcdddm/LEOLRS0-3`  
工作树：`codex/ui-rebuild-baseline`  
最后更新：2026-05-18

---

## 文档导航

| 文件 | 类型 | 说明 |
|------|------|------|
| [01-ui-system-audit-2026-05-17.md](./01-ui-system-audit-2026-05-17.md) | 🔍 缺陷审计 | 对原始应用（`localhost:8501`）进行的 CSS 系统级审查，记录 7 类问题及根因 |
| [02-phase2-rebuild-log-2026-05-17.md](./02-phase2-rebuild-log-2026-05-17.md) | 📋 重构日志 | Phase 1 / Phase 2 重构进度记录，含已完成项、运行时验证结果、设计决策和待办缺口 |
| [03-visual-spec.md](./03-visual-spec.md) | 📐 视觉规范 | UI 视觉完成标准，定义 token 体系、描边层级、组件规范和验收标准 |
| [04-rebuild-plan-v3.md](./04-rebuild-plan-v3.md) | 🗺️ 重构计划 | Phase 0–5 执行路线图，含关键设计决策、分支策略和启动顺序 |
| [05-phase2-rebuild-log-2026-05-18.md](./05-phase2-rebuild-log-2026-05-18.md) | 📋 重构日志 | 参数扫描归属迁移、侧边栏背景收口、圆角冲突修复、mtime 缓存、浏览器验证完整记录 |
| [06-audit-2026-05-18.md](./06-audit-2026-05-18.md) | 🔍 员工审计 | 对 05 日志所有声明的逐项代码核实，独立发现 4 项结构问题，含修复优先级排期 |
| [07-phase3-completion-log-2026-05-18.md](./07-phase3-completion-log-2026-05-18.md) | 📋 重构日志 | 清理主题写入路径、迁移参数扫描 helper、完成双主题页面 QA 并建立截图基线 |
| [08-sidebar-ui-followup-2026-05-18.md](./08-sidebar-ui-followup-2026-05-18.md) | 📋 修补日志 | 配置侧边栏独立滚动、滑杆化、色彩语义收口、PDF 按钮方形化、导航点击修复 |
| [08-audit-phase3-2026-05-18.md](./08-audit-phase3-2026-05-18.md) | 🔍 综合审计 | Phase 3 完成声明核实 + 5 问题 / 5 风险 / 7 改进方案 + 白天模式失效根因专项排查（含锁定夜间模式推荐方案）|

---

## 快速定位

**找某个具体 bug 的根因** → `01-ui-system-audit`，看"详细报告"各节  
**了解当前做到哪里了** → `02-phase2-rebuild-log`，看 §2（已完成）和 §6（尚存缺口）  
**判断某个设计决策是否符合规范** → `03-visual-spec`，看对应组件或描边规则  
**排期下一步工作** → `02-phase2-rebuild-log` §7 + `04-rebuild-plan` Phase 2–5  

---

## 审计摘要

### 原始应用问题等级分布

| 等级 | 数量 | 状态 |
|------|------|------|
| 🔴 严重 | 2 | ✅ 均已在重构分支修复 |
| 🟠 高 | 2 | ✅ 导航选择器已修；背景色已补 |
| 🟡 中 | 2 | ⚠️ Timeline 超宽未最终验证；Section head 边框仍待调整 |
| 🟢 低 | 1 | 🔲 rem/px 混用和硬编码颜色待后续统一 |

### Phase 2 重构进度（截至 2026-05-18）

| 阶段 | 完成度 |
|------|--------|
| Phase 1: CSS 提取 + 主题入口 | ✅ 完成 |
| Phase 1→2 桥接：组件抽离 | ✅ 完成（SectionHead, SidebarPanels） |
| Phase 2: SessionKeys 集中 | ✅ 完成（27 个 key，静态断言覆盖） |
| Phase 2: 侧边栏背景收口 | ✅ 完成（`--leo-sidebar-bg` + base.css 绑定） |
| Phase 2: 主题切换浏览器验证 | ✅ 完成（light/dark DOM 值均已核实） |
| Phase 2: 参数扫描页面归属迁移 | ✅ 完成（入口与 helper 实现均已迁至 `backtest_page.py`） |
| Phase 2: 参数扫描浏览器验证 | ✅ 完成（5 阶段进度 + 全部结果区块可见） |
| Phase 2+: 金属绿输入框边框 | ✅ 完成（`--leo-metallic-gold/green` token + border-image） |
| Phase 3: 视觉 QA（全页 × 双主题） | ✅ 首轮完成（Daily / Market Health / Backtest / Settings，light + dark） |
| Phase 3: 截图基线 | ✅ 已建立（`docs/audit/screenshots/2026-05-18-phase3/`） |
| Phase 3+: 配置侧边栏细节修补 | ✅ 完成（独立滚动、slider 字色、趋势参数 slider、绿色手动控制、蓝色信息面板） |

---

## 验证指令

```bash
# 语法验证
python3 -m py_compile \
  trend_system/gui.py \
  trend_system/interfaces/streamlit/shared/session_state.py \
  trend_system/interfaces/streamlit/shared/theme.py \
  trend_system/interfaces/streamlit/pages/daily_page.py \
  trend_system/interfaces/streamlit/pages/market_health_page.py \
  trend_system/interfaces/streamlit/pages/backtest_page.py \
  trend_system/interfaces/streamlit/pages/settings_page.py

# 单元测试
pytest tests/test_streamlit_shared_helpers.py tests/test_streamlit_page_registry.py -q
```
