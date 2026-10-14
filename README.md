<div align="center">

# 🌟 lzl-skill

### 精选实用 AI Agent 技能库 · 赋能日常开发、创意生产与工作复盘
**A curated collection of battle-tested skills for AI Agents (Claude Code, Codex, ZCode & more).**

<p align="center">
  <img src="https://img.shields.io/badge/Author-sol-blue?style=flat-square" alt="Author" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome" />
</p>

[快速开始](#-快速开始) • [创意与媒体](#-1-创意与多媒体生产) • [工程与效率](#-2-工程质量与工作流) • [端侧与系统](#-3-端侧智能与系统管理) • [认知与文化](#-4-认知哲学与传统文化)

</div>

---

## 📖 项目简介

`lzl-skill` 是一个面向现实场景的高质量 Agent 技能合集。旨在将繁复的手工调试、多步重复劳动与代码审查工作沉淀为确定性、自包含、可移植的工程工具，全面兼容支持 `SKILL.md` 规范的 Agent 环境。

---

## 🧭 技能目录

### 🎨 1. 创意与多媒体生产
* **[anything2video](https://github.com/2021291696/anything2video)** — **代码驱动自动化视频生成引擎**
  输入主题或产品文案，自动编排分镜结构、配音旁白与 Remotion 动画，输出 1080P 高质感讲解视频。
* **[glassify](https://github.com/2021291696/glassify)** — **前端界面毛玻璃化改造 Skill**
  对已有前端项目（原生 CSS / Tailwind / Flutter）执行样式嗅探与安全重构，实现高透、优雅的现代毛玻璃拟态视觉。

---

### 💼 2. 工程质量与工作流
* **[logic-review](https://github.com/2021291696/logic-review)** — **代码与内容逻辑审查 Skill**
  代码 11 维 + 内容 7 维清单化逻辑审查。贯彻双态证据纪律，默认只审不修，有效拦截模型幻觉与架构缺陷。
* **[worklog-alllog](https://github.com/2021291696/worklog-alllog)** — **周报整理与工程备忘生成器**
  自动化扫描会话记录与 Git 变更，萃取关键需求叙事、履历素材与面向管理者的精简备忘。
* **[agent-git-workflow-skills](https://github.com/2021291696/agent-git-workflow-skills)** — **严谨型 Git 工作流套件**
  包含本地留痕（`git-record`）、防冲突安全推送（`git-push`）、主干对齐（`git-sync`）与变更报告（`change-report`），内置凭据防泄漏规则。

---

### 📱 3. 端侧智能与系统管理
* **[yunkai](https://github.com/2021291696/yunkai)** — **本地端侧手机 AI Agent**
  Android 11+ 与 HarmonyOS NEXT 双端原生实现。具备屏幕理解、写操作确认卡审批、手势执行与全本地长期记忆。
* **[weaver-evolve](https://github.com/2021291696/weaver-evolve)** — **Agent 自进化与知识维护 Skill 集群**
  Codex 与 Claude Code 双平台一等支持的四合一技能集群：以 `weaver-自我迭代` 为主协调器，协同调度 `memory-keeper`（即时记忆处理）、`file-tidy`（目录智能归位）与 `debug-architect`（根因复盘与防错规约），驱动 Agent 系统长期自进化。
* **[setup-tool](https://github.com/2021291696/setup-tool)** — **Agent 工具安装与验证管家**
  支持 Skill / Plugin / MCP / CLI / Binary / 桌面应用的自动化路由安装、环境核验与 Word 使用说明书生成。
* **[web-search-mcp](https://github.com/2021291696/web-search-mcp)** — **多后端联网搜索 MCP**
  支持 DuckDuckGo、Brave、Google 等主流引擎，动态探测可用后端，为 Agent 提供稳定联网检索能力。

---

### 🔮 4. 认知哲学与传统文化
* **[high-confidence-mingli-skill](https://github.com/2021291696/high-confidence-mingli-skill)** — **高置信度命理分析伴侣**
  八字 / 紫微斗数 / 七政四余三盘互译。依托置信度门禁与斯多葛克制语风，提供客观中立的命盘规律推演。
* **[fortune-observatory](https://github.com/2021291696/fortune-observatory)** — **高精度排盘观测网站**
  采用标准天文星历算法，配备现代互联网文化主题界面的命理排盘应用。
* **[Reflection](https://github.com/2021291696/Reflection)** — **桌面端内省与复盘应用**
  专注心境梳理与底层决策念头复盘，倡导工具为人服务的工程哲学。

---

## ⚡ 快速开始

项目内技能适配遵循通用 `SKILL.md` 规范的 Agent 环境（如 Claude Code、Codex、ZCode 等）。

### 单技能引入
进入目标仓库目录，按照仓库说明克隆或引入至对应的 `.agents/skills/` 目录。例如：
```bash
# 引入代码审查 Skill
git clone https://github.com/2021291696/logic-review.git
```

### 工具管家自动化配置
亦可加载 **[setup-tool](https://github.com/2021291696/setup-tool)**，通过交互式指令一站式完成依赖检测与路由装载。

---

## 🤝 贡献与交流

* **Star 支持**：若本项目对你的工作流有所启发，欢迎点亮右上角 ⭐ **Star**。
* **问题反馈**：若在使用中发现任何边界漏洞或有优化建议，欢迎提交 [Issues](https://github.com/2021291696/lzl-skill/issues)。

---

<div align="center">
  <sub>Created with precision by <a href="https://github.com/2021291696">sol</a></sub>
</div>