# 项目逻辑

当前项目采用“两层编排”：

1. 主流程负责入口页面读取、静态/动态策略判断、计划生成与最终代码导出
2. `exploration` 子图负责动态页面探索、页面交互验证、human in the loop 处理与探索总结

项目目标不是长期运行一个黑盒爬虫，而是：

- 先判断目标网站更适合静态抓取还是动态抓取
- 如果需要动态探索，就通过 `exploration` 子图验证真实页面路径与交互方式
- 再把探索得到的结果整理成 `scraping_plan`
- 最后导出可直接执行的 Python 代码

## 主流程

当前主流程如下：

```text
html_loader
-> strategy_router
   |- static  -> static_prepare -> code_exporter -> END
   |- dynamic -> exploration_subagent
                 -> plan_synthesizer
                 -> code_exporter
                 -> END
```

### `html_loader`

读取入口 URL 的 HTML。

### `strategy_router`

直接基于入口页清洗后的 HTML 结构判断采用：

- `static`
- `dynamic`

这里不再单独做 HTML 摘要节点，而是直接让模型根据清洗后的页面结构判断是否需要浏览器交互。

### `static_prepare`

如果页面适合静态抓取，就基于清洗后的 HTML 直接形成静态 `scraping_plan`。

### `exploration_subagent`

如果页面需要动态交互，就进入 `exploration` 子图。

### `plan_synthesizer`

主流程使用：

- `exploration_summary`
- `human_intervention_summary`

生成最终 `scraping_plan`。

这里的 plan 不要求固定 JSON，而是要求描述清楚：

- 每一步访问哪个页面
- 执行什么动作
- 期待什么结果
- 如何判断成功
- 如果涉及 human in the loop，代码应如何暂停并等待用户确认

### `code_exporter`

最后基于：

- `entry_url`
- `scraping_plan`
- `user_request`

导出最终可执行代码，并写入：

- `state["final_code"]`
- `state["final_code_path"]`
- [exports/final_code.py](/E:/learning/economic_activities/AI_coding/web_crawler_agent_local/exports/final_code.py)

在写入前，会去除可能出现的 ```python / ``` 围栏。

## exploration 子图

`exploration` 是独立的 LangGraph 子图，用于动态页面探索。

### 子图职责

- 观察当前页面
- 选择下一步工具
- 为选中工具构造参数
- 执行工具
- 处理中途出现的验证码、登录页、干扰弹层
- 将有效探索过程整理为 `exploration_history`
- 最后输出面向代码生成的 `exploration_summary`

### 子图节点

当前 exploration 子图包含这些节点：

- `browser_bootstrap`
- `observer`
- `human_gate_detector`
- `human_gate_pause`
- `human_gate_resume`
- `tool_selector`
- `tool_arg_builder`
- `tool_executor`
- `post_tool_interrupt_handler`
- `state_updater`
- `exploration_summary`
- `human_intervention_summary`

其中：

- ```exploration/nodes.py``` 只负责节点函数
- ```exploration/graph.py``` 负责子图装配、路由与运行入口

## exploration 的输入原则

exploration 阶段采用“当前页优先”的输入方式。

LLM 在探索时看到的核心信息是：

- 当前页 `page_architecture`
- 最近几步 `exploration_history`
- 当前选中工具对应的工具说明文档

### 当前页结构

`page_architecture` 是当前页面清洗后的完整结构文本，用于让模型直接判断：

- 当前页面属于什么类型
- 页面上有哪些可以尝试的交互
- 接下来更适合搜索、点击、翻页、等待，还是进入详情页

模型默认只看当前页，不读取历史页面的大块脚本结构，以节省 token。

### `exploration_history`

`exploration_history` 是 exploration 的核心过程记忆。

每一条 history 主要记录：

- 本轮调用了什么工具
- 传入了什么参数
- 当前处于哪个页面
- 结果是否成功
- 是否点击了目标
- 是否出现了 human gate
- 这一步是否推动了后续提取

`exploration_history` 不再保存历史页面的大块结构文本，而是只保留足够支持后续决策和最终总结的关键信息。

## 工具选择与渐进式披露

exploration 采用两阶段工具决策：

### 第一阶段：`tool_selector`

模型先只决定“下一步要用哪个工具”。

输入：

- 当前页 `page_architecture`
- 最近几步 `exploration_history`
- 工具索引文档

输出：

- 工具名
- 工具选择理由

### 第二阶段：`tool_arg_builder`

模型只为已选工具生成参数。

输入：

- 当前页 `page_architecture`
- `exploration_history`
- `recent_failure_summary`
- 单个工具的详细说明文档

输出：

- 工具参数
- 参数构造理由

这样可以避免一次性把所有工具细节全部喂给模型。

## 当前工具集合

当前 exploration 可见工具包括：

- `finish`
- `search_site`
- `click_target`
- `goto`
- `go_back`
- `wait_for_selector`
- `scroll_once`
- `sample_detail_pages`

其中：

- `click_target` 是唯一保留的点击工具
- 不再向 LLM 暴露 `click`
- 不再向 LLM 暴露 `list_links`、`list_buttons`、`count_selector`

工具说明存放于：

- ```tool/browser_tool_explanation/index.md```
- ```tool/browser_tool_explanation```

工具实现位于：

- ```tool/browser_tool.py```
- ```tool/pageread_tool.py```

## `sample_detail_pages` 与详情页结构分析

`sample_detail_pages` 现在承担两层作用：

1. 验证候选详情链接是否真的能进入详情页
2. 为后续代码生成建立详情页提取逻辑

当前实现中，详情页结构分析不再作为一个独立 step 暴露给 LLM，也不会单独增加 exploration 步数。

实际逻辑是：

- 当 `sample_detail_pages` 成功采样到详情页后
- 系统会立刻读取该详情页的 `page_architecture`
- 并调用模型生成一段“如何从这个详情页提取用户目标信息”的说明
- 这段说明会直接作为 `detail_architecture_read` 合并进同一条 `sample_detail_pages` 的 history 记录中

也就是说：

- `sample_detail_pages` 成功
- 详情页结构分析必然发生
- 两者绑定在同一条 history 中
- 不会额外新增 `step` 或 `index`

这样既保留了详情页提取逻辑证据，又避免了探索步数膨胀。

## human in the loop

项目保留 human in the loop。

当 exploration 过程中出现这些情况时，会进入人工介入流程：

- 登录页
- 验证码
- 二次验证
- 人机校验
- 无法自动关闭的干扰弹层

处理逻辑是：

1. 先检测当前页面是否被阻塞
2. 如果是可自动关闭的干扰弹层，先尝试自动关闭
3. 如果自动关闭失败，或本身就是登录/验证码等真正阻塞场景，则进入 `human_gate_pause`
4. 用户处理完成后，通过 `human_gate_resume` 恢复 exploration

如果工具执行后在进入 `state_updater` 前被 human gate 打断，子图会保留待更新状态，并在恢复后优先完成这次状态提交，避免有效工具结果丢失。

## 本地登录态复用

项目根目录下维护一份本地 ```session.json```，用于保存 Playwright 的站点登录态。

当前逻辑是：

- 进入 exploration 时，浏览器会先按目标 URL 的域名查找本地会话信息
- 如果存在对应站点的会话，就优先复用该登录态
- 如果本地登录态不存在或已经失效，则继续走现有的 human in the loop 流程
- 用户手动完成登录、验证码或验证步骤后，当前上下文的登录态会写回 `session.json`

这部分逻辑只存在于本地浏览器工具层：

- 不进入 exploration prompt
- 不进入主流程 prompt
- 不暴露给任何 LLM
- 不写入最终导出的代码

## `exploration_summary` 的作用

exploration 结束后，不再把大量中间页面结构直接回传给主流程，而是生成一份面向代码生成的总结：

- 哪些动作有效
- 哪些动作失败
- 页面路径是怎样推进的
- 搜索、分页、详情进入、字段提取应如何实现
- human in the loop 应该在什么位置暂停和恢复

`plan_synthesizer` 和 `code_exporter` 都依赖这份总结。

## 日志

当前调试日志分成两类：

### 主流程日志

- ```debug/debug_log.json```

记录主流程节点级事件，例如：

- 当前执行到哪个主节点
- 该节点更新了哪些核心状态
- `scraping_plan`
- 最终代码导出情况

### exploration 详细记录

- ```debug/exploration_record.json```

记录 exploration history 的详细流水，例如：

- `step`
- `page_url`
- `decision.tool`
- `decision.args`
- `result`
- 如果某次 `sample_detail_pages` 成功，还会在同一条记录里包含 `detail_architecture_read`

因此这个文件反映的是“真实探索动作记录”，而不是 exploration 内部所有节点的逐步状态快照。

## 最终产物

项目最终会得到：

- `scraping_plan`
- `final_code`
- `final_code_path`

最终代码写入：

- ```exports/final_code.py```

当前代码导出约束包括：

- 动态浏览器默认 `headless=False`
- 保留 human in the loop 逻辑
- 对敏感浏览器动作加入轻量随机等待
- 如果涉及 human in the loop，必须使用显式用户确认，如 `input()`
- 不允许用随机等待替代用户确认
- 禁止依赖未验证的 popup 假设
- 禁止使用未验证的 `page.evaluate()` 直接调用页面内本地函数进行导航
