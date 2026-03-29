# 网页爬虫智能体项目逻辑

基于 LangGraph 的网页爬虫 Agent。系统先判断站点适合静态抓取还是动态抓取；如果是动态站点，会先做浏览器探索，再合成结构化抓取计划，最后由宿主 `runtime_executor` 解释执行该计划，而不再生成并运行黑盒 Python 脚本。

## 工作流

```text
html_loader -> html_summarizer -> strategy_router
  |- static  -> static_prepare ------------------------------|
  |- dynamic -> browser_bootstrap                           |
                 -> exploration_observer                    |
                 -> human_gate_detector                     |
                    |- pause -> human_gate_pause            |
                    |           -> human_gate_resume -------|
                    |- continue -> exploration_decider      |
                                   -> exploration_tool_executor
                                   -> exploration_state_updater
                                   -> exploration_router
                                      |- continue -> exploration_observer
                                      |- stop -> plan_synthesizer --------|
                                                               -> runtime_executor
                                                               -> result_evaluator
                                                                  |- pass -> runtime_finalizer -> code_exporter -> END
                                                                  |- fail -> runtime_debug_agent -> runtime_executor
```

## 核心原则

### 1. 探索阶段只收集证据

- exploration_decider 只能基于当前快照、已列出的链接、按钮、脚本片段和历史动作做下一步决策。
- 未验证详情访问或分页行为前，不允许直接 `finish`。
- 如果用户请求里明确包含关键词搜索需求，并且页面存在搜索入口，探索阶段要优先验证搜索流程。
- `click_target` 是默认的精确点击工具，优先传入作用域、选择器、元素类型、文本、精确匹配和索引。
- `search_site` 用于站内搜索，参数包括 `query`、`input_selector`，以及可选的提交按钮或回车方式。
- `sample_detail_pages` 只消费 LLM 显式传入的 `args.links`。

### 2. 正式抓取改为 runtime plan 执行

- `plan_synthesizer` 产出结构化 `scraping_plan`。
- `runtime_executor` 直接解释 `scraping_plan`，通过宿主 Playwright 会话执行导航、翻页、详情访问和字段提取。
- 若 `required_actions` 中包含搜索步骤，runtime 会先执行搜索，再进入列表或详情提取。
- 不再使用 `code_generator / code_executor / debug_agent` 这套黑盒代码执行链路。
- debug 时修的是 `scraping_plan`，不是整段 Python 代码。
- 在 runtime 通过校验后，再由 `code_exporter` 基于已验证计划导出最终可执行代码。

### 3. human gate 统一处理

- 探索阶段和正式抓取阶段都复用 `detect_human_intervention`。
- 遇到登录、验证码、二次验证、人机识别时，保留浏览器窗口和上下文，暂停等待用户处理。
- 用户完成后在同一浏览器上下文中继续执行，不丢失登录态。
- 若用户中止，则任务终止并记录错误。

### 4. 工具层统一服务 exploration 和 runtime

- `tools.py` 负责统一浏览器能力层。
- 保留的关键安全动作包括：
  - `safe_goto`
  - `safe_go_back`
  - `safe_click`
  - `click_target`
  - `safe_wait_for_selector`
  - `safe_scroll_once`
  - `search_site`
- 原先与这些 `safe_*` 重叠的裸 `goto / click / go_back / wait_for_selector / scroll_once` 已移除。
- `build_page_snapshot`、`list_links`、`list_buttons`、`extract_preview`、`extract_text`、`extract_structured_rows` 同时服务探索和运行时。

## 计划执行逻辑

### dynamic runtime

- 从 `scraping_plan.entry_url` 启动浏览器。
- 根据 `list_page.row_selector` 等信息抽取列表项。
- 如果 `required_actions` 中有搜索动作，先执行搜索。
- 若计划包含详情页字段或 `page_pattern == "list_to_detail"`，则进入详情页提取字段，再返回列表页。
- 根据分页规则执行一次翻页，再继续下一轮。
- 每次关键导航后都检测 human gate。
- 最终将结果写入：
  - `result_data`
  - `result`
  - `execution_meta`

### static runtime

- 使用 `requests + BeautifulSoup` 读取页面。
- 根据计划中的 `row_selector` 和字段规则提取结构化数据。
- 输出同样写入 `result_data / result / execution_meta`。

## 字段提取规则

- 优先使用显式 `selector`。
- 若字段来自键值表格或标签行，优先用：
  - `container_selector` 或 `row_selector`
  - `match_text` / `label`
- 先定位整行，再分析 `th/td`，避免直接假设固定列号。
- 尽量使用容器优先、标签优先、结构优先的规则，而不是脆弱的 `nth-child`。

## 记忆分层

### state

保存全局、跨节点需要持续存在的信息，例如：

- `current_page_snapshot`
- `exploration_history`
- `detail_samples`
- `scraping_plan`
- `result_data`
- `result`
- `execution_meta`
- human gate 状态字段

### metadata

只保存单轮、会被下一轮覆盖的临时信息，例如：

- `pending_exploration_decision`
- `last_tool_name`
- `last_tool_args`
- `last_tool_result`
- `last_listed_links`

当前页面的完整链接集合直接来自 `current_page_snapshot["links"]`，不再在 `state` 中重复存一份顶层 `available_links`。

## 模块职责

- `main.py`: LangGraph 节点图与路由
- `nodes.py`: 探索、计划合成、runtime 执行、runtime debug、代码导出
- `tools.py`: HTTP、DOM 快照、Playwright 会话、安全浏览器动作、人机阻塞检测
- `prompts.py`: 各阶段提示词
- `validators.py`: JSON 结构校验
- `state.py`: 全局状态定义
