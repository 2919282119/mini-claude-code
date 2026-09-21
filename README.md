# miniCC — 仿 Claude Code 的终端 Coding Agent

一个纯 Python 从零实现的 AI 编程助手（CLI），模仿 **Claude Code** 的核心工作方式：用户以自然语言下达编程任务，Agent 通过 **ReAct 循环**（Reason → Act → Observe）自主地读代码、改代码、跑命令、查资料，直到完成任务，并在写文件、执行命令等敏感操作前向用户请求授权。

- 纯 Python 实现，无 Web 框架，核心代码约 2900 行（57 个源文件，不含测试）
- LLM 通过 OpenAI 兼容接口调用；内置**多模型映射**（`llm/model.py`），每个模型绑定各自的 API Key / BaseURL 环境变量与上下文窗口，`/model` 可在运行时切换
- 已打包为可安装 CLI（`pyproject.toml`）：`pip install -e .` 后，任意目录下执行 `miniCC` 即可启动
- 项目目录：`tools/`、`agent/`、`commands/`、`llm/`、`rag/`、`cli/` 分层解耦，各模块可独立替换

## 核心功能

| 能力 | 说明 |
| --- | --- |
| ReAct Agent 循环 | `agent_loop` 反复执行「组装上下文 → 调用 LLM → 若请求工具则执行并回填结果 → 再调用」，直到 LLM 给出最终答复；对话中每步都打印工具调用与参数，过程可观测；单轮任务最多循环 30 次（`MAX_LOOP_CNT`），超过即停止并提示，避免工具调用失控陷入无限循环；工具参数错误或执行异常**不会中断进程**，错误信息作为工具结果回填，由 LLM 自行纠正重试 |
| 工具系统 | 8 个基础工具：`read_file` / `write_file` / `edit_file` / `grep` / `glob`（按通配符查找文件） / `bash` / `list_dir` / `search_web`（联网搜索），外加 `load_skill` / `run_subagent`（子 Agent） / `rag_search`（知识库检索，按库名选库），共 11 个；`bash` 支持 `background=true` 后台启动长期服务（如 dev server，stdin/out/err 全部隔离），前台命令 30s 超时后**杀整棵进程树**（防止孙进程持有管道导致永久卡死）；grep 自动跳过 `.git`/`node_modules` 等目录 |
| 工具注册表 | `ToolRegistry`：声明式定义工具（名称/描述/参数/权限级），自动生成 OpenAI function-calling 的 JSON Schema |
| 子 Agent 并行 | `run_subagent` 一次接收 `tasks` 列表（每项是一段**自包含**的任务描述），用 `ThreadPoolExecutor` **并行**执行，上限 `MAX_SUBAGENT_COUNT = 4`、多余任务排队，全部结束后把 `{"results": [{"task", "result"}]}` 回填给主 Agent。每个子任务各自新建 `AgentState` + `ContextManager`——**看不到主对话**、不写父会话消息、不落盘、不碰长期记忆（`memory_manager=None`）。禁止嵌套由代码保证：`create_subagent_registry` 按名字把 `run_subagent` 从子注册表里**剔除**，提示词里的约束只是辅助说明。权限**在派生时确认一次**：工具为 `EXECUTE` 级、用户看到完整任务列表后确认，子 Agent 内部以 `permission_mode="auto"` 跳过逐次询问（`check_permission` 是阻塞式 `input()`，多线程并行会抢 stdin）。子 Agent **静默执行**（`verbose=False`，不打印工具调用），结束后统一打印启动/完成行与每个任务的结果摘要；单个子任务异常只影响自己（错误写进该任务的 `error` 字段） |
| MCP 工具接入 | 基于**官方 mcp SDK**（同步接口封装 async SDK：后台线程 + asyncio 事件循环桥接）。支持两种传输：**Streamable HTTP**（远程 URL）与 **stdio**（本地子进程，如 `uvx`）。配置在 `~/.miniCC/mcp.json`，用斜杠命令管理：`/mcp`（列表）、`/mcp add <name> <url>`、`/mcp add <name> -- <命令>`、`/mcp remove <name>`——由程序确定性合并配置，不会覆盖丢失已有条目。启动时完成握手与 `tools/list`，把远端工具包装成普通 `Tool` 注册进同一注册表——对 agent 完全透明。工具名带 `服务器__工具` 前缀防冲突，权限默认 `EXECUTE`（首次调用需确认），调用失败/超时返回错误不阻塞；单服务器连接失败只警告跳过；stdio 子进程退出时统一清理 |
| 权限检查 | 按 `READ / WRITE / EXECUTE` 分级：读操作自动放行，写/执行操作交互式询问（y / n / a，输入做全角归一化，中文输入法打出的 `ｙ` / `ｎ` / `ａ` 同样有效）；选「记住并允许（a）」后以 *工具名* 为键，本进程内该工具后续调用不再询问（避免逐次确认过于频繁；只记住显式选择的「记住并允许」，回车或 `n` 的拒绝只作用于本次，重启进程后清空） |
| 会话管理 | 每次对话的完整状态封装为 `AgentState`（session_id / messages / cwd / name / model），每轮回答后序列化为 JSON 存到 `~/.miniCC/sessions/`；新会话自动以首条输入前 50 字符命名，`/resume` 列表因此显示有意义的名称而非 None；支持 `resume` 跨进程恢复任意历史会话继续对话（连同模型选择一并恢复） |
| 上下文管理 | 从每次响应的 `usage.prompt_tokens` 直接读取真实 token 用量（非本地估算）；`/context` 查看上下文窗口占用（已用 / 剩余 / 百分比）；`/compact` 让 LLM 总结历史消息、保留最近 10 条，以 `[Conversation Summary]` 注入上下文；用量 ≥ 80% 时自动触发压缩 |
| 多模型映射 | `llm/model.py` 维护模型注册表（当前 kimi / deepseek），每条配置声明「模型名 + API Key 环境变量名 + BaseURL 环境变量名 + 上下文窗口」；默认 deepseek，`/model <name>` 运行时切换（连同上下文窗口一并更新，随会话持久化）；新增模型 = 加一条配置 + `.env` 补对应变量 |
| 斜杠命令 | `/help` `/clear` `/rename` `/resume` `/context` `/compact` `/btw` `/memory` `/model` `/skills` `/mcp`，另有 `!` 前缀直通执行 Shell 命令 |
| 旁路问答 `/btw` | 用「系统提示 + 当前对话历史 + 新问题」临时组装请求问 LLM，结果直接展示而**不写入**对话历史，不污染主任务上下文 |
| 跨会话长期记忆 | `~/.miniCC/memory.json` 持久化，`/memory` 支持增删查清；每次请求动态拼进 system prompt，让 Agent 在后续会话中记得用户偏好与约定 |
| 项目指令文件 CC.md | 两级指令加载：全局 `~/.miniCC/CC.md` + 当前项目 `./CC.md`，每次请求动态读取追加到系统提示词（分别标注 `# Global Instructions` / `# Project Instructions`），用于固化跨项目的个人偏好与项目级约定（相当于 Claude Code 的 CLAUDE.md） |
| Skills 技能系统 | 以 Claude Code 的 `SKILL.md`（YAML frontmatter + Markdown）为规范，从全局目录 `~/.miniCC/skills/<name>/SKILL.md` 自动发现；采用**渐进式披露**——仅把「技能名 + 一句话描述」做成 `load_skill` 工具的 description 暴露给模型，由模型按需调用加载完整内容，避免上下文无谓膨胀；自带内置技能（如 `find-skills`），首次启动时自动复制到全局技能目录（已存在则不覆盖），`/skills` 可列出全部可用技能 |
| RAG 知识库检索（可选） | `rag_search(kb, query)` 对本地 PDF 知识库做**混合召回 + cross-encoder 精排**——**一个 PDF 一个库**，库清单写在 `static/rag_files/knowledge_bases.json`（库名 → PDF 文件名 + 一句话描述，描述手写）。库列表在装配时拼进 `rag_search` 的 description（同 `load_skill` 的做法），模型一开始就知道有哪些库可选、不必多一次往返去发现；库名匹配做了 NFKC + 大小写归一化（中文输入法的全角字符也能对上），对不上则返回「知识库不存在 + 可用列表」让模型自纠。检索分两段：**先召回、再精排**。召回是混合检索——稠密路（FAISS + bge 向量，`k=20`）与稀疏路（BM25，`k=20`，jieba 分词）交给 `EnsembleRetriever` 做 RRF 融合，返回按 `page_content` 去重的并集（≤40 条）；精排把这不超过 40 条候选交给 cross-encoder `BAAI/bge-reranker-v2-m3` 逐对打分，**取分数最高的 8 条**给模型。**截断放在精排之后**，所以给模型的上下文量与加 rerank 之前一样是 8 条——效果若变能归因到重排本身，而不是"同时多给了资料"（两个变量一起动就无法判断）。rerank 补的正是 RRF 的短板：**只看排名、不看分数**，某一路塞进来的低质量结果一样会被等权计入；cross-encoder 直接对 `(query, 正文)` 整体打分，能把这类结果压下去。条数写死而不让模型选：它看不到相似度分数、也不知道上一批够不够，猜出来的数字不如钉死的常量；嫌少时让它换个 query 再检索一次（由"返回了什么"驱动，比猜有依据）。两路权重相等，因为**没有评测集时调权重就是猜**；reranker 同理用 fp16 权重（实测 36 条候选 1.0 秒，fp32 要 3.7 秒），不显式设 `max_length`（默认取模型自己的 8192，远超 chunk 长度）。BM25 的语料直接取自 FAISS 已存的 docstore（`index.pkl` 里就带着 chunk 正文），不额外落一份稀疏索引，因而不会有两份索引不同步的问题。**为什么必须用 jieba**：`BM25Retriever` 默认按空格切词，对中文等于失效（整句变成一个 token），BM25 就只剩"整句精确匹配"一条路；jieba 还能把 `PagedAttention` 这类英文术语原样保留成一个 token，而那正是加 BM25 想捞回来的那类查询。**全链路懒加载**：langchain、embedding 模型、reranker、FAISS 索引、jieba 都在首次调用时才加载，且**缓存命中时完全不联网**（见模块表 `embeddings.py`：网络不通时实测加载照常，输出里没有任何 HEAD 重试）（reranker 是本项目最重的一次加载——模型 2.14 GB，首次检索才下载，实测 140 秒；设备显式选 `cuda`、不可用时回退 CPU，并把实际设备打印出来，不用靠猜。首次构造检索器实测合计 ~40 秒，其中 `langchain_classic` 导入约 10 秒、reranker 载入约 10 秒，其余是 embedding 与 FAISS；同进程内换第二个库约 12 秒）（首次构造混合检索器实测另有 ~10 秒，且**几乎全部来自 `langchain_classic.retrievers` 这个重模块的导入**——不是 jieba 分词、也不是 BM25 建索引：jieba 词典只占 0.3 秒，对 757 个 chunk 分词同样是亚秒级。`EnsembleRetriever` 只在 `langchain_classic` 里有，`langchain_community.retrievers` 并不导出它，所以这 10 秒省不掉；之后走进程内缓存），且这些 import 都在函数内部——因此即使 RAG 依赖没装（`pip install -e ".[rag]"`，可选）或某个库的索引没建，miniCC 也照常启动，工具返回一句提示文本交给 LLM，而不是抛异常打断主循环。**按库懒建**：某个库首次被检索且索引不存在时才构建（实测 303 页的书 757 chunks 约 2 分钟、519 页的书 1095 chunks 约 3 分钟，耗时随篇幅增长），不会启动时把全部 PDF 建一遍；判断依据是 `index.faiss` 是否存在而非目录是否存在（构建中途失败留下的空目录不会造成「已建好」的假象）。索引在 `rag/rag_index/<库名>/`，是纯本机产物，已在 `.gitignore` 排除 |

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
| `tools/` | 工具层 | `Tool` 声明式定义 + `tool_registry` 注册表 + `permission` 权限检查；`local/`（本地实现，其中 `usual/run_subagent.py` 是子 Agent 工具，以工厂闭包持有注册表与 model/cwd）与 `mcp/`（MCP 接入，含远程 HTTP 与本地 stdio 两种传输）最终都包装成 `Tool` 注册进同一注册表——新增工具 = 一个 `Tool(...)` 声明，无需改动 agent 主循环 |
| `agent/` | 智能体层 | `agent.py` 主循环（含 30 次循环上限，`verbose` / `permission_mode` 两个开关供子 Agent 复用同一套循环）；`session.py` AgentState 会话状态与持久化；`context.py` token 用量跟踪与上下文压缩；`memory.py` 跨会话长期记忆；`skill.py` SKILL.md 发现与内置技能安装；`system_prompt.py` 行为约束（先理解再修改 / 优先获取真实信息 / 控制工具调用 / 子 Agent 委派准则等中文工作准则）+ CC.md（全局/项目级）加载 |
| `commands/` | 命令层 | `handle_command.py` 只做分流：`!` 走 Shell 直通、`/` 走斜杠命令、其余返回 `False` 交回对话循环；`slash/` 下**一个斜杠命令一个模块**，都暴露同一签名 `run(parts, state, session_manager, context_manager, memory_manager)`，`slash/__init__.py` 保留 if-chain 分发（新增命令 = 新建文件 + 加一个 `if`，不必改其它命令） |
| `llm/` | LLM 客户端 | OpenAI 兼容 SDK 封装，`tools` 参数可选传递 |
| `rag/` | 检索层（可选） | `knowledge_base.py`：读 `static/rag_files/knowledge_bases.json` 库清单（读坏/缺失时安全返回空字典，**绝不抛异常**——它在启动时被导入）、按库名解析 PDF 与索引路径、库名 NFKC + 大小写归一化、生成给 LLM 看的库列表；`build_index.py`：`build_index(kb)` 把一个库的 PDF 切分向量化存到 `rag/rag_index/<库名>/` 并返回向量库（可 `python -m rag.build_index` 建全部库）；`embeddings.py`：`get_embeddings()` 进程内共享的 embedding 单例——所有库用的是同一个模型、推理又是无状态纯函数，共用一份常驻内存才不会随库数线性增长（`build_index` 与 `retriever` 都用它，单开一个模块是为了避免两者互相依赖）；加载统一走 `load_local_first()`：**先只认本地缓存，本地没有（首次使用）才回退联网下载**。`huggingface_hub` 默认会为每个文件发 HEAD 去查远端有没有更新，网络不通时每个文件要重试 5 次退避（1+2+4+8+8 秒），模型明明就躺在本地缓存里却要白等——embedding 与 reranker 都走这条路径，判定依据是本地找不到时抛的 `OSError`（实测 0.0 秒、不发请求）；`retriever.py`：`get_retriever(kb)` 按库名缓存、索引缺失时补建，返回「稠密 + BM25 混合召回（`EnsembleRetriever` RRF 融合，`CANDIDATE_K=20`/路）→ cross-encoder 精排（`_RerankRetriever`，取 `TOP_K=8`）」的两段式检索器。**embedding 与 reranker 都是进程内单例**，两者被并发调用的安全性已实测（子 Agent 是 `ThreadPoolExecutor` 并行的，上限 4）：8 线程并发 `encode`、4 线程并发跑 36 对批次打分，均无异常且与串行结果分差 0.00e+00。重型依赖（langchain / faiss / torch / sentence-transformers / jieba）全部在函数内 import，模块可被安全导入 |

### 关键设计决策

1. **system prompt 不入 `messages`，请求时动态拼接**——压缩（compact）只操作 `state.messages`，因此永远不会把 system prompt 一起压缩掉（修复过该 bug）。
2. **压缩策略 = LLM 总结 + 保留窗口**：旧消息交给 LLM 按固定要点（用户目标/已完成工作/文件路径与改动/错误与解法/未完成任务）提炼为摘要，与最近 10 条原始消息重组上下文，在信息不丢失与 token 控制之间折中。
3. **声明式工具 + 自动 Schema**：每把工具只需维护一份「描述 + JSON 参数约束 + 权限级」，function-calling 所需的 schema 由 `Tool.to_schema()` 统一生成。
4. **读代码库用 grep，只有文档知识库才用 RAG**：代码检索不做向量索引，靠 `grep`/`read_file` 精确检索——小项目下零开销、结果可信，且避免检索噪声误导模型；`rag_search` 只服务于「这份文档语料里怎么讲的」这类语义问题，语料是本地 PDF（不是代码库），与代码检索互不干扰。**工具的 description 刻意保持与领域无关**（只讲「检索 PDF 文档、不是源码、按描述挑库」），具体主题由 manifest 里每个库自己的描述承担 —— 否则加一本别的领域的书就得改代码。
5. **Skill 渐进式披露 + 让模型自己决定加载**：技能目录（名称 + 一句话描述）随 `load_skill` 工具的描述静态发送，不进 system prompt、不随对话累积；完整 SKILL.md 正文只在模型调用 `load_skill` 后作为工具结果进入上下文，同一技能不会被反复注入。
6. **创建与修改分工，局部编辑带防误改保护**：`write_file` 负责创建文件/整体覆盖；修改已有文件走 `edit_file` 的 `old_text → new_text` 定点替换——匹配串出现多次时**拒绝执行**（防止误改多处），找不到时返回错误信息让模型自纠。系统提示词同时引导模型「修改已有文件优先用 `edit_file`，而非整文件重写」。（注：Claude Code 式 patch editing——一次提交多处替换——尚未实现，见「后续规划」）
7. **`state.messages` 引用保持稳定（clear + extend）**：该列表被 REPL、agent 主循环、命令层共享持有，一旦重绑定（`state.messages = [...]`），其它持有者仍在操作旧列表，出现「用户输入加不进去」等分叉 bug——`/resume` 恢复会话与 compact 压缩上下文因此统一改为 `clear() + extend()` 原地更新，并由 `tests/test_resume.py` 回归测试锁定该行为。
8. **知识库清单写进 `rag_search` 的 description，而不是单开一个「列出知识库」的工具**：库名是 `kb` 参数的合法取值，本就属于工具契约的一部分——写进 description 后模型开局就知道有哪些库可选，省掉一次「先发现再调用」的往返；更重要的是避免了模型**不去查列表、直接瞎猜库名**导致的参数错误重试（那比多一跳更贵）。这与 `load_skill` 把技能列表拼进 description 是同一套做法，风格一致。代价是库很多时 description 会膨胀，且新增库需重启才被模型看到；当前是个位数知识库，代价可忽略。
9. **子 Agent = 复用同一套 `agent_loop` + 两个开关，隔离靠「新建对象」而非「共享状态」**：子 Agent 不另写一套循环，而是在 `run_one_subagent` 里复用 `agent_loop` 并传 `verbose=False`（静默）、`permission_mode="auto"`（跳过逐次询问）、子 Agent 专用提示词、`memory_manager=None`（不碰长期记忆）；隔离性来自每个子任务各自新建 `AgentState` 与 `ContextManager`，父会话的 `messages` 不被写入。**禁止嵌套**以代码为准：`create_subagent_registry` 按名字过滤掉 `run_subagent` 构造子注册表。注册表在装配时把 `model` / `cwd` 注入工具闭包（`tools_setup(model, cwd)`，注意传的是 `MODELS` 的 key 而不是 `ModelConfig.name`），所以会话中途 `/model` 切换不会改变本次启动创建的子 Agent 工具。并发上限取 4：`call_llm` 每次新建 client、本身线程安全，真正瓶颈在**账号侧的并发额度**（实测 kimi 侧并发为 1，任务多时会返回 429，错误只落在该子任务上）。

10. **混合检索 = 稠密 + BM25，RRF 融合后交给 cross-encoder 精排**：两路各取 `CANDIDATE_K=20`，`EnsembleRetriever` 返回的是按 `page_content` 去重的并集（最多 40 条），再由 `_RerankRetriever` 精排后取 `TOP_K=8`（详见 12）。**截断放在最后一步**，是为了让**给模型的上下文量保持不变**——仍是 8 条、与加 rerank 之前一样，这样效果变化才能归因于重排本身，而不是"同时多给了资料"（两个变量一起动就无法判断）。权重取相等（0.5/0.5），因为**没有评测集时调权重就是猜**。要承认 RRF 的固有局限：**只看排名、不看分数**，某一路给出的低质量结果一样会被等权计入。BM25 的语料直接取自 FAISS 已存的 docstore，不额外落一份稀疏索引——避免两份索引不同步；代价是依赖 langchain 的私有属性 `docstore._dict`，由 `tests/test_rag.py::TestDocstoreIsReusable` 用一次真实的 `save_local`/`load_local` 往返钉住，上游若改结构会**明确失败**，而不是静默让 BM25 拿到空列表（那种退化不报错，属于最难发现的一类）。**注意本次没有验证检索质量变好**：验证到的是「链路正确、恰好 8 条、无重复、两路都真的跑了」；要判断质量必须建评测集，而目前没有。

11. **嵌入跑在 GPU 上、FAISS 留在 CPU 上——这是一次刻意分工，不是配置遗漏**：`HuggingFaceEmbeddings` 不传 `device`，底层 `SentenceTransformer(device=None)` 的语义是**自动探测**（有 CUDA 就用，否则回退 CPU），所以 `build_index` / `retriever` 里的嵌入**不需要显式开 GPU**，代码里也完全看不出这一点（实测 757 个 chunk：GPU **1.4 秒** vs CPU **15.2 秒**，约 11 倍；这要求 torch 是 CUDA 版，CPU 版 torch 下自动探测会走 CPU）。而 FAISS 侧刻意留在 CPU：装的是 `faiss-cpu`，实测 757 个向量建索引 **< 1 毫秒**、单次检索 **0.033 毫秒**——这个量级上 GPU 化的收益远小于 CUDA 上下文初始化与数据传输开销，何况 Windows 上并没有 `faiss-gpu` 的 pip 包（`pip index versions faiss-gpu` 直接找不到）。代价是**设备选择完全是隐式的**：CUDA 不可用时静默回退 CPU，代码和输出都不反映。另外，建索引与查询用不同设备**不影响检索结果**——实测同一文本 CPU/GPU 向量最大差 1e-7 量级，三条查询的检索结果顺序完全一致。

12. **精排用 cross-encoder，把截断挪到精排之后、候选池放大到 40**：RRF 是**只看排名不看分数**的融合，某一路塞进来的低质量结果会被等权计入；cross-encoder（`BAAI/bge-reranker-v2-m3`）把 `(query, 正文)` 拼成一对送进同一个 Transformer 打分，能看到两者的交互——这正是双塔 embedding 和 BM25 都缺的那部分信息。三个取值都值得说明：**候选池改成 20/路（去重后 ≤40）**——原来是两路各 8、融合后直接截断到 8，rerank 只能在 RRF 已经选出的 16 条里重排，捞不回排在更后面的段落，所以同时把召回放大、把截断后移；**最终仍只给 8 条**——上下文量与加 rerank 之前一致，变量才可控；**用 fp16**——最初定的是 fp32，理由是「半精度省下的那点延迟感知不到」，那是我没实测的猜测，实测把它推翻了：**36 条候选 fp32 要 3.7 秒、fp16 只要 1.0 秒**（快 3.7×），显存也从权重 2166 MB / 峰值 3009 MB 降到 **1083 MB / 1512 MB**。选 fp16 而不是 bf16 同样是实测的结果：bf16 尾数位比 fp16 少（8 vs 10），对接近平局的分数扰动更大——同一次检索里 bf16 换掉了 fp32 前 8 中的 1 条，fp16 则与 fp32 前 8 完全同序（单条最大分差 1.4e-03 vs 6.6e-03）。**但这只是 1 个查询的证据**，不足以说 fp16 在质量上等于 fp32：没有评测集，两者孰优根本判不了，能说的只有「fp16 便宜 2.7 秒、显存减半，且在这一个样本上没有改变排序」。**不显式传 `max_length`**——`None` 在 sentence-transformers 6.x 里会保留 tokenizer 自己的 `model_max_length`，此模型实测就是 **8192**，而我一度打算显式传的 1024 反而会**更激进地截断** chunk。设备**显式**选 `cuda`、不可用时回退 CPU 并把实际设备打印出来——补上 11 里 embedding 那处「设备选择完全隐式、代码和输出都不反映」的代价。reranker 与知识库无关，做成进程内单例，不按库缓存。**仍然没有验证检索质量**：加 rerank 之前没建评测集，之后也没有；能验证的只有「链路接对、rerank 确实跑了、`predict` 收到的是 `(query, 正文)` 对、最终仍是 8 条、跨库复用同一个模型实例」，**不能**声称 rerank 让结果更好。另外这次是「每路 8→20」与「加 rerank」两个变量同时动，即便将来测出效果也无法归因到 rerank 一项。

### 目录结构

```
miniCC/
├── main.py                  # 应用入口：REPL、组件装配（注册表/会话/记忆/上下文）
├── pyproject.toml           # 打包配置（entry point: miniCC = main:main）
├── agent/
│   ├── agent.py             # ReAct 主循环（MAX_LOOP_CNT=30；verbose / permission_mode 供子 Agent）
│   ├── session.py           # AgentState + SessionManager（~/.miniCC/sessions/*.json）
│   ├── context.py           # ContextManager：token 统计 / get_usage / compact / auto_compact(≥80%)
│   ├── memory.py            # MemoryManager：跨会话长期记忆（~/.miniCC/memory.json）
│   ├── skill.py             # SkillManager：技能发现 + 内置技能安装到全局
│   └── system_prompt.py     # Agent 行为准则 + CC.md（全局/项目级）加载
├── commands/
│   ├── handle_command.py    # 分流：! → Shell 直通，/ → 斜杠命令，其余返回 False 走对话
│   ├── shell_command.py     # ! 前缀的 Shell 直通
│   └── slash/               # 斜杠命令：一个命令一个模块，统一 run(parts, state, session_manager, context_manager, memory_manager)
│       ├── __init__.py      #   if-chain 分发，入口 handle_slash_command
│       ├── help.py / clear.py / rename.py / resume.py / compact.py / btw.py
│       ├── memory.py / model.py / context.py / skills.py
│       └── mcp.py           #   /mcp 增删查（确定性合并，不丢已有配置）
├── llm/
│   ├── model.py             # 模型映射表（模型名 / API Key 与 BaseURL 的 env 变量名 / 上下文窗口）
│   └── call_llm.py          # OpenAI 兼容调用（按 ModelConfig 读取对应环境变量）
├── cli/banner.py            # 启动 Banner（Logo / 当前模型 / 工作目录）
├── rag/                     # 知识库检索（可选依赖，见 pyproject 的 [rag] extra）
│   ├── knowledge_base.py    #   库清单读取 + 路径解析 + 库名归一化 + 生成库列表
│   ├── embeddings.py        #   get_embeddings()：进程内共享的 embedding 单例（所有库共用一份）
│   ├── build_index.py       #   build_index(kb)：PDF → 切分 → embedding → FAISS（可 python -m 建全部）
│   └── retriever.py         #   get_retriever(kb)：按库缓存的懒加载；稠密+BM25 混合召回（≤40）→ cross-encoder 精排 → 8 条
├── static/
│   ├── rag_files/           # knowledge_bases.json（库清单，入库）+ 原始 PDF（已 gitignore）
│   └── skills/              # 内置技能（首次启动自动复制到 ~/.miniCC/skills/）
│       └── find-skills/SKILL.md
├── tools/
│   ├── Tool.py              # 声明式工具基类（自动生成 schema）
│   ├── tool_registry.py     # 注册表
│   ├── permission.py        # READ/WRITE/EXECUTE 分级 + 记住授权
│   ├── setup.py             # 工具装配（本地 + MCP + 子 Agent；入参 model/cwd 供子 Agent 继承）
│   ├── local/               # 本地工具实现
│   │   ├── builtin/         #   bash / grep / glob / ls / read / write / edit
│   │   └── usual/           #   search_web / load_skill / run_subagent（子 Agent） / search_rag（知识库）
│   └── mcp/                 # MCP 接入（基于官方 mcp SDK）
│       ├── config.py        #   ~/.miniCC/mcp.json 读写
│       ├── client.py        #   SDK 封装（后台线程 + asyncio 事件循环桥接）
│       └── manager.py       #   按配置创建客户端、包装成 Tool、退出清理
└── tests/
    ├── test_permission.py   # unittest：权限放行/询问/拒绝（mock 用户输入）
    ├── test_resume.py       # 回归：/resume 与 compact 的 messages 引用稳定性
    ├── test_bash_timeout.py # 回归：前台超时杀进程树、后台 stdin 隔离
    ├── test_agent_tool_errors.py # 回归：工具参数错误不崩溃，错误回填给 LLM
    ├── test_file_tools.py   # 回归：文件工具的 ~ 路径展开
    ├── test_mcp.py          # unittest：SDK 类型转换、工具包装、失败跳过、配置读取
    ├── test_mcp_commands.py # unittest：/mcp 增删查（确定性合并，不丢已有配置）
    ├── test_console_output.py # 回归：输出流不支持 emoji（GBK 管道）时不崩
    ├── test_subagent.py     # unittest：真并行（Barrier）/ 并发上限 / 禁嵌套 / 任务隔离 / 汇总输出
    └── test_rag.py          # 回归：无 langchain 也能导入 / 索引不可用时降级不抛异常 / 空目录触发补建 / k=8
```

## 快速开始

```bash
pip install openai python-dotenv tavily-python pyyaml mcp
# 复制 .env.example 为 .env，填入所用模型的 Key/BaseURL（KIMI_API_KEY / KIMI_BASE_URL 或 DEEPSEEK_*）与 TAVILY_API_KEY

# 可选：启用 rag_search 知识库检索（会拉 langchain / faiss / torch，体积较大）
pip install -e ".[rag]"
python -m rag.build_index     # 预热索引，避免第一次对话中途卡 2 分钟

# 方式一：项目内直接运行
python main.py

# 方式二：安装为全局命令，任意目录下启动
pip install -e .
miniCC
```

- 存储位置：会话 `~/.miniCC/sessions/`，长期记忆 `~/.miniCC/memory.json`，技能 `~/.miniCC/skills/<name>/SKILL.md`（frontmatter 写 `description`，正文写操作规范；手动放入的技能用 `/skills` 刷新即可发现，无需重启）。仓库自带的内置技能（如 `find-skills`）在首次启动时自动复制到该目录，已存在则不覆盖；RAG 索引 `rag/rag_index/<库名>/`（已 gitignore，不入库）
- RAG 知识库（可选）：`pip install -e ".[rag]"` 启用。把 PDF 放进 `static/rag_files/`，并在同目录的 `knowledge_bases.json` 里登记一个库：
  ```json
  { "ai-agents-in-depth": { "file": "AI-Agents-In-Depth.pdf", "description": "一句话描述，模型靠它决定用哪个库" } }
  ```
  `file` 是磁盘上的 PDF 文件名（中英文都行），键名是给模型的**库名**（建议短、ASCII，因为模型必须一字不差地输出它）。库列表在启动时读入并拼进 `rag_search` 的描述，所以**新增库要重启**才被模型看到（和 MCP 工具一样）。索引按库懒建：某库首次被检索时自动构建（约 2~3 分钟/库，随篇幅增长），也可先 `python -m rag.build_index` 一次建好全部；换 PDF 后要删掉该库的索引目录重建。未安装 RAG 依赖时 miniCC 照常启动，`rag_search` 只返回一句不可用提示。**首次检索还要下载 cross-encoder 精排模型 `BAAI/bge-reranker-v2-m3`（2.14 GB，实测 140 秒，之后走 HF 缓存）**，并且它同样在函数内懒加载，所以不检索就不会多下这个模型
- MCP 日志：stdio 服务器自身的日志转存到 `~/.miniCC/logs/mcp-<服务器名>.log`（不刷屏）；连接失败、调用失败由 miniCC 直接报告
- 项目指令：全局 `~/.miniCC/CC.md` 与项目根目录 `CC.md` 会被自动追加到系统提示词（全局在前、项目在后），每次请求实时读取，写完即生效
- 模型切换：默认 `deepseek`；`/model` 查看当前模型与可选列表，`/model kimi` 切换（需在 `.env` 配好该模型的 `KIMI_API_KEY` / `KIMI_BASE_URL`）；在 `llm/model.py` 的 `MODELS` 中加一条配置即可接入新模型
- MCP 工具：推荐用斜杠命令管理（重启后连接生效）：
  ```
  /mcp add niu-lai https://niu-lai.net/api/mcp            # 远程 HTTP 服务器
  /mcp add yahoo -- uvx --with "mcp<2" yahoo-finance-mcp  # 本地 stdio 服务器（-- 之后为命令）
  ```
  `/mcp` 列出全部、`/mcp remove <name>` 移除。也可直接编辑 `~/.miniCC/mcp.json`（格式与 Claude Code 的 `.mcp.json` 一致：http 用 `url` + `headers`，stdio 用 `command` + `args` + `env`）
- 常用命令示例：`/resume`（列出历史会话并选择继续）、`/context`（查看上下文占用）、`/compact`（手动压缩上下文）、`/skills`（列出可用技能）、`/memory 用户偏好...`（记住约定）、`! pytest tests/`（直通跑命令）

## 技术栈

Python 3.10+（dataclass / typing）、OpenAI Python SDK（function calling）、官方 mcp SDK（MCP 客户端）、Tavily Search API、PyYAML、unittest；**可选** RAG 栈：LangChain（社区包 / HuggingFace / PyMuPDF4LLM / text-splitters）、FAISS、`BAAI/bge-small-zh-v1.5`（经 sentence-transformers）、cross-encoder `BAAI/bge-reranker-v2-m3`（同经 sentence-transformers 的 `CrossEncoder`）、BM25（`rank-bm25`）+ `jieba` 分词；setuptools 打包（`pyproject.toml` → `miniCC` 命令，RAG 相关依赖放在 `[rag]` extra）；配置全部经 `.env` 注入，不硬编码密钥。
