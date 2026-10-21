# v054 r2：官方评分初态与三组共同 Actor 初态

本修订解决真实官方镜像与旧准入判据不一致的问题。它保留全部500题、既定官方镜像digest和官方评分器；另为REF、MATCH和PROJECT准备相同的Actor派生镜像。没有启动模型回合、训练或生成新任务成绩。

## 为什么旧判据拦住229题

截至2026-10-21上午，1195个去重镜像资产已经全部完成SHA验证，共131,932,243,128 bytes。旧流水线已加载229个镜像，但旧判据要求`HEAD == dataset base_commit`，并将所有base之后的commit和非零Git fsck直接拦下。229份旧回执保持原状，不能将本次新规则回填成旧预检成功。

固定首Astropy和首Django的定向只读审计得到：

| 证据 | astropy__astropy-12907 | django__django-10097 |
| --- | --- | --- |
| 官方image HEAD | `d350420dae50c80ca33b845734c31428d62af0a8` | `a51eeca2111c21fc73455e3e248dc2165387880d` |
| HEAD来源 | 作者及提交者为SWE-bench，邮箱setup@swebench.com，父commit是dataset base | 相同关系 |
| 与base的tree关系 | 不同；1861个路径改变模式，其中仅pyproject.toml内容改变 | tree完全同值 |
| 实际内容变化 | build-system的setuptools增加`==68.0.0`版本约束 | 无 |
| 工作树 | 干净 | 干净 |
| fsck完整错误 | `refs/remotes/origin/HEAD`为全0无效指针 | 同一错误 |

Astropy的其余1860个路径仅由100644变为100755。已经安装的官方SWE-bench 5.0.2 `image_builder/docker_utils.py` 中，`git_clone_timesafe`明确执行仓库权限调整。官方[v4.1.0构建规格](https://github.com/SWE-bench/SWE-bench/blob/v4.1.0/swebench/harness/constants/python.py#L597)也包含这条Astropy构建前依赖约束。该公开源码和镜像中的实际差异共同支持“既有构建适配”的解释；这里没有读取参考修复或隐藏测试来选择保留哪些文件，也没有声称已重现整个官方Dockerfile。

实际安装的5.0.2评分入口在启动官方镜像后直接应用候选补丁；它不先将整个仓库重置为dataset base。首题评分脚本中的base checkout只针对其测试文件，属于可信评分侧。相关评分侧核对由评分分支独立完成，未将脚本内容传入Actor构建。因而若把求解端整个仓库强行重置回base，反而会移除官方构建依赖约束，并使候选差分基线与实际评分初态不同。

审计原件位于`runs/software-benchmark-v054/images/baseline-audit-r1/`，包括完整fsck错误、commit身份、差异计数、唯一pyproject差异及官方config构建history。原镜像的Git错误并不自动证明含有答案；旧严格判据也不能直接放宽后继续称其历史已隔离。

## 冻结的新规则

规则保存在`config/v054-actor-baseline-r2.json`，实现为`tools/verified_actor_baseline_v054.py`。策略SHA同时覆盖配置原始字节与实际容器构建程序，首次冻结值为`9de8a08584ce3737730636abe48262d085d05d8189af9d649bc4a3fcc9cdc976`。

1. 只使用原题不可变官方镜像。要求官方工作树干净；若HEAD不同于dataset base，必须是直接以base为唯一父commit、署名为SWE-bench/setup的已识别setup提交。未知关系保留原题并列技术未定。
2. 保留官方setup HEAD的完整tracked tree及现有ignored构建物，包括文件内容、模式和符号链接。不会根据参考补丁、测试成绩或疑似相关文件过滤代码。
3. 删除Actor派生容器内整个继承的`.git`，再以原tracked路径重建一个确定性的单根commit。新tree必须精确等于官方setup tree；原对象库、旧refs、reflog、远端、hooks和index均不复制。
4. 实际核对严格fsck成功、对象库只含一个commit、新工作树干净、旧官方HEAD和dataset base对象均不可读取，以及ignored构建物的路径清单保持不变。原base仅保留在可信侧身份映射中，不能假称新Actor HEAD就是原base。
5. 仅处理明确的目标包路径：删除已发现的目标发行包Conda缓存；对指定Conda环境中位于checkout之外的目标import包，将其替换为指向本题公开checkout对应模块的符号链接。没有盲删整个依赖缓存，也没有将外部包源码复制进任务树。所有实际动作逐题记录，残留目标路径阻止准入。
6. 核对官方testbed环境Python的明确路径及可执行身份；不安装新SDK依赖，不挂宿主目录或Docker socket，不运行隐藏评分。完整任务测试成功不是这一初态检查的条件，公开测试与官方评分接缝另报。

派生镜像仅用于求解端。官方评分镜像及其config ID没有改变。候选的内容差分相对于实际官方setup树导出，dataset base仍承担任务和评分身份。REF、MATCH、PROJECT使用完全相同的派生Actor初态；这属于三组共同的求解环境准备，并非PROJECT额外工具能力或接口收益。

去除全部Git历史也去除了原本可能合法的祖先查询能力。这是明确冻结的共同信息限制，因此不能宣称与允许完整历史的外部论文运行条件完全相同。若版本推断依赖Git历史，其影响也属于这一共同准备条件；不能隐去后将差异全部归因于模型或项目接口。

## 映射与运行边界

逐题回执保存在：

```text
runs/software-benchmark-v054/images/actor-admission-r2/instances/<instance_id>.json
runs/software-benchmark-v054/images/actor-admission-r2/configs/<config_digest>.json
runs/software-benchmark-v054/images/actor-admission-r2/state.json
```

主要字段为`official_image_id`、`official_manifest_digest`、`dataset_base`、`base_tree`、`official_head`、`official_tree`、`actor_image_id`、`actor_config_blob`、`actor_head`、`actor_tree`、`policy_sha256`和`public_python`。config原始字节从专用Docker的不可变config存储只读取得，并核对其SHA等于Actor image ID；没有重新保存或hash整套镜像层。

每个真实准备容器最多4 CPU、16 GiB，禁网络、移除全部capabilities并启用no-new-privileges；全量最多8个并行容器。仅访问本项目专用Docker。所有未知错误保留题目身份，不换题，不记作模型失败。

官方镜像离线加载由独立`tools/load_verified_images_offline_v054.py`以最多4路进行。它只复用1195个现有完整SHA回执和文件stat绑定，不重新下载或hash大型blob，也不重复执行旧预检；500个原题身份始终保留。

## 首题控制与实际进展

首Astropy和首Django的容器内初态与隔离检查已通过。首次发布阶段Docker commit布尔参数拼写错误导致两份技术失败；修正后commit实际成功，但Docker29把弃用提示写入stdout，导致调用方第一次把提示文本也当作image ID。随后仅核对并复用已生成的两个派生image，修正输出解析，没有第三次重建容器。原失败回执保留于`prior-attempts/`。

Astropy派生image为`sha256:b3b91f6a3e1d4a99e72fb3ff225a8e167d29716e2702bcffb471c4efbd6a1728`，新根commit为`e572af97883068a33564cf787411074705963f7b`；新tree严格等于官方setup tree `507f65ecab7408b900788d937fdad20e5b4e87b8`。Django派生image为`sha256:a8df10d73d326daa01530166fcd259a897ec4abb5f9c6d77b8d35b04c26b8ad0`，新根commit为`0860f6220873f71d2c9c4b066015109f8e001391`，tree保持`d4eb2e5cc340316fa277528044ee35d1ac473dc5`。

全500准入由`proworksim-v054-actor-admission-r2.service`执行，首2题成功回执复用，其余题只在官方镜像离线加载后执行。随后仅处理下述7个实际结构性例外，其余已通过任务没有重跑。

## Gitlink子模块和冗余构建副本

六个早期Astropy任务（7166、7336、7606、7671、8707、8872）的`astropy_helpers`为已经初始化的Git子模块，父索引模式为160000。将它当普通目录交给`update-index`失败，旧回执保留。新分支为`config/v054-actor-gitlinks-r1.json`及`tools/verified_actor_gitlinks_v054.py`：

- 完整保留公开子模块工作树、ignored构建物及父树gitlink OID。
- 删除继承的子模块对象库；只重建其当前原始commit及对应tree/blob对象，并用shallow边界截断父历史。原始当前commit的OID不变，子模块对象库实际只剩1个commit，严格fsck成功。
- 父仓库仍按普通r2规则新建单根commit，父tree精确等于官方setup tree。没有把子模块flatten之后冒称Git tree相同。
- 此分支等待原8并发批次结束后才以6并发执行，没有超出准备容器并发上限。

子模块能力另由`software_benchmark_gitlinks_v054.py`贯穿完整文件快照、来源provider及唯一候选导出。任何层级的`.git`控制元数据被排除，公开子模块文件仍完整可读写。父gitlink的path/OID单独绑定；候选补丁编码用的flatten tree明确标为encoding，不作为官方父Git tree报告。

唯一新增合成控制使用真实父repo及初始化子repo，覆盖子模块内部文本变更、执行位、删除和新增二进制文件。在父目录执行与官方相同的工作树`git apply --binary`后，完整文件树与锁定候选精确一致，父gitlink OID保持不变。第一次执行通过（1 passed，0.15秒）。随后核对实际PROJECT完整候选物化流程，发现其清空公开工作树会一并移除nested Git控制目录；现先暂存已准入子模块的控制目录，替换完整公开payload后再恢复，不将控制元数据放入模型候选。对这一必要改动扩充同一个控制，第二次通过（1 passed，0.22秒），同时验证子模块HEAD和完整payload保持；[两次执行记录](../../artifacts/software-benchmark-v054/actor/gitlink-candidate-control-r2.json)均保留，没有重跑无关17项控制。修改、新建、删除或移动gitlink身份本身仍明确报`deployment_limit`，不能将无法表达的元数据操作静默丢弃；正常父仓库修改和已有子模块内部文件修改均可导出。

最后的`psf__requests-1142`只有未跟踪的`build/lib/requests`目录，tracked/index均无变化。单独分支`config/v054-actor-requests-buildcopy-r1.json`要求所有未跟踪项都属于这个明确目录，并逐一与公开`/testbed/requests`原文件比较。实际65个文件全部逐字节同值，才移除这份冗余副本及空父目录；真正源码、其他构建物和官方评分镜像没有改变。该题新tracked tree同样精确等于官方setup tree，原失败回执保留。

这两个分支均依据模型运行前的实际环境结构决定，不根据得分或参考修复选择规则。每道题的三组使用同一分支和同一派生镜像。

## 09:33收尾结果与解释范围

2026-10-21 09:33:10 CST的固定回执为 [actor-baseline-completion-r2.json](../../artifacts/software-benchmark-v054/actor/actor-baseline-completion-r2.json)，完整500题索引为 [actor-baseline-index-r2.json](../../artifacts/software-benchmark-v054/actor/actor-baseline-index-r2.json)，SHA256 `7b9f9943097a506b7b21b3c210ed3f3bca3f65ef2e8a07aff952dccfcae90efc`，1,155,750 bytes。

| 结果 | 实际数量 |
| --- | --- |
| 官方镜像加载 | 500/500 |
| 共同Actor初态准入 | 500/500 |
| 普通r2分支 | 493 |
| 保留官方gitlink的子模块分支 | 6 |
| 已证明同值的Requests构建副本分支 | 1 |
| Actor tracked tree等于对应官方setup tree | 500/500 |
| 父Git单根、严格fsck通过 | 500/500 |
| 发生定向目标包路径处理的任务 | 27 |
| 删除目标发行包Conda缓存项 | 54 |
| 将外部目标import副本指回本题公开源码 | 16 |
| 本次准备新增模型调用、下载、整层重hash | 均为0 |

三个冻结策略SHA依次为`9de8a08584ce3737730636abe48262d085d05d8189af9d649bc4a3fcc9cdc976`、`6bfff50a57878236e331ec74c581fb28554ef5f2434ab3ce55f73928b780837a`及`b6a57a1a941240e3d61e50ec4cca0227ccf7cfd8d099fad266dffadfee463977`。逐题索引记录实际策略、官方与派生image/config ID、全部基线映射、明确Python、子模块证据及定向移除动作。

这里完成的是官方资产加载和三组共同的CPU Actor初态准入。定向包路径检查不代表对整个文件系统的无泄露证明。原生工具、PROJECT公开测试、官方评分接缝、模型容量及正式运行授权仍是独立门；不能将本报告的500/500改写成三组正式模型实验已经通过。
