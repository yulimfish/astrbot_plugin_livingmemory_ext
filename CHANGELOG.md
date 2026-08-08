# Changelog

## v0.1.1 (2026-08-07)

- 新增「记忆日记」功能：定时拉取上游 LivingMemory 当日记忆，经 LLM 总结为日记并发送到指定群聊。
- 支持多套发送规则（`diary_digest` 配置板块）：每条规则独立设置总结范围（所有 / 单群聊 / 单好友对话）、总结时间（HH:MM）与发送位置（群号）。
- 支持配置获取记忆的时间范围（`memory_range`）：每条规则可选 今日 / 昨日 / 近 7 天，默认今日。
- 日记总结自动注入当前 AstrBot 人设（`persona_manager`），提示词可自定义（内置默认提示词）。
- 上游记忆库以只读方式（`mode=ro`）读取，支持并发读取；库文件缺失或读取失败时安全降级跳过。
- 日志接入 AstrBot 日志体系：改用 `astrbot.plugin.*` 专属 logger，`[DiaryDigest]` 运行日志可直接在 WebUI「平台日志」页查看（此前裸 logger 日志仅写入服务器控制台，WebUI 不可见）。
- 消息平台适配器选项扩展：规则 `platform` 新增 `qqab` / `qqofficial`（原仅 `aiocqhttp`），解决 AstrBot `send_message` 按平台 id 匹配失败导致的日记消息静默丢弃问题。
- 发送位置改为动态下拉选择：`send_to` 与 `platform` 合并为「发送位置」一项，下拉选项由插件自动从当前平台拉取全部群聊（显示群名、支持输入搜索过滤），无需手填平台与群号，避免填错导致消息静默丢弃；旧配置（纯群号 / 完整消息源格式）自动兼容。
- 「范围目标」同步改为动态下拉选择：`scope_target` 与发送位置同一套机制，选项自动拉取当前平台的全部群聊与好友（带「群 / 好友」标识），支持输入搜索过滤；纯群号旧配置自动兼容（平台继承自发送位置）。
- 修复群组 / 好友日记总结 0 条：好友类型键改为 AstrBot 标准 `FriendMessage`（原 `PrivateMessage` 恒失败）；会话 LIKE 不再锁死平台段；上游按全局范围（`livingmemory:global`）写库时按 `metadata.source_session_id` 兜底归类到对应群/好友。新增只读诊断脚本 `scripts/diagnose_memories.py`。
- 日记规则新增「补充提示词」字段（`extra_prompt`，可选）：针对单条规则的额外总结要求，会拼接在插件级日记提示词之后、AstrBot 人设注入之前生效，便于为不同群聊定制不同的总结侧重。

## v0.1.0 (2026-08-07)

- 项目初始化：AGPL-3.0 合规声明（README + LICENSE）、插件元数据（metadata.yaml）、开发规约（AGENTS.md）。
- 定制化功能内容待定。
