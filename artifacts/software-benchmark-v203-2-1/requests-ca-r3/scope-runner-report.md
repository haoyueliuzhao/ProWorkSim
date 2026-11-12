# Requests2317 CA独立评分范围与执行器

该范围只允许Requests2317的新gold/empty两个控制，key为 `control-ca-r3-psf__requests-2317-{gold,empty}`；不复用r2已消费control身份。BATCH为 `runs/software-benchmark-v203-2-1/requests-ca-r3`，新scope/grader/环境源单独封存，不改在途r2代码、plan、queue、resource claim或service。没有模型/API权限、新volume或新service。

最初讨论过共享父评分lane/lease，主协调任务明确否决后未执行该方案。最终使用已冻结CPU pool的offset64–71，实际两lane为64–67与68–71，和父0–63互斥；所有claim/release仅在本BATCH的resource-claims目录。容器各4CPU/16GiB、host scorer各4GiB并与本容器共享对应4核，两个host直接评分进程由一次fork产生，没有第三个常驻评分监督进程或新unit。

独立上界8CPU/40GiB，和父最坏64CPU/456GiB合计72CPU/496GiB。准入要求实际CPU pool≥72、MemAvailable≥64+496=560GiB、主盘free≥128+父spool32+本批spool8=168GiB。不会以父当前低用量代替其最坏已授权上界，也不会暂停父任务或调整共享主机设置。一次只读准入观察为pool176、MemAvailable912672747520B、disk184456839168B，passed；这是时点观察，执行前还要重新核验。

容器继续network none、drop ALL、no-new-privileges；只有这一个Requests评分任务允许NET_ADMIN/NET_BIND_SERVICE和两个逻辑Host到127.0.0.1的私有映射。CA环境实现由独立环境任务准备，本范围不改测试、gold patch、verify参数、模型可见接口或cash ledger。环境manifest必须如实记录精确SSL CA加载环境适配，不能描述为完全未经适配的原生环境。实际是否gold通过须由后续真实控制结果证明。

scope/runner两项必要CPU控制通过（2 passed in0.16s）：检查新2控制计划、独立CPU集合、联合上界和模型/actor操作拒绝；临时目录执行实际native claim_resource/release_resource，验证20GiB每条host+container预约、最多两条以及所有lease仅属于新临时BATCH。没有消费正式control资源、Docker或API调用。证据scope-runner-cpu-controls.json；复算tests/test_passive_requests_ca_scope_v203_2_1_r3.py。

执行器在评分前、两个进程清理后完整核验本scope与父已冻结source文件身份。每个进程调用实际scorer前限制自身CPU及4GiB地址空间。只有未进入任何评分函数/Docker路径的失败才可凭明确未进入证明释放本claim；已进入评分后的异常必须依靠native真实quiescence证明，不猜测清理成功。正常完成后严格校验两份官方receipt、独立run_id、cleanup、CA前后证据，再生成资格；仅passed字段不能替代证据。

主任务封存：

```bash
PYTHONPATH=src .venv/bin/python -B tools/run_passive_requests_ca_v203_2_1_r3.py --seal
```

主任务真实执行：

```bash
.venv/bin/python -B tools/run_offline_scorer_v096.py tools/run_passive_requests_ca_v203_2_1_r3.py --execute
```

本记录是准备交接，不声明真实控制已经通过。Requests原slot_id/seed/5M的单题首模型续接另行准备，必须同时等待父engineering-gate.passed和本CA qualification passed，不热改父队列，不增加逻辑尝试或150元现金预算。
