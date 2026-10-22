# v055 host r4：异步克隆的磁盘预约

## 问题与范围

2026-10-22，释放已完成任务的缓存后，旧 host r3 在一次调度循环中连续派发多项任务。原准入只检查当前文件系统剩余空间是否超过 100 GiB，无法计入已派发但尚未完成的异步 rootfs 克隆。任务可以在读取到相近的 free 值后同时开始占盘，因此“每次派发时 free 合格”不足以保护随后实际剩余空间。

r4 仅修订 host 的新任务派发准入。原 v055 计划、3000 个 slot、六组配置、全局现金账本、scientific solver r3 activation、在途 worker 与评分规则保持原身份。已进入的任务不重放，也不向其发送停止信号。评分和结果收集继续走原路径。

## 预约规则

对已有合格模板，从冻结的 `rootfs_manifest` 读取 `regular_file_bytes` 和 entries 数量，验证该 manifest 的哈希；不扫描文件树，不读取根文件系统 payload，不执行 `du`。同一 receipt SHA 在 coordinator 进程内缓存一次估计。

令 `S` 为 regular_file_bytes，`N` 为 entries 数量，单个生成任务的预约量为：

```
2 × (S + N × 8192 bytes) + 8 GiB
```

两份克隆对应求解 actor 与同步公开测试 actor；每项 8 KiB 提供文件块取整和元数据余量；8 GiB 为工作树、输出与其他临时文件的保守余量。正常公开测试返回后会清理其克隆。异常保留的内容继续占用真实文件系统 free，因此不会因状态终止而从实际已用空间消失。

尚无模板 manifest 的新预热任务，每项预约 128 GiB。该保守估计参考原提取器 32 GiB regular-file 上限，覆盖导出、提取、初始化 clone 和余量。它不是 Docker 导出体积的数学上界，也不是文件系统配额。

每次准入都重新读取当前 free，并扣除旧 v054 与新 v055 中全部 `intent`/`running` generation 的完整预约，以及新 v055 正在运行的 preparation 预约。旧活动任务缺少可用模板大小证据时扣 96 GiB；新 generation 缺少所需模板证据则保持 pending。对端状态无法可靠读取时，也拒绝新派发。

完整预约一直保留到任务离开活动状态，不扣除已经实际写盘的部分。因此已写盘的活动任务会在 free 与预约中被有意重复计入。这会降低高水位下的可用并发，换取对尚未写盘的异步操作的保守处理。

```
新生成：free − 全部活动峰值预约 − 新任务预约 >= 100 GiB
新预热：free − 全部活动峰值预约 − 新任务预约 >= 128 GiB
```

旧 v054 预热服务本次不重新启动。旧模型队列的恢复 host 应使用相同 guard，仅消费已合格模板。

## 两队列协调与持久性

`disk_dispatch_lock()` 使用 `runs/software-benchmark-v055/disk-dispatch-r4.lock` 上的独占 `flock`。两套 coordinator 必须在持有该同一锁时完成以下完整步骤：读取对端最新状态、计算预约、准入判断、写入 durable intent、派发 worker。锁只串行化主机准入和 launch，不串行化模型执行。

新 v055 `launch(kind=generation)` 与 `launch_preparation` 均这样执行。拒绝后不创建 worker、不写入正式运行 intent、不修改 pending slot 身份。继承 tick 的局部计数可能在该次循环虚增一次，但下一 tick 根据 durable 状态重新统计；影响是该轮少派发，不会制造完成或重复运行。某轮首次因容量拒绝新 generation 后，其余 generation 等待下一轮，避免在同一轮按模板大小挑选后面的题目。

`kind=score` 不经过新增磁盘预约门，原预算、CPU、内存和评分并发门继续保留。终止状态释放预约仅改变未来准入计算，不删除该任务任何数据。

本修订解决的是 coordinator 自身“先派发、后异步占盘”的超发问题。它不能禁止其他用户同时写盘，也不能对任意 actor 输出量提供硬配额保证；100/128 GiB 余量及逐次实时观察仍是必要保护。

## 最小 CPU 控制

一次必要控制完成，零模型请求、零评分、零真实 worker、零实验队列写入。覆盖：

- 生成 100 GiB / 预热 128 GiB 门槛的等号及差 1 byte 边界。
- 两份 clone、元数据与工作区余量的字节公式。
- 两队列活动 intent/running 与新 preparation 全部计入；终止任务释放预约。
- 模拟 free 不变的异步派发，200 GiB free、每任务 20 GiB 时，5 个 durable intents 后拒绝第 6 个；评分仍可启动。
- 收集终止结果后允许另一个 pending 任务获得释放的预约。
- 对端元数据异常时，新 slot 保持 pending。
- 真实 flock 对独立 open description 的互斥。

证据：`artifacts/software-benchmark-v055/disk-reservation-host-r4/cpu-control.json`，SHA `e13b1942a72580cc3c1f5a83aaa6dec5b139486487b0b41b6a8e408a24474d47`。

## 封存身份与部署边界

- 模块：`src/proworksim/software_benchmark_queue_native_host_v055_r4.py`，SHA `d58926d21e37f7c87e20aa3aa54778980c5740031ebf70f0a5cd29c4d4166088`。
- 入口：`tools/run_deepseek_queue_native_host_v055_r4.py`，SHA `fbb3c7bc97ca08802b9be9865b39ad315caef2dd314435148b750dbc8d72b417`。
- host revision：`runs/software-benchmark-v055/native-host-revision-r4/revision.json`，SHA `bde55dac5e8e6af81e2739d5fc240be4b80e36ae5bcdc1aee001c7fb89b396df`。
- scientific solver activation 继续为 r3，SHA `99c4aadb7a23be7f96b649dd19bf319b163c26db42e6a83d1c3195ecc853a186`。

部署由主协调端在旧 coordinator 的安全休眠边界停止其进程后接管原 state；旧 worker、GPU 驻留模型、评分与缓存回收不随之停止。实际启动与实时状态证据由本次主协调端另外记录，本文不将 CPU 控制等同于整批实验完成。
