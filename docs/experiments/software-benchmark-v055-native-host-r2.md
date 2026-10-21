# v055 原生压缩前缀修复的独立 host 接续

此修订为新的 host 入口与单回合 wrapper，不修改原冻结 v055 文件、3000个槽、已经进入的任务或2000元账本。修复的模型接口依据另见 `native-prefix-r2` 的两份真实历史前缀 CPU 复现记录；没有为此重跑已进入任务。

## 接续边界

新的 `NativeHostCoordinator` 继承原队列状态管理、原 worker 观察、评分与预热实现。调度循环来自单独封存的 host hold 模块，唯一新增生成门是在尚未具备 r2 activation 时保留两个 MATCH 组的 pending 槽。REF、PROJECT 以及所有已经进入的 worker 继续运行；hold 不把 pending 当作模型失败，也不宣称主面板完成。

根协调器负责在安全调度边界停止旧协调器、释放 `coordinator.lock`，再启动新入口。独立 generation／score／preparation systemd unit 及其 Actor scope 不随这个交接停止。新入口沿用原 queue root、plan、slot和账本；它在状态中追加 host revision 历史，不重写在途 job。

预封存的 MATCH-only host seal 为 `f997401e3ea08988fa2347e7dfd5f00e41cd3dcf001728cb5af7fa4cd4210424`，根代理先采纳该host暂停新MATCH。随后扩展原生 REF／MATCH 路由；初版native-host seal `e13dba1c7c347e022185f537df6871276718bc174ec8e21cf0898d3ca9c0780c`保留为未采用的交接来源声明。由于实际直接前任已经是MATCH-hold host，另写`revision-after-hold.json`更正交接来源，未改代码。实际采纳的seal为 `82e6b34f20602578ad8324e3d39ff5441c63dafeba70dd090e9587c91a196b4f`，入口如下：

```bash
.venv/bin/python tools/run_deepseek_queue_native_host_v055_r2.py run \
  --revision runs/software-benchmark-v055/native-host-revision-r2/revision-after-hold.json \
  --sha256 82e6b34f20602578ad8324e3d39ff5441c63dafeba70dd090e9587c91a196b4f
```

根代理已经完成两次协调器交接，当时采用的unit为`proworksim-v055-deepseek-six-conditions-native-host-r2.service`。两次`handoff/intent.json`均记录只向协调器发送信号，worker／model／grader信号清单为空；对应`launched.json`记录无任务重放、无模型重载。上述命令是实际部署入口的记录，不应在已有协调器持锁时另启第二份。

## 单独激活原生 r2

activation的固定路径是 `runs/software-benchmark-v055/native-prefix-r2/activation.json`。根代理已发布SHA256 `33455781469b835a68e7fac78d40e5223cf7c051f9dd2b34c52fd9019c80a76a`，运行修订标识为`v055-native-prefix-count-r2`。缺失时只hold MATCH；存在时必须同时满足以下条件，才对未来尚未开始的REF／MATCH生效：

- 独立版本为 `v055-native-solver-activation-r2`，绑定原 plan，arms恰为REF和MATCH，`admitted=true`。
- 引用 `passed=true` 的独立资格记录及全部新增文件的精确SHA。
- 生成入口是新 `run_deepseek_episode_v055_r2.py`，controller入口是新 `run_deepseek_controller_v055_r2.py`。
- 不允许用新的SHA覆盖任何原 frozen dependency。

一旦被采纳，activation内容不能改写或消失。新回合的 `generation.runtime_revision` 保存该activation引用；它也进入实际config的`solver_activation`与source集合。PROJECT继续调用原runner/controller，不进入r2原生接口。

新的episode wrapper仅在自己的独立进程内，精确替换原runner准备启动的controller文件路径。它复用原runner的环境准备、claim、资源、start、监督、静默边界、候选导出、官方请求与清理逻辑；没有添加模型服务、代理或额外工具。每个新native回合另写`solver-routing.json`和结果链接，记录实际路由次数。原条件文件、API flags、采样、上下文、输出及每题预算保持原引用。

## 验证及解释范围

host门控进行了零模型CPU检查。随后额外构造REF、MATCH、PROJECT三种实际job，但mock systemd启动：REF／MATCH的argv选择r2 wrapper并带逐行修订引用，PROJECT保留原runner，科学条件引用不变。该控制没有启动真实服务、申领正式槽或调用模型，回执为 `native-host-revision-r2/routing-cpu-control.json`，SHA `005074c3431583bbbf6b9dfe7c1deac4734bd41b6d31fab5816277ae9bb98d2c`。

接口侧的canonical新module与已通过的staging版本逐字相同；新controller entry仅把同目录导入改为明确的`proworksim`模块导入。其映射资格是`native-prefix-r2/canonical-source-mapping-r1.json`。实际生成仍使用原严格官方counter；只对SDK内部临时、不完整的压缩前缀计数走已验证的新路径。不得把不同运行修订无标识地合并为同一固定实现的完整结果。

网络、host生命周期与初始冻结的小证据已另归档到 `artifacts/software-benchmark-v055/runtime-controls-r1`，共40个文件、139365字节。归档保留原失败记录，未复制rootfs、完整仓库树、权重、tokenizer二进制、完整CA bundle或密钥文件。

后续activation、实际seal以及两次handoff小证据单独归档到`artifacts/software-benchmark-v055/runtime-deployment-r2`，原档不覆盖。


## r3 后续接续与磁盘预热门

2026-10-22，根协调器将前述r2 host接续至`proworksim-v055-deepseek-six-conditions-native-host-r3.service`。新host seal为`f36e5657bee37b679ed0a105f9ceab10151126c2d52b722073cc3f8f29c66b9b`，activation为`99c4aadb7a23be7f96b649dd19bf319b163c26db42e6a83d1c3195ecc853a186`，均在`runs/software-benchmark-v055/native-host-revision-r3`。未来REF／MATCH采用单独资格通过的原生r3入口，补回SDK对话转为provider消息时遗漏的原始thinking字段；PROJECT维持r1，既有回合继续原job。接口依据见r3独立文档与两条历史失败事件的零API CPU控制，不能把修订前异常重标为正常模型失败。

同一host增加一个准备吞吐门：六个新条件都尚未进入、且模板qualified的不同任务计为未使用就绪库存；该库存与在途preparer数之和达到8时不再创建新preparer，已有preparer继续收口。实施前只读观察为190个未使用就绪任务和2个在途preparer，故立即停止新增预热，允许库存供正常32路生成消费。此门不减少生成／评分并发上限，也不取消100GiB生成、128GiB预热磁盘底线。原v054独立预热器另有限制：1 worker、最多2个由其准备而尚未消费的任务；01:17其状态为waiting。

r3复用已封存r2的tick/launch/collect方法，只有新activation验证与preparation override不同。被库存门拒绝的preparation在继承tick内部仍短暂计入当次尝试数，至多减少这一tick的预热派发，不会超派；实际worker计数在下个tick重新从状态读取。每个新增native回合继续记录`generation.runtime_revision`，不能仅凭继承job序列化的r2版本标签推断solver版本。

唯一新增CPU检查模拟三种真实job配置的派发，验证REF／MATCH路由r3、PROJECT保留旧入口，并检验库存8、7+1、7+0、0+2四个边界；未启动服务、未申领正式slot、未新增模型请求。回执SHA为`811fd2fc543d6222db6fe956477149d3c71a0781ad6ec15a1e1f8186db980a83`。交接仅停止协调器，回执记录0回合重放、0模型重载；activation、seal、CPU控制与handoff五份小证据归档在`artifacts/software-benchmark-v055/runtime-deployment-r3`。
