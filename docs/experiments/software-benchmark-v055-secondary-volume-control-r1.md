# v055 data1副盘的单例零模型生命周期控制

本控制验证真实data1工作区经项目内bind路径运行现有v055环境生命周期。物理源为`/data1/proworksim-zhuxinrui/v055-worker-volume-r1`，项目可见路径为`runs/software-benchmark-v055/secondary-volume-r1`。原有数据没有迁移。挂载由独立部署步骤创建，其回执为`runs/software-benchmark-v055/secondary-volume-admission-r1/volume.json`（SHA-256 `8b2b2d00cb78b28abb7ba4c78a4746ae07b8666b6722fc1021fc1b3ea5e58091`）。

新工具`tools/check_secondary_volume_v055_r1.py`在专用检查进程复用原`check_deepseek_host_lifecycle_v055.py`；原checker和所有冻结运行源码均未修改。它只选择MATCH单例：真实模板clone、原生SDK以本地程序响应执行think与finish、导出唯一候选、核对评分请求、证明写进程静止、执行原安全cleanup。网络由原fixture禁止，不使用真实API key或共享费用账本，不启动正式评分。

原checker声明MATCH与PROJECT两个本地fixture槽；新wrapper只执行MATCH一个，回执明确PROJECT未执行、不产生测试结论。独立授权和claims写在本control目录，不占任何正式3000槽；模板原缓存锁在控制期间保持共享锁，避免读模板时被回收。源配置选已准备的django-13343，而非已经回收rootfs的旧slot1模板，无下载。

实际通过一次完整控制，未重复PROJECT或接口全量资格。clone后直接记录设备号：data0为66306，data1为66307，目标rootfs确在data1。bind两端device与inode一致，owner为1021:1022、模式0700，项目路径无符号链接重定向；控制结束后rootfs已经删除，结果、候选和环境metadata仍留存。程序响应2条、真实API调用0、网络尝试0、正式槽claim0、官方grader调用0、GPU加载0。

主回执`runs/software-benchmark-v055/secondary-volume-r1/host-lifecycle-match-r1/volume-control.json` SHA-256为`c559206c45b1ae7f113ded546ee55567e5c1b26424da8b4fd460869b9b249f7e`。小型证据归档`artifacts/software-benchmark-v055/secondary-volume-control-r1/`，共8份文件、26301字节，另有索引；没有复制rootfs、完整源代码树、参考答案、模型轨迹或大型rootfs清单。

静态路径核对与这一次实际运行共同说明：冻结runner、numeric-owner clone helper和静止cleanup允许这个项目内bind目标跨设备工作。它们并不要求源和目的st_dev相同。此结论只覆盖副盘文件系统路径及生命周期，不重新宣称模型/API资格或正式任务表现，也不代表尚未部署的多盘调度已经上线。
