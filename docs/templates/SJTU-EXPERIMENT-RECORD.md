# LLM 课程实验记录

> 复制本文件后填写。不要把 `.env`、凭据、模型文件、数据库、运行日志或含个人数据的
> 原始提示内容提交到 Git。

## 1. 实验信息

- 实验标题：
- 日期：
- 课程章节或学习主题：
- 实验者：
- 仓库 commit：
- Evaluation Run ID：

## 2. 研究问题与假设

- 研究问题：
- 可证伪假设：
- 主要自变量（只能有一个）：
- 预期改善：
- 可能副作用：

## 3. Baseline 与 Candidate

| 配置 | Baseline | Candidate | 是否相同 |
| --- | --- | --- | --- |
| Application Version 名称 / ID |  |  | 否 |
| provider |  |  |  |
| model |  |  |  |
| system prompt 摘要 |  |  |  |
| generation parameters |  |  |  |
| knowledge config / 资料版本 |  |  |  |
| tool config / 权限策略 |  |  |  |

受控变量说明：

- [受控变量 1]
- [受控变量 2]
- [受控变量 3]

如果表中除主要自变量外还有不同项，停止运行并先拆分实验。

## 4. Evaluation Suite 与预注册判据

- Suite 名称 / 版本 / ID：
- 选择该 Suite 的原因：
- Test Case 数量和类型：
- release-blocking 条件：
- correctness 预期：
- safety 预期：
- latency / cost 预算（没有配置时写“未配置”）：
- 哪些结果必须 Human Review：

## 5. 执行环境

- 执行方式：确定性离线 fixture / 本地 Ollama / 其他已实现 provider
- 操作系统：
- provider 和模型的实际可用性证据：
- `ollama list` 中的准确模型名（未使用 Ollama 时写“不适用”）：
- Semantic Judge provider / model：
- 是否发生 provider 或 judge failure：

不要把 fixture 结果写成真实模型观察，也不要把失败或未运行写成通过。

## 6. 结果

| 指标 | Baseline | Candidate | 差异 |
| --- | ---: | ---: | ---: |
| correctness passed / total |  |  |  |
| safety passed / total |  |  |  |
| failed Test Cases |  |  |  |
| average latency |  |  |  |
| total cost |  |  |  |

- new regressions：
- existing failures：
- release-blocking evidence：
- 精确规则命中及 Execution ID：
- Semantic Evaluation 结论、理由与置信度：

## 7. Human Review

- Queue Item / Execution ID：
- 路由原因：
- 原始自动证据冲突：
- 人工 outcome：pass / fail
- rationale：
- 自动证据是否保持不变：

## 8. Release Decision

- Release Rule 名称 / 版本：
- Decision：pass / fail / manual review required
- 阻塞原因：
- Execution evidence 链接或 ID：
- evidence fingerprint：
- immutable snapshot 数量：

## 9. 结论与限制

- 假设是否得到支持：
- 能由本实验支持的最小结论：
- 不能由本实验推出的结论：
- 评测集版本、模型、裁判或环境限制：
- 是否存在 fixture 与真实模型证据混淆风险：

## 10. 反思与下一步

- 最重要的失败或意外：
- 哪条证据改变了最初判断：
- 下一个实验只改变哪个变量：
- 是否需要新增或升级 Evaluation Suite：
- 是否需要 Human Review 规则或 Release Rule 调整：
