# v0.25联合经历人工审阅

[打开交互HTML总览](index.html) · [中文导读](reading-notes.md) · [CSV索引](summary.csv) · [离线ZIP](../v025-joint-experiences.zip)

原16条联合经历全部导出；不调用模型、不重放世界、不重新评分。中文标签与导读为审阅辅助；成员原话保留原文。

| 序号 | 经历 | 类型 | 实际生成/请求 | 原R | 完整职责 |
|---|---|---|---:|---:|---|
| 01 | [train-00-0](episodes/train-00-0.md) | A · 依据交接与新交付 | 17/18 | 0.2 | 否 |
| 02 | [train-01-0](episodes/train-01-0.md) | B · 错误初稿复核与修复 | 15/17 | 0.0 | 否 |
| 03 | [train-00-1](episodes/train-00-1.md) | A · 依据交接与新交付 | 19/19 | 0.2 | 否 |
| 04 | [train-01-1](episodes/train-01-1.md) | B · 错误初稿复核与修复 | 12/14 | 0.0 | 否 |
| 05 | [train-00-2](episodes/train-00-2.md) | A · 依据交接与新交付 | 17/17 | 0.2 | 否 |
| 06 | [train-01-2](episodes/train-01-2.md) | B · 错误初稿复核与修复 | 14/16 | 0.0 | 否 |
| 07 | [train-00-3](episodes/train-00-3.md) | A · 依据交接与新交付 | 20/21 | 0.2 | 否 |
| 08 | [train-01-3](episodes/train-01-3.md) | B · 错误初稿复核与修复 | 16/18 | 0.0 | 否 |
| 09 | [train-00-4](episodes/train-00-4.md) | A · 依据交接与新交付 | 22/22 | 0.2 | 否 |
| 10 | [train-01-4](episodes/train-01-4.md) | B · 错误初稿复核与修复 | 13/15 | 0.0 | 否 |
| 11 | [train-00-5](episodes/train-00-5.md) | A · 依据交接与新交付 | 17/18 | 1.0 | 是 |
| 12 | [train-01-5](episodes/train-01-5.md) | B · 错误初稿复核与修复 | 25/27 | 0.0 | 否 |
| 13 | [train-00-6](episodes/train-00-6.md) | A · 依据交接与新交付 | 22/22 | 0.2 | 否 |
| 14 | [train-01-6](episodes/train-01-6.md) | B · 错误初稿复核与修复 | 17/19 | 0.3 | 否 |
| 15 | [train-00-7](episodes/train-00-7.md) | A · 依据交接与新交付 | 22/22 | 0.2 | 否 |
| 16 | [train-01-7](episodes/train-01-7.md) | B · 错误初稿复核与修复 | 15/17 | 0.0 | 否 |

## 文件结构

- `index.html`：可筛选总览；`episodes/*.html`：成员/事件/关键词筛选、可展开的完整上下文与返回。
- `graphs/*.svg`：成员协作有向图，按事件顺序展示可确认的跨成员请求、交接、提交检查和复核反馈；在HTML点击箭头可定位原事件。实线为工具已记录，虚线为被拒尝试，不等同业务判断正确或对方已读。未绑定请求、幂等重试与历史提交问题单独标注；无法确认接收成员的拒绝不虚构连线，图下注明原序号。
- `episodes/*.md`：适合逐段批注，模型正文与执行参数保留，工具返回摘要有明确标注。
- `data/*.json`：角色与调用身份绑定的审阅数据；完整输入按message/tool内容地址去重，可精确还原。
- `reading-notes.md`：事后中文导读与逐条原事件证据；不混入模型原始轨迹。
- `manifest.json`：原始文件SHA、覆盖核对与输出清单。

HTML为离线文件，无CDN、无网络请求；下载ZIP后打开其中index.html。模型输入详情由页面内嵌数据展开，无需本地Web服务。

审阅者可看全局快照；每名成员实际可见内容以对应请求为准，不能把全局材料当作其当时输入。原数值token/logprob数组没有复制到此阅读包，仍位于服务器SHA绑定原件，故本包不替代完整训练备份。

## 生成方法与边界

导出器 `scripts/export_joint_review_v025.py` 只读原支持集合；中文阅读说明独立保存在 `notes.json` / `reading-notes.md`。在仓库根目录运行：

```bash
.venv/bin/python scripts/export_joint_review_v025.py --zip docs/reviews/v025-joint-experiences.zip
```

各原请求包含顶层字段顺序，使用 `reconstruct_input(review, decision)` 可原样重建并复现项目 json_bytes 序列化的 input_sha256。导出时核验所有请求、世界动作以及捕获文件，两个独立 fixture 控制跨角色同调用ID、拒绝／未生成／无调用停止、末尾格式反馈和原文HTML转义。

原model_attempt、public_observation/public_tools、policy_decision、role_not_scheduled、动作链接与服务包装不逐条展开；实际请求中的完整视野与工具定义、生成原文、真实世界执行、格式反馈、控制和边界事件均保留。审阅包不包含完整训练token数组或运行资源遥测。

## 覆盖计数

```json
{
  "started_requests": 302,
  "actual_generations": 283,
  "non_generation_requests": 19,
  "world_actions": 258,
  "world_action_ok": 231,
  "world_action_rejected": 27,
  "boundary_errors": 29,
  "unlinked_boundary_errors": 9,
  "parse_errors": 5,
  "format_feedback_events": 14,
  "model_control_events": 11
}
```

