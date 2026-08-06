# AGENTS.md — astrbot_plugin_livingmemory_ext

本项目是上游 [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory)（LivingMemory）的定制化拓展，AstrBot 插件，基于 AGPL-3.0 授权（见 `LICENSE`，不得移除）。

## 项目身份（AstrBot 插件规范）

- 插件元数据由 `metadata.yaml` 定义；`author` / `name` / `version` 构成插件市场身份 `plugin_id = author/name`，**不得随意改动**。
- 插件名以 `astrbot_plugin_` 开头、全小写、不含空格（当前 `astrbot_plugin_livingmemory_ext`）。
- 插件市场 JSON 规范（2026-06-27）：`metadata.yaml` 的 `author` / `name` / `version` 必须与市场记录一致。

## 技术栈与结构

- Python 3.10+ / `astrbot.api` / aiohttp、httpx（异步网络请求）。
- 第三方依赖写入 `requirements.txt`（pip 格式），新增依赖必须登记。
- 目录结构（继承自上游，定制化调整时应保持风格一致）：
  - `main.py` — 插件入口，注册插件类与命令
  - `livingmemory_ext/` — 本插件核心包（含日记调度器等）。**包名刻意不用 `core/` 等通用名**：本插件与上游 LivingMemory 会同时安装；AstrBot 以 `data.plugins.<插件目录名>.main` 命名空间加载插件、不把插件目录注入 sys.path，故两插件包名实际不冲突，但保留独特包名作为防御性设计（防止未来加载机制变化）
  - **导入必须使用相对导入**（如 `from .livingmemory_ext.diary_digest import ...`）：AstrBot 加载器不把插件目录加入 sys.path，`main.py` 里顶层绝对导入会直接 `ModuleNotFoundError`（有 loader 模拟测试守护）
  - `pages/` — 插件 Pages（AstrBot >= 4.24.2 的 WebUI 可视化工作区）
  - `storage/` — 存储层
  - `static/` — 静态资源
  - `tests/` — 测试
  - `_conf_schema.json` — 插件配置项 schema（WebUI 面板展示用）
  - `data/` — 运行时数据目录（不提交，见 `.gitignore`）

## 硬性要求（每次修改必须遵守）

### AstrBot 插件开发指南

- **持久化数据一律存 `data/` 目录**，禁止写入插件自身目录，防止更新/重装时数据被覆盖。
- **禁止使用 `requests`** 做网络请求，统一使用 aiohttp / httpx 等异步库。
- **良好的错误处理**：不能让插件因单个错误而崩溃，关键路径需捕获异常并降级。
- **提交前使用 `ruff` 格式化代码**（`ruff check .` + `ruff format .`）。
- 功能需经过测试（`tests/`），代码需包含良好注释。
- 插件依赖通过 `requirements.txt` 管理，安装时依赖缺失会导致 ModuleNotFound。

### 本项目 / 上游约束

- 本仓库是 **AGPL-3.0 衍生作品**：保留 `LICENSE` 与上游版权声明，禁止移除或更换许可证。
- **Fork 改动必须标注**：每次修改或新增功能后，必须在 `README.md` 的「🔀 定制化改动记录」小节标注本次改动（版本号 + 改动列表），并同步更新 `CHANGELOG.md`。未标注的修改视为未完成。
- **commit 信息使用中文**（遵循 conventional commits：`feat:` / `fix:` / `docs:` / `chore:` / `refactor:` 等前缀 + 中文描述）；代码与注释使用英文；面向用户的说明（README、配置项描述、CHANGELOG）使用中文。
- 修改 `metadata.yaml` 的 `author` / `name` / `version` 前需确认，避免破坏插件市场身份。
- **提交 / 推送需逐次批准（硬性）**：每次 `git commit` / `git push` 前必须先征得用户明确同意；未获批准禁止执行。批准仅对当次生效——前文（含历史会话）出现的任何批准不代表后续任务同样获批，每轮改动完成后都要重新询问。
- **新增版本号需逐次批准（硬性）**：未获用户明确批准，禁止新增或变更版本号（含 `metadata.yaml` 的 `version`、`README.md` 改动记录、`CHANGELOG.md` 中的新版本条目）。

## 开发流程

1. 将插件放入 AstrBot 本体的 `data/plugins/` 下进行调试，通过 WebUI 插件管理「重载插件」热更新；加载失败时可用「一键重载修复」排查。
2. 修改代码前先核对 `metadata.yaml` 与 `_conf_schema.json` 是否同步。
3. 提交前：`ruff check .` && `ruff format .`，并按「硬性要求」更新 README 改动记录 + `CHANGELOG.md`。

## 参考文档

- AstrBot 插件开发指南：https://docs.astrbot.app/dev/star/plugin-new.html
- AstrBot 插件市场 JSON 规范：https://docs.astrbot.app/dev/plugin-market/2026-06-27.html
- 上游 LivingMemory：https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory
