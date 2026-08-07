# Changelog

## v0.1.1 (2026-08-07)

- 新增「记忆日记」功能：定时拉取上游 LivingMemory 当日记忆，经 LLM 总结为日记并发送到指定群聊。
- 支持多套发送规则（`diary_digest` 配置板块）：每条规则独立设置总结范围（所有 / 单群聊 / 单好友对话）、总结时间（HH:MM）与发送位置（群号）。
- 支持配置获取记忆的时间范围（`memory_range`）：每条规则可选 今日 / 昨日 / 近 7 天，默认今日。
- 日记总结自动注入当前 AstrBot 人设（`persona_manager`），提示词可自定义（内置默认提示词）。
- 上游记忆库以只读方式（`mode=ro`）读取，支持并发读取；库文件缺失或读取失败时安全降级跳过。
- 日志接入 AstrBot 日志体系：改用 `astrbot.plugin.*` 专属 logger，`[DiaryDigest]` 运行日志可直接在 WebUI「平台日志」页查看（此前裸 logger 日志仅写入服务器控制台，WebUI 不可见）。
- 消息平台适配器选项扩展：规则 `platform` 新增 `qqab` / `qqofficial`（原仅 `aiocqhttp`），解决 AstrBot `send_message` 按平台 id 匹配失败导致的日记消息静默丢弃问题。
- 新增插件 Pages「日记发送目标」页面：自动拉取当前所有平台的群列表，提供可搜索的下拉框，选择后一键写回规则配置（`platform` + `send_to`），避免手填出错导致消息静默丢弃。

## v0.1.0 (2026-08-07)

- 项目初始化：AGPL-3.0 合规声明（README + LICENSE）、插件元数据（metadata.yaml）、开发规约（AGENTS.md）。
- 定制化功能内容待定。
