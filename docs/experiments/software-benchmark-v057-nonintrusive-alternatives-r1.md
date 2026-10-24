# v057 不改共享主机配置的替代办法

日期：2026-10-24。用户要求寻找其他修复方法，并明确不得影响服务器。本轮只查阅项目源码、既有证据和官方文档，做一次普通用户临时解释器验证；没有修改宿主挂载、注册表、网络、系统服务或其他用户进程，没有启动容器、NAT、模型或评分。实验暂停配置保持不变。

## 结论

| 问题 | 可采用的办法 | 当前证据与边界 |
| --- | --- | --- |
| `binfmt_misc`历史注册项无法确认 | 在项目命令中显式调用匹配版本的Python | 项目相关入口已如此实现；一次合成字节码验证通过。无需为了这些入口修改全局注册，但这不证明历史注册项或其他用户任务已恢复。 |
| Requests评分依赖和测试服务不兼容 | 保留固定离线依赖方案，放到独立评测环境继续验证 | 既有r2只让四题中的2931、5414完整gold通过，1921、1766仍未通过。没有新的评分资格。 |
| 当前共享主机上的NAT／挂载风险 | 将剩余评分环境验证移到另一台机器上的专用评测环境 | 建议方案，尚未分配目标机器或运行。当前服务器不新建VM，不尝试新的root或rootless网络路径。 |

## 显式解释器：已有实现，已作最小验证

`binfmt_misc`提供额外格式到解释器的自动分派；注册需要写内核接口。直接执行匹配的解释器不需要为该调用新增格式注册。参见[Linux内核文档](https://docs.kernel.org/admin-guide/binfmt-misc.html)、[Python 3.10命令行文档](https://docs.python.org/3.10/using/cmdline.html)。

静态核查的实际入口：

- `tools/run_native_sdk_controller_v054.sh:27`使用resident Python；v057 runner调用该包装器。
- `src/proworksim/software_benchmark_queue_v056.py:124`起构造显式评分Python命令；v057补评工具只替换评分模块名。
- `tools/run_native_worker_mapped_v056.sh:31`起显式调用bootstrap及worker Python。
- `src/proworksim/software_benchmark_native_rootfs_v054.py:117`要求`linux/amd64`。本轮检查的工具、源码和配置未发现直接执行`.pyc`或调用QEMU跨架构入口；这一范围不代表全服务器软件。

普通用户验证用`/usr/bin/python3.10`生成仅打印固定文本的临时字节码，再由同一解释器显式执行；Python 3.10.12返回预期文本，临时目录正常删除。结果见[interpreter-control.json](../../artifacts/software-benchmark-v057/nonintrusive-alternatives-r1/interpreter-control.json)。没有为了验证重启服务或补写handler。

这种办法只替代格式自动识别，不替代任务隔离。现有运行器中的`unshare/chroot`路径继续受硬暂停约束。它也不会自动恢复其他用户已失败的任务。系统配置文件记录启动时拟注册规则，不能证明事故发生前的实际注册状态；因此没有用重启`systemd-binfmt`重建一个未经确认的全局前态。参见[systemd binfmt.d文档](https://www.freedesktop.org/software/systemd/man/latest/binfmt.d.html)。

## 剩余评分：保留候选，另机验证环境

既有离线控制表明，旧Requests的TLS信任路径、部分`Session.send`行为与历史httpbin服务兼容仍需解决。本轮没有通过关闭证书校验、修改候选CA文件、改官方测试或模拟超时异常来获得通过；现有结果不足以证明离线方案已完全可用。细节沿用[原环境准入记录](software-benchmark-v057-requests-grading-environment-r1.md)。

建议在与当前共享服务器分离的机器上建立专用CPU评测环境：保留四个固定镜像、官方harness、原基线、官方测试和16份已锁定补丁；网络及依赖修订在该环境内完成。当前主机只负责保留已有材料。普通容器仍依赖宿主的内核命名空间、控制组及容器守护进程，不能把换成另一种容器启动方式当成对当前主机完全无影响的证明。参见[Docker安全文档](https://docs.docker.com/engine/security/)。

异机方案仍须先完成同一冻结环境的四个参考修复和四个空补丁控制：全部gold通过、全部空补丁因目标测试失败、结果及退出证据可信后，才可补评原16份候选。直接访问真实httpbin也不能预先保证通过。正式结果使用新的环境身份和run ID，保留原评分，不重跑模型或把环境变化混入旧条件。

最小交接范围为四题的数据／镜像／基线身份、固定评分器及源码、16份原补丁与候选锁、依赖与证书清单和八项控制计划。镜像载荷只有目标环境缺失时才补齐；下载继续遵守固定digest、国内镜像、直连、无代理的既定规则。没有复制宿主系统目录、Docker socket、其他用户数据或主机恢复取证材料。

交接材料从`runs/software-benchmark-v056/queue-r2/state.json`中四个Requests任务的`score.dispatched_request`引用追溯；请求绑定原补丁、候选锁、镜像、数据、基线与评分器。环境资产索引位于`runs/software-benchmark-v057/grading-environment-r1/`；旧控制保留在`environment-admission-r1/`和`environment-admission-r2/`。官方评分可直接接收已有预测补丁，不要求重新生成，见[官方评分说明](https://www.swebench.com/SWE-bench/guides/evaluation/)。

**现有v057入口绑定本机路径、Docker socket和未准入NAT，不能原样搬过去执行。** 远端需要独立的执行适配与环境身份，重新映射路径但保留候选字节／哈希。当前未配置独立执行目标，未进行打包传输、资源申请或远端适配实现。本报告完成的是替代方法及其可行边界核对，不能记为评分环境修复完成；`hold=true`仍有效，16项补评尚未启动。
