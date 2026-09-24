# 真实模型工作人员

`report-deepseek.json`为一个模型作者＋固定规则审阅者；`sql-deepseek.json`为公开项目群中的一个模型P1执行者，其他角色固定，先由P0通过真实SQL/提交/发布产生资料起点。它们使用显式单动作JSON协议及latest_observation上下文选择，不暗中提供领域答案。运行需要`.env`里的DEEPSEEK_API_KEY。

```bash
.venv/bin/proworksim scenario-build runs/model-report-demo --spec examples/model-v11/report-deepseek.json
.venv/bin/proworksim staff-run runs/model-report-demo --output runs/model-report-demo.json
.venv/bin/proworksim episode-assess runs/model-report-demo --experience runs/model-report-demo.json --output runs/model-report-grade.json
```

新建目录/输出文件；SQL场景可替换spec。模型失败、预算停止或机构接受均不能直接读成独立质量通过。每个模型角色有最多120次决策、150次attempt、500000累计token、8192单次输出及1USD保守计费上限；请求预留、上下文和环境机会可能更早停止。连续运行必须提供最新checkpoint，会另建episode并保留上一段结果；不把后续成功回填。

`development-protocol.json`固定最初36个开发episode（full_history，六场景×两后端×三次），原结果保留。`prepared-project-protocol.json`为之后三项独立接口诊断，角色起点和context条件不同，不替换原失败。`two-workers-protocol.json`单列模型作者＋模型审阅者，反馈环境不同。native和JSON pilot协议保留各自原配置，不能把模拟transport测试算进模型样本。

本地Qwen使用已有只读权重目录和独立GPU HTTP服务。以本机训练环境为例：

```bash
CUDA_VISIBLE_DEVICES=7 PYTHONPATH=src .train-venv/bin/python -m proworksim.local_model_service \
  --model /path/to/Qwen2.5-7B-Instruct --revision ACTUAL_REVISION \
  --output runs/qwen-service-new --port 18761 --max-batch 3
```

协议中的模型路径/revision/manifest须与实际文件一致；服务器仅监听127.0.0.1，记录共享GPU信息与真实token轨迹。不得把其他项目的既有服务自动当成同权重版本。DeepSeek调用与本地参数训练分别记录。
