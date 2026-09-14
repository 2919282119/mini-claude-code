# miniCC — 仿 Claude Code 的终端 Coding Agent

一个纯 Python 从零实现的 AI 编程助手（CLI），模仿 **Claude Code** 的核心工作方式：用户以自然语言下达编程任务，Agent 通过 **ReAct 循环**（Reason → Act → Observe）自主地读代码、改代码、跑命令、查资料，直到完成任务，并在写文件、执行命令等敏感操作前向用户请求授权。

- 纯 Python 实现，无 Web 框架，核心代码约 2000 行
- LLM 通过 OpenAI 兼容接口调用；内置**多模型映射**（`llm/model.py`），每个模型绑定各自的 API Key / BaseURL 环境变量与上下文窗口，`/model` 可在运行时切换
- 已打包为可安装 CLI（`pyproject.toml`）：`pip install -e .` 后，任意目录下执行 `miniCC` 即可启动
- 项目目录：`tools/`、`agent/`、`commands/`、`llm/`、`cli/` 分层解耦，各模块可独立替换

## 核心功能

| 能力 | 说明 |
| --- | --- |
| ReAct Agent 循环 | `agent_loop` 反复执行「组装上下文 → 调用 LLM → 若请求工具则执行并回填结果 → 再调用」，直到 LLM 给出最终答复；对话中每步都打印工具调用与参数，过程可观测；单轮任务最多循环 30 次（`MAX_LOOP_CNT`），超过即停止并提示，避免工具调用失控陷入无限循环 |
| 工具系统 | 8 个基础工具：`read_file` / `write_file` / `edit_file` / `grep` / `glob`（按通配符查找文件） / `bash` / `list_dir` / `search_web`（联网搜索），外加 `load_skill`，共 9 个；`bash` 支持 `background=true` 后台启动长期服务（如 dev server，stdin/out/err 全部隔离），前台命令 30s 超时后**杀整棵进程树**（防止孙进程持有管道导致永久卡死）；grep 自动跳过 `.git`/`node_modules` 等目录 |
| 工具注册表 | `ToolRegistry`：声明式定义工具（名称/描述/参数/权限级），自动生成 OpenAI function-calling 的 JSON Schema |
| 权限检查 | 按 `READ / WRITE / EXECUTE` 分级：读操作自动放行，写/执行操作交互式询问（y / n / a）；选「记住（a）」后以 *工具名* 为键，本进程内该工具后续调用不再询问（避免逐次确认过于频繁；允许与拒绝都会被记住，重启进程后清空） |
| 会话管理 | 每次对话的完整状态封装为 `AgentState`（session_id / messages / cwd / name / model），每轮回答后序列化为 JSON 存到 `~/.miniCC/sessions/`；新会话自动以首条输入前 50 字符命名，`/resume` 列表因此显示有意义的名称而非 None；支持 `resume` 跨进程恢复任意历史会话继续对话（连同模型选择一并恢复） |
| 上下文管理 | 从每次响应的 `usage.prompt_tokens` 直接读取真实 token 用量（非本地估算）；`/context` 查看上下文窗口占用（已用 / 剩余 / 百分比）；`/compact` 让 LLM 总结历史消息、保留最近 10 条，以 `[Conversation Summary]` 注入上下文；用量 ≥ 80% 时自动触发压缩 |
| 多模型映射 | `llm/model.py` 维护模型注册表（当前 kimi / deepseek），每条配置声明「模型名 + API Key 环境变量名 + BaseURL 环境变量名 + 上下文窗口」；默认 kimi，`/model <name>` 运行时切换（连同上下文窗口一并更新，随会话持久化）；新增模型 = 加一条配置 + `.env` 补对应变量 |
| 斜杠命令 | `/help` `/clear` `/rename` `/resume` `/context` `/compact` `/btw` `/memory` `/model` `/skills`，另有 `!` 前缀直通执行 Shell 命令 |
| 旁路问答 `/btw` | 用「系统提示 + 当前对话历史 + 新问题」临时组装请求问 LLM，结果直接展示而**不写入**对话历史，不污染主任务上下文 |
| 跨会话长期记忆 | `~/.miniCC/memory.json` 持久化，`/memory` 支持增删查清；每次请求动态拼进 system prompt，让 Agent 在后续会话中记得用户偏好与约定 |
| 项目指令文件 CC.md | 两级指令加载：全局 `~/.miniCC/CC.md` + 当前项目 `./CC.md`，每次请求动态读取追加到系统提示词（分别标注 `# Global Instructions` / `# Project Instructions`），用于固化跨项目的个人偏好与项目级约定（相当于 Claude Code 的 CLAUDE.md） |
| Skills 技能系统 | 以 Claude Code 的 `SKILL.md`（YAML frontmatter + Markdown）为规范，从全局目录 `~/.miniCC/skills/<name>/SKILL.md` 自动发现；采用**渐进式披露**——仅把「技能名 + 一句话描述」做成 `load_skill` 工具的 description 暴露给模型，由模型按需调用加载完整内容，避免上下文无谓膨胀；自带内置技能（如 `find-skills`），首次启动时自动复制到全局技能目录（已存在则不覆盖），`/skills` 可列出全部可用技能 |

## 系统设计

### 消息与调用流程

```
main.py (REPL)
   │  用户输入
   ▼
handle_command ── /命令 或 !命令 命中? ──yes──> 直接处理（不进入对话）
   │ no
   ▼
追加 user 消息到 state.messages
   ▼
agent_loop(state, registry, context_manager, memory_manager)        ◀── 注意这里
   │ 循环（上限 30 次）：                                                  传的是 messages 引用，
   │   组装请求 = system_prompt(+CC.md 指令 + 长期记忆) + 历史消息        每一次更新都会
   │   call_llm(model_config, messages, tools=registry.schemas())      写回 AgentState
   │   （model_config = MODELS[state.model]，随 /model 切换）
   │   context_manager.update(response)  → 用量≥80% 自动 compact
   │   ↓ message.tool_calls?
   │   是 → registry 查工具 → check_permission → 执行 → 工具结果以
   │        role="tool" 回填 messages，继续下一轮
   │   否 → 返回最终答复
   ▼
打印答复 → SessionManager.save(state) 持久化到 ~/.miniCC/sessions/
```

### 模块划分

| 模块 | 职责 | 关键设计 |
| --- | --- | --- |
| `tools/` | 工具层 | `Tool` 声明式定义 + `tool_registry` 注册表 + `permission` 权限检查；新工具 = 写一个函数 + 一个 `Tool(...)` 声明并注册，无需改动 agent 主循环 |
| `agent/` | 智能体层 | `agent.py` 主循环（含 30 次循环上限）；`session.py` AgentState 会话状态与持久化；`context.py` token 用量跟踪与上下文压缩；`memory.py` 跨会话长期记忆；`skill.py` SKILL.md 发现与内置技能安装；`system_prompt.py` 行为约束（先理解再修改 / 优先获取真实信息 / 控制工具调用等中文工作准则）+ CC.md（全局/项目级）加载 |
| `commands/` | 命令层 | 斜杠命令与 `!` Shell 直通，与正常对话分流 |
| `llm/` | LLM 客户端 | OpenAI 兼容 SDK 封装，`tools` 参数可选传递 |

### 关键设计决策

1. **system prompt 不入 `messages`，请求时动态拼接**——压缩（compact）只操作 `state.messages`，因此永远不会把 system prompt 一起压缩掉（修复过该 bug）。
2. **压缩策略 = LLM 总结 + 保留窗口**：旧消息交给 LLM 按固定要点（用户目标/已完成工作/文件路径与改动/错误与解法/未完成任务）提炼为摘要，与最近 10 条原始消息重组上下文，在信息不丢失与 token 控制之间折中。
3. **声明式工具 + 自动 Schema**：每把工具只需维护一份「描述 + JSON 参数约束 + 权限级」，function-calling 所需的 schema 由 `Tool.to_schema()` 统一生成。
4. **读代码库用 grep 而非 RAG**：不做向量库/索引，靠 `grep`/`read_file` 精确检索——小项目下零开销、结果可信，且避免检索噪声误导模型。
5. **Skill 渐进式披露 + 让模型自己决定加载**：技能目录（名称 + 一句话描述）随 `load_skill` 工具的描述静态发送，不进 system prompt、不随对话累积；完整 SKILL.md 正文只在模型调用 `load_skill` 后作为工具结果进入上下文，同一技能不会被反复注入。
6. **创建与修改分工，局部编辑带防误改保护**：`write_file` 负责创建文件/整体覆盖；修改已有文件走 `edit_file` 的 `old_text → new_text` 定点替换——匹配串出现多次时**拒绝执行**（防止误改多处），找不到时返回错误信息让模型自纠。系统提示词同时引导模型「修改已有文件优先用 `edit_file`，而非整文件重写」。（注：Claude Code 式 patch editing——一次提交多处替换——尚未实现，见「后续规划」）
7. **`state.messages` 引用保持稳定（clear + extend）**：该列表被 REPL、agent 主循环、命令层共享持有，一旦重绑定（`state.messages = [...]`），其它持有者仍在操作旧列表，出现「用户输入加不进去」等分叉 bug——`/resume` 恢复会话与 compact 压缩上下文因此统一改为 `clear() + extend()` 原地更新，并由 `tests/test_resume.py` 回归测试锁定该行为。

### 目录结构

```
miniCC/
├── main.py                  # 应用入口：REPL、组件装配（注册表/会话/记忆/上下文）
├── pyproject.toml           # 打包配置（entry point: miniCC = main:main）
├── agent/
│   ├── agent.py             # ReAct 主循环（MAX_LOOP_CNT=30）
│   ├── session.py           # AgentState + SessionManager（~/.miniCC/sessions/*.json）
│   ├── context.py           # ContextManager：token 统计 / get_usage / compact / auto_compact(≥80%)
│   ├── memory.py            # MemoryManager：跨会话长期记忆（~/.miniCC/memory.json）
│   ├── skill.py             # SkillManager：技能发现 + 内置技能安装到全局
│   └── system_prompt.py     # Agent 行为准则 + CC.md（全局/项目级）加载
├── commands/handle_command.py   # 斜杠命令 + ! Shell 直通 + /model 切换 + /btw 旁路问答
├── llm/
│   ├── model.py             # 模型映射表（模型名 / API Key 与 BaseURL 的 env 变量名 / 上下文窗口）
│   └── call_llm.py          # OpenAI 兼容调用（按 ModelConfig 读取对应环境变量）
├── cli/banner.py            # 启动 Banner（Logo / 当前模型 / 工作目录）
├── skills/                  # 内置技能（首次启动自动复制到 ~/.miniCC/skills/）
│   └── find-skills/SKILL.md
├── tools/
│   ├── Tool.py              # 声明式工具基类（自动生成 schema）
│   ├── tool_registry.py     # 注册表
│   ├── permission.py        # READ/WRITE/EXECUTE 分级 + 记住授权
│   ├── setup.py             # 工具装配
│   ├── load_skill.py        # skill 加载工具（描述中内嵌技能目录）
│   └── my_tools/            # basic: bash/grep/glob/ls/read/write/edit   usual: search_web
└── tests/
    ├── test_permission.py   # unittest：权限放行/询问/拒绝（mock 用户输入）
    ├── test_resume.py       # 回归：/resume 与 compact 的 messages 引用稳定性
    └── test_bash_timeout.py # 回归：前台超时杀进程树、后台 stdin 隔离
```

## 快速开始

```bash
pip install openai python-dotenv tavily-python pyyaml
# 复制 .env.example 为 .env，填入所用模型的 Key/BaseURL（KIMI_API_KEY / KIMI_BASE_URL 或 DEEPSEEK_*）与 TAVILY_API_KEY

# 方式一：项目内直接运行
python main.py

# 方式二：安装为全局命令，任意目录下启动
pip install -e .
miniCC
```

- 存储位置：会话 `~/.miniCC/sessions/`，长期记忆 `~/.miniCC/memory.json`，技能 `~/.miniCC/skills/<name>/SKILL.md`（frontmatter 写 `description`，正文写操作规范；手动放入的技能用 `/skills` 刷新即可发现，无需重启）。仓库自带的内置技能（如 `find-skills`）在首次启动时自动复制到该目录，已存在则不覆盖
- 项目指令：全局 `~/.miniCC/CC.md` 与项目根目录 `CC.md` 会被自动追加到系统提示词（全局在前、项目在后），每次请求实时读取，写完即生效
- 模型切换：默认 `kimi`；`/model` 查看当前模型与可选列表，`/model deepseek` 切换（需在 `.env` 配好该模型的 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`）；在 `llm/model.py` 的 `MODELS` 中加一条配置即可接入新模型
- 常用命令示例：`/resume`（列出历史会话并选择继续）、`/context`（查看上下文占用）、`/compact`（手动压缩上下文）、`/skills`（列出可用技能）、`/memory 用户偏好...`（记住约定）、`! pytest tests/`（直通跑命令）

## 技术栈

Python 3.10+（dataclass / typing）、OpenAI Python SDK（function calling）、Tavily Search API、PyYAML、unittest；setuptools 打包（`pyproject.toml` → `miniCC` 命令）；配置全部经 `.env` 注入，不硬编码密钥。

## 后续规划

- **patch editing**：参照 Claude Code，把 `edit_file` 从「单次定点替换」扩展为「一次提交多处替换」（行号 + 上下文定位），并引入编辑预览/失败回退等防护
- **长期记忆按用户/会话隔离**：当前 `memory.json` 为单机全局文件，未区分用户维度
