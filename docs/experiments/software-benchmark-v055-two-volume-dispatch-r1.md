# v055 双卷任务放置与 v054 主盘计量

## 容量与隔离范围

2026-10-22 的只读观察显示真实`/data1`约994.89 GiB空闲，而
`/data1/zhuxinrui`是指向`/data0/zhuxinrui`的符号链接，沿该别名写入不会增加磁盘容量。
主协调端因此创建独立目录`/data1/proworksim-zhuxinrui/v055-worker-volume-r1`，绑定挂载到
项目内全新的`runs/software-benchmark-v055/secondary-volume-r1`。没有移动或覆盖已运行目录。

注册的主盘`st_dev=66306`、副盘`st_dev=66307`。副盘目录由uid1021/gid1022拥有，采用独立
UUID和SHA绑定marker。注册清单为
`runs/software-benchmark-v055/secondary-volume-admission-r1/volume.json`，SHA为
`8b2b2d00cb78b28abb7ba4c78a4746ae07b8666b6722fc1021fc1b3ea5e58091`。

仅后续DeepSeek生成worker放到副盘；原有生成回合继续使用原目录。Qwen、共享环境cache、
预热、Docker评分、主队列状态、现金ledger和claims继续位于主盘。原回合4 CPU/16 GiB
配置、API并发和预算门槛不改变。副盘的增加不是把主盘空闲数值替换为副盘数值。

## 按实际文件系统分别预约

共同helper为`src/proworksim/software_benchmark_disk_volumes_v055_r1.py`。每个协调器启动时
`configure`固定一个注册清单，此后每次准入重新核对注册SHA、marker SHA与UUID、目录
所有者、source与bind目标inode/device、确切mountinfo中的设备和来源，且两个卷的设备必须
不同。路径被符号链接替换、挂载丢失或设备改变均拒绝新派发，不会静默落回主盘目录。

在原共享磁盘锁内读取两队列状态，先应用已经独立验证的磁盘阶段计量，再按每个活跃worker
目录的实际`st_dev`归属到主盘或副盘。v055使用`generation.directory`，v054使用
`generation.worker_directory`。准备worker及共享cache必须仍在主盘。每个卷只扣除落在自己
卷上的未来增长预约；未知或不一致的放置记录会保守显示到两卷并阻止新派发，不能当作空闲。

Qwen默认目标为主盘，并继续复用原dispatcher、新任务双clone保守估算及旧消费者预热优先
规则。副盘DeepSeek生成保留该卷100 GiB余量，不为主盘预热再额外扣副盘256 GiB；主盘
预热及Qwen仍执行对应主盘余量。DeepSeek原tick中的主盘全局低水位保留，以保护主盘上的
评分、账本和共享基础设施。调度锁持有至durable intent和启动，两个协调器不会同时重复
使用同一份可用容量。

## 必要控制与部署边界

一次必要CPU控制覆盖：真实挂载身份；真实worker目录设备归属；旧/新生成和准备分别记账；
未知目录不释放预约；准备不能搬到副盘；挂载身份失效拒绝派发；Qwen原dispatcher、锁和
策略身份保持。一次真实只读快照`metadata_error=null`，当时主盘8个预约共
95,188,942,359字节，副盘预约为0。这只是部署前观察，不代表后续吞吐或并发已经达到目标。

CPU收据为`runs/software-benchmark-v055/disk-volume-control-r1/receipt.json`，SHA：
`40d73c21c886ed99ab8fac9813cee67612708b7aefbf35f3af00467920bff2a3`。控制中的模型调用、
GPU加载、正式claim、服务修改和真实队列写入均为0。主协调端另有真实跨卷零模型生命周期
控制，DeepSeek新目录路由也由其host修订分别记录。

Qwen入口`tools/run_qwen_disk_volumes_v054_r4.py`仅在独立新host进程内替换磁盘委托，保留
原resource-recovery adoption、原rows和在途worker。有效封存位于
`runs/software-benchmark-v054/disk-volumes-r4a/revision.json`，SHA：
`b4b9bb45c0e38605482de44d591a5b4c74fc6228e1231054a3486a94b6e11004`。
首次未部署的r4封存因虚拟环境的`__file__`使用`/data1`软链接别名、与规范化`/data0`路径
比较失败而被保留；修正仅涉及新入口的路径规范化，随后另建r4a封存，没有重跑正式回合。

有效封存、该初始失败记录和共同CPU收据归档到
`artifacts/software-benchmark-v054/disk-volumes-r4/`与
`artifacts/software-benchmark-v055/disk-volume-control-r1/`。实际接管和任务进入副盘应以各自
planning adoption与worker目录设备记录为准。

当前CPU预算在旧Qwen5个生成、DeepSeek4个评分且预留24 CPU时，允许新生成29个；旧评分
活跃时进一步下降。内存观察允许更多，但不能据此越过CPU预算。新增副盘用于接近已有
CPU允许的并发，不在本修订中提高32个生成的配置上限。
