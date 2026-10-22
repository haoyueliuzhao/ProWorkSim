# v053 已结束镜像下载中间文件回收

2026-10-22，用户授权进一步清理或压缩无用历史数据以保障当前实验。此次只清理旧 v053
镜像下载与装载的中间 payload，没有再次处理前一批 v054 的597个下载层，也没有删除
模型、Docker image、Docker内部存储、实验结果、补丁或评分。

## 精确范围与结果

删除计划覆盖以下三个已经完成装载的历史批次中的唯一普通文件：

- `runs/software-panel-v053/prefetch-ranks09-24-v1/blobs/`：已验证的大型压缩层。
- `runs/software-panel-v053/prefetch-ranks25-32-v1/blobs/`：已验证的大型压缩层。
- `runs/software-panel-v053/parallel-images/blobs/`：已验证的大型压缩层，以及该批次的
  `parallel-images/eight-original-images.docker.tar` 标准装载归档。

共删除 **35个文件**，payload合计 **24,277,098,967字节**。删除前文件stat记录的已分配块
总量为 **24,277,282,816字节，约22.61 GiB**。这是被删文件的分配量，不以并发实验期间
文件系统空闲空间差值代替独立测量。

两个具有额外硬链接的压缩层被明确排除，避免把仍被其他链接引用的块误算成已释放空间。
所有小型配置、manifest、下载SHA证明、装载收据、日志和失败记录均保留。当前
`native-binding-control/r3` 的runtime及stdlib、共享合格模板和运行中环境均未改动。

## 删除依据与边界

三个批次的原 `docker-load-receipt.json` 均为passed，并记录固定镜像身份相符。执行前
确认这批 **32个唯一image ID**仍存在于当前项目Docker。当前Qwen原绑定、GPU6 kernel-r6
和DeepSeek的直接文件冻结集合不引用所选payload。未来任务运行使用已有Docker image，
不需要保留已经完成装载的这些下载副本。

压缩层直接使用既有SHA和stat证明，不重新读取约24GB数据做冗余哈希。装载tar使用原
构建时的SHA证明、记录大小和本次封存后的stat。删除模式必须输入精确计划SHA；执行前
再次检查文件身份、证明材料、当前image ID和冻结依赖，并排除已知历史下载/装载进程及
打开目标payload的本项目或本用户进程。操作持有独立回收锁及目标文件独占锁。

操作没有停止、重启或重载任何服务。所删中间副本未来若需重新建立，可以根据保留的固定
registry摘要和manifest重新下载、重新构造装载tar；此回收不保证离线下载副本仍可直接复用。
原下载完成证明作为历史事实保留，本次回收收据标明对应payload已退役。

## 工具与审计材料

- 工具：`tools/reclaim_legacy_image_downloads_v053.py`，复用先前清理工具中的只读引用与冻结
  文件集合检查，不修改任何已封存host/helper。
- 计划：`runs/software-panel-v053/historical-download-retirement-r1/plan.json`
- 计划SHA：`f91e55d3c6fd4d34b6d63803df256602a1f2a73ff2f151f15168b8f0f0ce8395`
- 完成收据：同目录 `completion.json`
- 完成SHA：`5081459600f7dc9c980f23e21aec8eea7d516e49c888520a1a0eb48e734ae215`

计划、执行前意图证据和完成收据原字节归档在
`artifacts/software-benchmark-v054/legacy-download-retirement-r1/`。
回收实际执行成功并通过自动审批；模型调用和服务信号均为零。
