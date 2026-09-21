# AI-Infra 检索评测基线

日期：2026-09-21  
文档：`AI-Infra-Book.pdf`  
SHA-256：`cdbb925efe420ab0c65a245068770e443b4f52995e902c56669324329725e217`

## 命令

```powershell
.venv\Scripts\python.exe scripts\evaluate_retrieval.py --data-dir D:\rag\data --output test-results\ai-infra-smoke.json
```

该运行未启用 `--with-answer`，没有调用回答服务。

## 结果

| 题型 | 通过 / 总数 |
| --- | ---: |
| definition | 5 / 5 |
| mechanism | 5 / 5 |
| comparison | 4 / 4 |
| summary | 4 / 4 |
| acronym | 4 / 4 |
| insufficient_evidence | 0 / 3 |
| 合计 | 22 / 25 |

定义、机制、对比、章节总结和缩写题均在最终证据中命中预期页码或术语。MHA、GQA、MQA 的第 44 页证据已稳定召回，既有 MHA 回归测试仍应保留。

## 剩余失败与裁定

`q23`、`q24` 和 `q25` 均为 `unexpected_evidence`。当前向量检索没有相似度阈值，任何问题都会返回最近片段；因此这些题暴露的是“无关问题仍返回相似片段”，并不能证明资料中存在答案。

本轮不为让这三题通过而降低召回或加入未经验证的全局阈值。下一轮应单独设计“证据不足”判定：以真实问题集校准阈值、明确回答服务应如何拒答，并为该行为增加独立回归测试。该工作与本轮“高频概念漏召回”目标不同，需单独评审后实施。

没有出现重复的 `not_recalled` 或 `not_selected` 故障模式，因此本轮不修改 `backend/app/engine.py`。这保留了经评测验证的当前检索策略，避免基于单次假设引入回归。
