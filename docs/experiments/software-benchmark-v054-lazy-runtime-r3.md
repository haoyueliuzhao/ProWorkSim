# v054：最终 Git 初态、逐题按需初始化与安全回收

日期：2026-10-21，Asia/Shanghai。本报告收尾 r3／r3.1 基线接入、逐题 native 资格和公开输出读取／临时副本回收；没有启动正式模型、训练或重新执行已闭合的官方评分／完整 UID 控制。

## 1. 为什么最终初态不沿用 r2 单根提交

公开入口检查观察到：只保留新造单根 Git 提交会令部分库的运行版本变化，例如 Django 的开发时间标记和 Matplotlib 的版本号。文件 tree 同值不足以证明测试环境语义完全一致。

最终映射保留原官方 setup HEAD、它的合法祖先闭包，以及仅指向数据 base 祖先的合法 tags；重新建立只包含该闭包的对象数据库，删除未来分支、无关 refs、reflog 和不可达对象。Gitlink 的父 OID、公开子树及合法子库历史按同一原则保留。实际原镜像／Actor 的 package version 必须相同。

完整 500 题的最终清单由 `artifacts/software-benchmark-v054/actor/actor-baseline-index-r3.json` 冻结。最终库存为 459 条 r3、41 条 r3.1；r2 的 500 条结构检查保留为中间阶段，不再作为最终版本语义就绪的依据。

## 2. 历史格式诊断保持真实，不伪装成 fsck 为零

合法历史中有七个精确已知对象：Flask 五个 tree、scikit-learn 一个 tree 含旧式零填充 file mode；Requests 一个 commit 含历史 badTimezone。它们来自固定官方镜像的同一 Git OID 和原始对象字节，不是 Actor 新产生的对象错误。

例外策略为 `config/v054-historical-git-format-exceptions-r31.json`，原字节 SHA：

`43f5dd872f7b6b3eb6ebb48441758daef2c590e40e62f971a5983ad05e9c992c`

新共同验证器只接受精确命中该策略的 object ID／type、原始对象 SHA、诊断代码和整行文本；还要求该题原官方 image 绑定、源诊断一致、对象在合法闭包内、目标对象 hash 核验通过。实际规范诊断行数组必须恰好等于这些例外行，不能含额外或重复行。该数组来自已执行策略的全行相等检查，回执明确标注规范化依据，未假称又捕获了一次原始 stderr。

Requests 的 actual full fsck return code **4 原样保留**，connectivity 为 0，闭包／refs／无不可达对象／运行版本等其他门保持。码 6、未知诊断或对象 hash 不同均拒绝。warnings-only 的实际码为 0。没有全局关闭某类 fsck 检查，也没有改写历史 commit／tree OID。

## 3. scorer r5 与此前真实官方评分的关系

新增 `software_benchmark_scorer_r5_v054.py` 使用最终 r3／r3.1 映射门。官方 5.0.2 的 patch apply、eval script、parser 和 resolved 判定不改；原官方评分镜像也不改。r4 的真实空候选官方评分结果和旧 r3 的 technical_unknown 均保留。

r5 安装身份还固定共同验证器、精确历史格式策略及三份原官方对象审计。正式请求仍使用 `baseline_mapping`、REF／MATCH 的 `native_candidate_lock`，或 PROJECT 原 code／delivery 双端点锁。不同映射／软件身份继续进入独立 run ID。

固定 manifest：`artifacts/software-benchmark-v054/scorer/installation-manifest-r5.json`，SHA：

`02639feec982a3b814fa5c9d317539258ae89f42f4c632a50a11c2a20691e5b2`

必要验证：实际首题 r3 映射及版本／未来 refs／HEAD 漂移拒绝控制 1 passed（0.06 秒）；新增精确历史错误／额外行／对象漂移／错误码拒绝控制 1 passed（0.06 秒）。随后只读验证 Astropy、Flask、Requests、scikit-learn 四份实际映射均通过，其中 Requests 保持 raw fsck=4。未重新运行官方测试或旧 UID／资源控制。

## 4. 逐题按需准备在正式回合领取前完成

新增 `ensure_native_instance(...)` 与 `tools/prepare_native_instance_v054.py`。所有 500 题都可使用同一入口，无需预先额外展开 500 份多 GiB 根目录。

输入包括固定公开 500 题投影、该题最终 mapping 的完整文件引用、cache root、控制标准库及私有 Docker socket。返回四个**绝对路径字符串**：

`rootfs_environment`、`rootfs_manifest`、`environment`、`qualification`。

流程如下：

1. 核对公开任务集合、mapping 的最终 schema／完整身份／实际版本证明；按 instance ID＋mapping SHA 创建独占 cache。
2. 从该题已准入的派生 Actor image 安全导出，使用已经验证的算法保留原数字 UID／GID，不安装额外模型或 SDK 包到任务根。
3. 核对旧真实控制中 UID／worker／resource **原始源码引用仍逐字匹配**。这次实际首题已通过该检查；没有把旧 SHA 改成新文件，也不靠推测继承资格。
4. 在该题新模板的独立临时 clone 内启动真实官方 worker。仅检查该题实际 public Python、目标 package 的运行版本及其 `/testbed` 来源、官方 setup HEAD／tree、UID 0 运行身份；这是新实例初始化，不重复整套工具／UID／攻击面控制。
5. 官方终端关闭、宿主 service 停止并 reap、实际 cgroup 空后，记录该题资格，将模板 `native_real_task_control_passed=true`。保留 receipt／manifest，删除该次初始化的多 GiB 临时 clone。
6. 已合格 cache 只检查固定引用后复用；每个正式 episode／公测仍获取独立完整 clone。未闭合的准备目录保留，不在下一次调用时自动覆盖或重新取样。

入口必须在 `Episode.claim`、GPU lease 和模型加载之前调用。失败记录为 `preparation_not_ready`、`slot_claimed=false`、`model_calls=0`，不计为模型失败，也不替换任务。运行器／配置工厂负责这一调用位置，见独立 runner 报告。

## 5. 实际首题一站式结果

此前启动的首题控制在会话中断期间继续运行，**09:54 CST 已自然完成**；恢复后只读其原输出，没有重启。

cache：

`runs/software-benchmark-v054/native-lazy-r3/astropy__astropy-12907/843dcc65484d2d05/`

`lazy-preparation.json` 为 qualified；正式 slot 和模型调用均 0。实际解释器为 `/opt/miniconda3/envs/testbed/bin/python`，package version 为 `5.1.dev623+gd16bfe05a.d20260815`，HEAD 为 `d350420dae50c80ca33b845734c31428d62af0a8`，tree 为 `507f65ecab7408b900788d937fdad20e5b4e87b8`。同题 r3 的模板资格门已打开，临时初始化副本已经在 quiescence 后移除，缓存模板保留。

qualification receipt SHA：

`f5e38e4c727c1b78ca016e744372b39b1d1a230a90b78a61bdc5c93e2b56a36a`

这证明实际按需链路闭合；不是声称全部 500 份 native rootfs 已展开或所有仓库测试已经执行。

## 6. 公开测试输出与一次性 clone 的安全边界

新增 `software_benchmark_rootfs_io_v054.py`：公开 stdout／stderr 从 rootfd 逐层以 `O_DIRECTORY|O_NOFOLLOW` 定位，最终文件使用 `O_NOFOLLOW|O_NONBLOCK` 并以 fstat 要求 regular file。Actor 不能把 stdout 或其父目录换成指向宿主文件的链接，让可信宿主读取后泄露到工具反馈；FIFO 也不能造成阻塞读取。

每条流上限明确为 16 MiB。超限、链接或非普通文件均是技术异常，保留现场，不截断后伪装成完整反馈。这个上限是完整输出传输的运行限额，不是删除源码或缩减任务文件的规则。

`cleanup_episode_rootfs(...)` 只接受本项目 episode 下的一份 clone，核对 manifest 中 `prepared_root` 和 `cloned_from_manifest_sha256`，拒绝删除缓存模板。要求正式 quiescence 及 `outer_launcher_reaped=true`，再次确认已登记 cgroup 为空，并检查 stdout／stderr／输入树或已锁候选等保留证据的完整 hash；保留证据必须位于将删除的 rootfs 外。

随后仅由固定 stdlib-only sudo helper 删除这一份根目录，不修改原 UID helper 或模型监控器源码。失败未锁候选、读取溢出或技术未知现场不能因节省空间而被静默清除。

两个必要合成控制通过（2 passed，0.08 秒）：完整有界读、父／末级 symlink 与 FIFO 拒绝；只删除 quiet clone，同时保留外部链接目标和宿主证据。没有重复三组完整控制。

稳定汇总为 `artifacts/software-benchmark-v054/native-environment/lazy-runtime-r3.json`。模型容量监控器已由根代理独立封源并运行；本项工作未修改其已冻结的 owner／runtime／GPU lease 文件。
