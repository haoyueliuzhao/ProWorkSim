# v203.2.1 历史请求证据无损归档准备

当前仅完成代码、只读候选计划和小型合成控制，**没有实际归档或删除历史文件，也没有向/data1写归档**。主任务审阅后负责执行。该工具不在本轮模型运行source闭包，后续存储审阅不会修改已冻结的模型提示、工具、权限、摘要、组织、controller、SDK或评分源码。

固定输入为v066/v064-continuation-r3、v181/full-context-pilot-r1和v169/communication-wave2-r2的 `episodes/<id>/controller-output/model-ledger`。计划包含688个有完整终态与清理证据的回合、151367个JSON，估算原分配块总量258.5907GiB。v066优先，596回合约141.60GiB；v181 56回合约66.21GiB；v169 36回合约50.78GiB仅在前者不足时作为后备。排除项与逐文件lstat在plan.json；估算不是已释放空间，也不是压缩率实验结果。

allowlist包含request/response/tokenize数字序号JSON（tokenize记录本身也是原始请求/返回证据），固定request-capture目录的payload/response/provenance/evidence JSON，以及source-presentation-inputs/source-presentations中的原输入溯源JSON。当前大头是v066的tokenization记录、v181/v169的逐请求完整provenance与source presentation。ledger.json、summary.json、events.jsonl、公测报告、patch、score、SQLite现金账本、模型权重、rootfs及当前12题数据不在allowlist，保持原位。

每个历史回合对应独立tar.zst，唯一输出根为已有普通用户私有目录 `/data1/proworksim-zhuxinrui/passive-history-v203-2-1`，拒绝符号链接和与data0相同的设备。没有新mount、root命令或共享服务改动。执行进程affinity限制在两颗可用CPU，最多两个独立归档并发，每个zstd使用T1。data1保留20GiB底线并先核对单回合最坏输出空间；data0空闲达到180GiB立即停止新归档，在途最多两个回合完成，不为追求全量归档继续释放历史数据。

准入要求：result为closed或已结束technical_unknown，quiescent=true、all_owned_objects_removed=true、cleanup_errors为空、create_result_unknown=false，无retained_objects、无本batch active claim；只普通用户所有、单链接、无扩展属性的regular file，不接受symlink或源子树mount。执行持有该批allocation.lock共享锁以阻止旧分配器新增资源，同时检查本用户cwd/exe/root/fd/maps没有该model-ledger的活跃引用；不会扫描其他用户的私有进程信息。每个文件使用O_NOFOLLOW打开并再次核对inode/dev/size/mtime/ctime；运行前、编码中、全回读验证后和unlink前均保持源身份检查。

SHA256在压缩输入流中计算，不在prepare预先读取大文件。归档写盘fsync后，必须完整解压读回每个成员并匹配原SHA、字节数、uid/gid/mode、纳秒mtime和完整成员集合，才写verified回执与源回合的归档指引；原文件在完整集合再次检查后逐一unlink。坏档、源变动、活跃引用或未证实清理均停止新归档。失败不会被伪装为成功：已创建归档身份不得自动重放，若中途释放遇到异常，可用已验证manifest逐文件恢复，不能覆盖原件或擦除旧失败。

旧 `checked(ref)` 需要原路径文件存在，所以归档后**必须显式restore再运行依赖这些原JSON的历史分析**。这不是透明替换，不建立symlink。单文件恢复会完整读完压缩帧，核对目标SHA与字节，拒绝覆盖任何现有路径，恢复原mode和纳秒mtime，再核对原canonical path/sha/bytes。inode、ctime和atime不承诺保持；实验原信息和原摘要、评分、账本保持。

必要CPU控制3项已通过，详情cpu-controls.json。测试运行真实zstd、完整回读、仅合成文件release、恢复同canonical SHA/mode/mtime、坏档保留原件、源变更拒绝和live FD/active claim拒绝。控制发现restore先设mtime再flush会使mtime变化，已经改为flush后恢复metadata；初始/tmp小于生产20GiB门的拒绝是fixture环境，现显式模拟足够headroom以测试5KiB合成数据，生产门没有降低。不能将这些合成控制写成258GiB历史数据已完成真实归档。

只读prepare已经执行；不要再次运行覆盖计划。经主任务审阅后，普通用户执行：

```bash
.venv/bin/python -B tools/archive_passive_pilot_history_v203_2_1.py --run --workers 2 --target-free-gib 180
```

按原model-ledger相对路径恢复某个文件：

```bash
.venv/bin/python -B tools/archive_passive_pilot_history_v203_2_1.py --restore /data1/proworksim-zhuxinrui/passive-history-v203-2-1/<item-id>/verified.json --member request-0001.json
```

运行进度在本目录progress.json；逐回合verified/released回执在data1对应目录。统计记录释放的原文件分配块，并将共享文件系统实际free作为单独观察，不把其他用户释放/占用空间的变化归因于本项目。
