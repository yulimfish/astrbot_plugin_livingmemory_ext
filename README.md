<div align="center">

# LivingMemory Ext

<p><strong>为 AstrBot 构建的长期记忆插件 —— <a href="https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory">LivingMemory</a> 的定制化拓展。</strong></p>

<p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-f2e8e5?style=flat-square&labelColor=5b403a" alt="AGPL-3.0 许可证"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-e9f1ef?style=flat-square&labelColor=263a36" alt="Python 3.10 或更高版本">
  <img src="https://img.shields.io/badge/AstrBot-%3E%3D%204.24.2-f3eee4?style=flat-square&labelColor=544c3d" alt="AstrBot 4.24.2 或更高版本">
</p>

</div>

## ⚠️ 上游与协议声明

本项目是 [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory)（原作者：lxfight）的**定制化拓展**，与原项目同为 AstrBot 插件。

上游项目以 **GNU Affero General Public License v3.0（AGPL-3.0）** 发布。依据 AGPL-3.0 要求，本项目：

- 保留 AGPL-3.0 许可证与上游版权声明（见 [LICENSE](LICENSE)）；
- 本仓库整体以 AGPL-3.0 发布，任何衍生作品须继续以 AGPL-3.0 授权；
- 对上游代码的修改与新增内容同样受 AGPL-3.0 约束；
- 上游版权归 `lxfight-s-Astrbot-Plugins` 所有。

## 🔀 定制化改动记录

> 规则：每次功能改动必须在此处标注（版本号 + 改动列表），并同步更新 [CHANGELOG.md](CHANGELOG.md)。见项目 [AGENTS.md](AGENTS.md)。

### v0.1.1（新增：记忆日记）

- 新增「记忆日记」功能：在自定义时间拉取上游 LivingMemory 保存的当日记忆，总结为日记并发送到指定群聊。
- 支持多套发送规则：一个群聊 A 配置一个总结时间发到群聊 A，群聊 B 同理，可同时配置多套（总结范围 / 总结时间 / 发送位置）。
- 支持配置获取记忆的时间范围：每条规则可选 `今日 / 昨日 / 近 7 天`（`memory_range`），默认今日。
- 配置项为独立板块 `diary_digest`，支持手动开关、自定义总结提示词（首次安装内置默认提示词），总结时自动注入当前 AstrBot 人设。
- 依赖上游 LivingMemory 插件（读取其 `data/` 下的记忆库，只读）。
- 双插件共存适配：核心包命名避开 `core/` 等通用顶层包名（防御性设计），上游记忆库为 WAL 模式，本插件以只读连接 + busy_timeout 并发读取。
- 日志接入 AstrBot 日志体系：插件日志改用 AstrBot 专属 logger（`astrbot.plugin.*`），可在 WebUI「平台日志」页直接看到 `[DiaryDigest]` 运行日志，便于排查调度器是否触发。
- 消息平台适配器支持多选：`platform` 配置项新增 `qqab` / `qqofficial` 选项（此前仅 `aiocqhttp`），发送目标需与 WebUI「平台管理」中的实际适配器 id 及真实群号一致，否则消息会被 AstrBot 静默丢弃。
- 发送位置改为动态下拉选择：规则配置中「发送位置」与「消息平台」合并为一项 `send_to`，下拉选项由插件自动从当前平台拉取全部群聊（显示群名，支持输入搜索过滤），只能从下拉中选择；旧配置（纯群号 / 完整消息源格式）自动兼容。注：下拉依赖适配器提供群列表 API（aiocqhttp 支持；无该 API 的适配器下拉将只有已配置值）。
- 「范围目标」同样改为动态下拉：`scope_target`（总结范围为单群聊 / 单好友对话时）自动拉取当前平台的全部群聊与好友供下拉选择（带「群 / 好友」标识，支持输入搜索过滤），只能从下拉中选择；纯群号旧配置自动兼容（平台继承自发送位置）。
- 修复「记忆日记」群组 / 好友总结取不到记忆的问题：①好友类型键改用 AstrBot 标准的 `FriendMessage`（原 `PrivateMessage` 恒匹配失败）；②会话匹配不再锁死平台段前缀，兼容 qqab 等第三方适配器；③上游将群记忆归入全局范围（`session_id=livingmemory:global`）时，按其保留的 `source_session_id` 来源字段兜底匹配，群组规则仍能取到对应群的记忆。附带只读诊断脚本 `scripts/diagnose_memories.py`（输出库内会话分布，便于排查 0 条问题）。
- 日记规则新增「补充提示词」字段（`extra_prompt`，可选）：为单条规则追加额外的总结要求，拼接在插件级日记提示词之后、AstrBot 人设注入之前生效。适合为不同群聊定制不同的总结侧重（例如「重点记录大家讨论的技术细节」），不配置则不影响默认行为。

### v0.1.0（项目初始化）

- 项目骨架初始化：AGPL-3.0 合规声明、插件元数据（`metadata.yaml`）、开发规约（`AGENTS.md`）。
- 定制化功能内容：待定（初始化阶段）。

## ✨ 功能概览

本插件在继承上游 LivingMemory 全部能力的基础上，新增以下定制功能（上游完整功能说明见 [官方文档](https://lxfight-s-astrbot-plugins.github.io/astrbot_plugin_livingmemory/)）：

### 🗓️ 记忆日记

每天在自定义时间，拉取上游 LivingMemory 中当日（本地时间 00:00 至当前时刻）保存的记忆，由 LLM 总结成一篇日记，并发送到指定群聊。

- **多套规则**：可添加多条发送规则，每条规则独立配置，例如「群聊 A 每天 21:00 总结群 A 的记忆发到群 A」「群聊 B 每天 08:00 总结所有记忆发到群 B」。
- **总结范围**：所有记忆 / 单群聊 / 单好友对话（下拉选择对话对象）。
- **人设注入**：总结提示词会拼接当前 AstrBot 人设（persona）的系统提示词，让日记符合 bot 的人设语气；内置默认提示词可直接使用，也可在配置中自定义。
- **只读读取**：以只读模式打开上游记忆库，与上游插件安全共存；库文件缺失或读取异常时自动跳过并记录日志。请确保上游插件已成功初始化（已生成记忆库），首次使用前可先让上游运行一段时间写入记忆。

配置入口：`插件 -> LivingMemory Ext -> 配置 -> diary_digest`。修改配置后请在插件管理页**重载插件**生效。

## 📦 安装

按 [AstrBot 插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html)：

1. 本插件依赖上游 [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) 已安装并正常写入记忆（记忆日记读取其记忆库）。
2. 将本插件放入 `AstrBot/data/plugins/`（或从插件市场安装），重载 AstrBot。
3. 进入插件配置页：在 `diary_digest` 板块打开开关、确认提示词，并添加至少一条发送规则（总结范围 + 总结时间 HH:MM + 发送位置下拉）。

## 🛠️ 开发

开发规约、硬性要求与 AstrBot 插件规范见 [AGENTS.md](AGENTS.md)。

## 许可证

本项目基于 [AGPL-3.0](LICENSE) 发布，上游 LivingMemory 版权归 `lxfight-s-Astrbot-Plugins` 所有。
