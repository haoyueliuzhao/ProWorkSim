# v053 启动状态记录

最新状态：2026-10-20 18:10 CST，v5 已完成全部数据与运行前准备，正式调度监控器已启动；18:47 的观察状态为 `waiting_resources`，尚无任务派发。完整题单、实测准备耗时和监控策略见 [v5 准备完成记录](software-panel-v053-preparation-complete-v5.md)。以下保留 14:44 的历史启动快照。

记录时间：2026-10-20 14:44 CST。这是后台作业的时点记录，不是能力结果；后续状态以流水线及正式结果文件为准。

## 已启动的作业

代码修订 `785289d32737bfd4720ae17723cda1e3e8e7ef60` 已同步到 `haoyueliuzhao/ProWorkSim` 的 main。固定方案见[实验协议](software-panel-v053-protocol.md)：200 个不同任务各一次，预选 40 题各追加两次，共 280 回合；原始 Qwen3.5-9B、原生 OpenHands 单 Agent、无训练适配器，输入加输出预算总上限 140,000,000 token。

系统服务 `proworksim-v053-panel-v4.service` 于 14:39:46 CST 启动，观察时为 active/running，MainPID 400708。它先做 CPU 环境准入，随后才依次冻结题单／重复子集／seed、检查全部初始请求、封存运行配置并进入正式监督器。初期观察已有 9 份有效任务资格，尚无完整仓库资格和最终 200 题面板；正式监督器未进入，正式模型调用为 0。

本轮使用独立 `environments-v4` 与 `pipeline-v4`，不把旧准备中断记录当作模型失败。Pydantic 的成功 clean 回执直接复用，缓存政策修订见[说明](software-panel-v053-cache-adaptation-v4.md)。前 32 个固定候选镜像缺失时，准入等待专用 Docker 导入，不另行发起重复 pull；等待上限 7,200 秒，超时按公共故障暂停。

用户级服务 `proworksim-v053-image-prefetch.service` 独立运行，观察时 MainPID 401231。它自动接续固定排名 25–32 的资产，不依赖交互回合继续存在。镜像数量和实测速率的较早快照见[传输说明](software-panel-v053-image-transfer.md)；其中“已加载”与“层已下载完”有分别记录，不能把后者视为环境准入通过。

## 当前证据位置

- 准备与正式运行编排：`runs/software-panel-v053/pipeline-v4/pipeline-state.json`
- CPU 阶段日志：`runs/software-panel-v053/pipeline-v4/00-environment_admission.log`
- 环境回执：`runs/software-panel-v053/environments-v4/`
- 下载协调状态：`runs/software-panel-v053/image-prefetch-supervisor-state.json`
- 全部资格完成后生成：`artifacts/software-panel-v053/environment-admission-v4.json`
- 冻结后生成：`docs/experiments/software-panel-v053-panel.json`
- 完成或暂停后生成：`docs/experiments/software-panel-v053-result-v4.json`（正式面板存在时另有 Markdown 报告）

## GPU 与结论边界

GPU3 已在物理 GPU 0–7 的既定调度名单内；UUID 为 `GPU-7e01944c-768c-2f33-d58e-85d9b62ee185`。本次只读快照显示其空闲 37,028 MiB，低于原有 46,080 MiB 准入门槛，不能据此启动正式驻留；资源会变化，监督器在实际调度时重新观察并等待容量。最多四个 resident，不为当前资源状态降低门槛或改变模型数值配置。

这份记录不提供 200 题完成率、不确定性、40 题波动统计或正式 token 消耗分布。这些结论须等待相应正式回合的真实记录；公共故障和技术未知仍单列，不能按已闭合小子集先行宣称实验完成。
