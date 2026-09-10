# 可分发 Skills

## maintaining-project-context

这是由 `ai提示词/维护协议.md` 转换得到的跨平台 Agent Skill。它只使用通用的 `SKILL.md`、相对路径和 Markdown 资源，不依赖 Codex 或 Claude 的专有字段。

### 安装

复制整个 `maintaining-project-context/` 文件夹，而不是只复制 `SKILL.md`：

- Codex：`~/.agents/skills/maintaining-project-context/`
- Claude Code：`~/.claude/skills/maintaining-project-context/`

若当前客户端没有立即发现新技能，重启对应客户端。

### 调用

- Codex：在提示中使用 `$maintaining-project-context`。
- Claude Code：使用 `/maintaining-project-context`，或让 Claude 根据任务描述自动触发。

技能会在长任务、多阶段任务、上下文压缩、跨会话恢复或任务交接场景中维护项目根目录下的 `PROJECT_CONTEXT.md`。短小、一次性任务不应自动触发。
