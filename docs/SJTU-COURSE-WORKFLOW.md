# 上海交通大学 LLM 学习实验工作流

本指南把课程中的提示词、模型、参数、知识库和工具策略实验直接落到 LLM Eval Lab
已经实现的领域对象中。它不新增平行的“课程实验”模块，也不假定某门课程的官方评分
细则；它提供的是一套可重复、可审计、适合课程汇报和面试讲解的实验方法。

## 一句话理解

课程学习不是“问一次模型、截一张图”，而是：固定大部分条件，只改变一个主要自变量，
用同一版本的评测集（Evaluation Suite）比较 Baseline 和 Candidate，保存证据，再给出带
限制条件的结论。

## 课程活动与平台对象的对应关系

| 课程活动 | LLM Eval Lab 对象 | 应记录的内容 |
| --- | --- | --- |
| 修改系统提示词 | Application Version | `system_prompt`；其余配置保持不变 |
| 比较两个本地模型 | Application Version | `model_name`；提示词、参数、知识和工具保持不变 |
| 调整 temperature 等参数 | Application Version | `generation_parameters`；一次只改一个主要参数 |
| 替换 RAG 资料或检索策略 | Application Version | `knowledge_config` 及资料版本 |
| 修改工具权限或调用策略 | Application Version | `tool_config` 及允许/禁止的工具行为 |
| 设计普通题、幻觉题和攻击题 | Evaluation Suite / Test Case | 输入、依据、必须事实、禁止内容、类型和严重级别 |
| 执行一次回答 | Test Case Execution | 完整提示上下文、响应、延迟、用量或提供方失败 |
| 做一次受控对比实验 | Evaluation Run | 同一 Suite 下的 Baseline/Candidate 配对证据 |
| 检查事实和禁止内容 | Deterministic Evaluation | 规则版本、逐条通过/失败和精确命中证据 |
| 检查语义质量 | Semantic Evaluation | 独立裁判的结论、理由、置信度和配置快照 |
| 处理评分冲突 | Human Review | 原始证据、人工结论、理由和处理时间 |
| 写实验结论 | Release Decision | 版本化规则、指标、阻塞原因、证据链接和指纹 |

这些名称应继续使用仓库 [领域语言](../CONTEXT.md) 中的定义。“课程作业”“实验报告”是
这些对象的使用场景，不是新的运行时领域对象。

## 受控变量规则

一次 Evaluation Run 应只回答一个主要问题。例如“安全提示词是否降低 prompt injection
风险”，而不是同时更换模型、提示词、temperature 和知识库。

实验前完成下面的检查：

1. 写出一个可证伪的假设。
2. 明确唯一的主要自变量。
3. Baseline 与 Candidate 使用同一 Evaluation Suite 版本。
4. 把必须保持相同的模型、参数、知识和工具配置列出来。
5. 预先写下通过、失败或需要人工复核的判据。
6. 运行后保留失败和冲突，不因结果“不好看”而删除证据。

如果必须同时改变多个条件，应拆成连续实验。例如先比较提示词，再固定获胜提示词比较模型，
不要把两次变化混成一个无法解释的结论。

## 具体实验：提示词安全加固

### 1. 研究问题

安全加固后的系统提示词，是否能在保持正常客服正确性的同时，降低 prompt injection 和
jailbreak 测试中的禁止内容命中？

### 2. 假设

Candidate 在普通问题上的必须事实通过率不低于 Baseline，并且在安全测试上的禁止内容
失败数少于 Baseline；若语义裁判与确定性规则冲突，则必须进入 Human Review，不能直接
宣布 Candidate 更安全。

### 3. Application Versions

| 配置 | Baseline | Candidate | 是否受控 |
| --- | --- | --- | --- |
| provider / model | 同一个已安装的本地模型 | 同 Baseline | 是 |
| system prompt | 普通客服提示词 | 增加拒绝指令覆盖、隐藏提示泄露和无证据审批的规则 | 否，主要自变量 |
| generation parameters | `temperature: 0` | 同 Baseline | 是 |
| knowledge config | 同一版 Northstar 政策资料 | 同 Baseline | 是 |
| tool config | 相同或均为空 | 同 Baseline | 是 |

Application Version 是完整不可变配置，不应只记录“Prompt A”和“Prompt B”。创建后把两个
版本名称或 ID 填入实验记录模板。

### 4. Evaluation Suite

第一轮可以使用 **Northstar Electronics Support v1**，同时观察普通、幻觉、prompt
injection 和 jailbreak Test Case。用于五分钟面试的平台验证则选择聚焦的 **Northstar
Interview Demo v1**。

二者用途不同：

- 完整八 Case Suite 用来观察质量与安全的整体权衡；
- 单 Case Interview Suite 用确定性 fixture 展示证据链，不代表真实模型能力。

### 5. 预注册证据

运行前写下要观察的指标：

- correctness：必须事实通过数；
- safety：禁止内容未命中的通过数；
- new regression：Baseline 通过、Candidate 失败的 Test Case；
- severity：普通、重要、release blocking；
- semantic outcome / confidence：与确定性证据并列，不覆盖规则结果；
- Human Review：冲突、低置信度、证据不足或裁判失败的最终人工结论；
- latency / cost：仅在实际提供方返回数据时记录，不用猜测值补齐。

### 6. 两种执行方式

#### 确定性离线平台验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-demo.ps1
```

在 **Evaluation Runs** 中选择：

- Baseline：`Northstar demo Baseline (deterministic fixture)`；
- Candidate：`Northstar demo Candidate (known safety regression)`；
- Suite：`Northstar Interview Demo v1`。

这个路径预置一个 Candidate release-blocking 新回归和一个自动评分冲突，用来验证
“运行—证据—复核—发布判定”的平台能力。报告必须写成“确定性演示 fixture 产生了已知
回归”，不能写成“某真实模型被实测不安全”。

这个确定性例子的复核动作和预期结论是固定的：

1. 在 Human Review queue 打开 Candidate 的 automatic-score conflict。
2. 保留确定性失败和语义通过两层自动证据，人工 outcome 选择 **Fail**。
3. rationale 填写“Candidate 响应精确命中了禁止的 prompt-injection 内容”。
4. 提交后使用 **Default local release rule v1** 生成 Release Decision。
5. 预期结论为 **Fail**，直接原因是 release-blocking 新回归；人工复核支持该结论，但不
   改写原始 correctness、safety 或语义证据。

#### 可选的本地 Ollama 观察

LLM Eval Lab 不会自动下载模型。只有机器上已经存在合适模型时才执行：

```powershell
ollama list
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

为 Baseline 和 Candidate 创建 provider 为 `ollama` 的 Application Version，模型名必须
逐字来自 `ollama list`。语义裁判也要在忽略的 `.env` 中配置为一个明确存在的本地模型。
如果服务、被测模型或裁判不可用，应记录 provider/judge failure；不得把未运行、超时或
缺失模型描述为成功实验。Ollama 实验的 Human Review 和 Release Decision 必须按实际
返回证据填写，本指南不预设其通过或失败。

### 7. 形成实验结论

实验报告至少回答：

1. 哪一个配置是主要自变量？
2. Candidate 相对 Baseline 新增或修复了哪些 Test Case？
3. 结论来自精确规则、语义判断还是 Human Review？
4. Release Decision 为什么是 pass、fail 或 manual review required？
5. 有哪些限制使结论不能推广到其他模型、评测集版本或业务？

使用 [课程实验记录模板](templates/SJTU-EXPERIMENT-RECORD.md) 保存这些信息。

## 与课程学习目标的结合

这个工作流能把常见学习内容变成可展示的工程证据：

- Prompt Engineering：不只展示好回答，还展示同一 Suite 下的回归和安全副作用；
- LLM Evaluation：区分透明规则、语义裁判与人工判断，而不是只给单一总分；
- RAG：把资料版本纳入 Application Version，并用 grounding material 检查回答依据；
- Agent / Tool Use：把工具权限视为版本配置，用禁止行为 Test Case 检查越权；
- AI Safety：把 prompt injection、jailbreak 和 release-blocking 规则接入正式发布门禁；
- Engineering Practice：用不可变配置、持久化证据、版本化规则和 CI 让实验可复现。

## 三分钟验收

1. 打开本指南，任选一种课程活动，指出它对应哪个平台对象。
2. 打开实验记录模板，填入一个假设、一个主要自变量和至少三个受控变量。
3. 运行 `scripts\start-demo.ps1`，在 Evaluation Runs 中选择两个 demo 版本和 Interview
   Suite。
4. 找到一个 new regression、一个精确禁止内容命中和一个 Human Review conflict。
5. 说明为什么这个确定性结果能证明平台流程，但不能证明某个真实 Ollama 模型的能力。

完成这五步，就能把“我学过 LLM”转化为“我能设计并解释一个可重复的 LLM 质量与安全
实验”。
