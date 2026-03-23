# 网页爬虫智能体 — 项目逻辑

基于 LangGraph 的智能爬虫 Agent。用户给出自然语言需求 + 目标 URL，Agent 自动完成策略选择 → 页面探索 → 计划合成 → 代码生成/执行/评估 → 全量代码产出。

## 工作流

```
html_loader → html_summarizer → strategy_router
               ├─ static → static_prepare ─────────────────────┐
               └─ dynamic → browser_bootstrap                  │
                              ↓                                 │
                   ┌→ exploration_observer                      │
                   │    → exploration_decider                   │
                   │    → exploration_tool_executor             │
                   │    → exploration_state_updater             │
                   │    → exploration_router ──┐                │
                   │         │ continue        │ stop           │
                   └─────────┘         plan_synthesizer ────────┤
                                                                ↓
                                                         code_generator
                                                          → code_cleaner
                                                          → code_executor
                                                          → result_evaluator
                                                              ├─ pass → code_finalizer → END
                                                              └─ fail → debug_agent → code_executor (循环)
```

## 关键机制

### 防幻觉
- Plan JSON 必须先填 `reference_html_snippets`（原始 HTML 片段），再写 `selectors`
- 探索中验证过的操作记录在 `observations`，code_generator 优先参考

### 强制探索
- exploration_decider **禁止** 在关键交互未验证前 finish
- 每个交互都先作为待验证假设处理，优先使用 DOM、链接、按钮、脚本片段和历史成功步骤作为证据
- 若存在详情访问或分页，至少要验证一次对应交互再进入 plan_synthesizer

### 交互与导航原则（贯穿 plan_synthesizer → code_generator → debug_agent）

- 不要用 `page.evaluate()` 调页面内本地 JS 做导航/翻页
- 不要假设 javascript 链接一定触发真实 popup
- 对 javascript-style href，应先根据证据推断真实目标或实际交互方式，再决定是直接导航还是点击已验证元素
- 对存在多个相似目标的点击，优先使用 `click_target` 提供作用域、元素类型、文本和索引等约束，而不是只靠单一文本模糊匹配

### Sample Mode & Finalizer
- 代码顶部 `SAMPLE_LIMIT = 3`，只能用 `[:SAMPLE_LIMIT]` 切片
- result_evaluator 截断 stdout 至 2000 字符，≥1 条有效即通过
- code_finalizer 用正则移除 SAMPLE_LIMIT，产出全量代码 `final_code`

### 动态代码鲁棒性
- 导航后 `wait_for_load_state` + `wait_for_selector`
- 守卫 `page.url` 防意外重定向
- `try/except PlaywrightTimeoutError` 优雅降级
- 默认 `headless=False`，便于观测与调试

### 表格字段提取规则
- 对键值型表格，禁止在无证据时直接假设值一定在某个固定列
- 正确顺序是：先定位包含字段标签的整行，再验证该行的 `td/th` 结构，最后决定实际值所在单元格
- 若标签和值在同一单元格中，提取整格文本并去掉标签前缀
- `observations` 应记录关键字段的结构定位规则和必要回退策略

### Snapshot 结构
```json
{
  "url": "...",
  "title": "...",
  "local_snippet": "cleaned DOM text",
  "links": [{"text": "...", "href": "..."}],
  "buttons": [{"text": "...", "selector": "..."}],
  "candidate_blocks": [{"tag": "tr", "count": 11}],
  "script_snippets": ["function openWin(id){...}"]
}
```

### 探索记忆分层
- `state` 保存全局记忆，如 `available_links`、`exploration_history`、`detail_samples`
- `metadata` 只保存单轮临时记忆，如 `pending_exploration_decision`、`last_tool_name/args/result`、`last_listed_links`

### 探索工具
- `click_target` 是通用点击工具，支持 `scope_selector / selector / element_selector / text / exact / index`
- `sample_detail_pages` 只消费 LLM 显式传入的 `args.links`

## 模块职责

| 文件 | 职责 |
|------|------|
| `main.py` | LangGraph 有向图定义、路由逻辑、条件边 |
| `nodes.py` | 所有节点函数；`ask_llm_for_json` JSON 修复重试 |
| `state.py` | `CrawlerState` 全局上下文 TypedDict |
| `tools.py` | HTTP 加载、DOM 净化、playwright 浏览器封装、代码沙箱 |
| `prompts.py` | 提示词模板（含防幻觉、SAMPLE_LIMIT、交互验证、动态鲁棒性） |
| `validators.py` | JSON 结构验证器 |
| `llm.py` | LLM 实例化 |
