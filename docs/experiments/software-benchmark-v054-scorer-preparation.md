# v054：官方评分器的实际准备与本地执行边界

日期：2026-10-20，Asia/Shanghai。用户授权本次“准备好数据与环境”；本文记录评分软件和真实 500 题评分规格的准备，不记录模型能力成绩。正式模型回合仍为 0。

## 1. 实际准备结果

在新的 `runs/software-benchmark-v054/scorer-venv/` 内安装了官方 **swebench 5.0.2**，使用已迁移的私有 CPU Python 3.12.3。没有改写 `runs/v016-sdk/resident-venv/`，也没有升级旧 v053 的 4.1.0 评分环境。

目标 wheel 为 `swebench-5.0.2-py3-none-any.whl`，142,715 bytes，SHA256：

`b7f0416a1e686eca22c2f749b5f816685a202835032f6683080e2b53545bbb62`

本次从 v053 的已有 pip HTTP 缓存找到该完整 wheel；完整 SHA 与预先核实的官方发布身份一致。安装使用 `--no-index --no-deps` 本地路径。此前两次清华镜像的包元数据请求均返回没有匹配分发，没有下载包 payload；发现缓存后没有继续网络下载，没有原站或代理回退。缓存最初来源属于旧 v053 的历史下载，不能改写成“本轮从国内镜像新下载”。

依赖复用采用两层：

1. 把旧 v053 独立 harness 的 59 个顶层依赖条目复制到新目录，排除其 `swebench`、4.1.0 distribution 元数据和旧 `.pth`；没有对旧目录做卸载或安装。
2. 新环境的 `.pth` 只读使用原 resident 的公共依赖路径；新环境自己的包在导入顺序上优先。完整有效版本清单包含 197 个 distribution 名称。评分前重新核对有效版本与已冻结 manifest，防止后续外部环境变化被隐式混入。

这是经过实际评分入口导入和本地规格检查的环境，不是面向所有开发／推理 extras 的安装，也不宣称全局 `pip check` 或模型运行验证通过。

已完成的实际 CPU 检查：

| 检查 | 结果 |
| --- | --- |
| 官方 `run_evaluation`、`grading`、`utils` 的真实导入 | 通过 |
| 安装后的全部 65 个官方 `.py` 文件与目标 wheel 内容逐项比较 | 完全一致 |
| 固定可信 JSON 的 500 行均调用官方 `make_test_spec` | 500／500 通过 |
| 每项 parser 已注册、`eval_type` 有效、F2P/P2P 列表保持原值 | 500／500 通过 |
| 需要远端下载的 `image_assets` | 0 项 |
| 合成日志：两个必需测试都通过 | 官方 resolved 为 true |
| 合成日志：F2P 失败、P2P 通过 | 官方 resolved 为 false |
| 合成日志：退出码 0，但没有测试执行证据 | 未被判为 resolved，`patch_successfully_applied` 为 false |
| 两项新增 pytest：完整评分身份隔离、本地 Docker 边界 | 2 passed |
| 新模块、准备工具、测试的 Ruff | 通过 |
| 私有 CPU 内实际 Docker CLI `--version` | Docker 29.3.1，可执行 |

实际 500 题规格控制在 **22:16:05–22:16:08** 完成。网络尝试 0，容器 0，基准测试执行 0，模型调用 0，GPU 启动 0；唯一子进程是 `docker --version`。三份合成日志只含人工测试标识，均不是 Verified 任务结果。

因此，**评分软件及全部 500 题的数据接口已经准备完成**。本项工作没有启动任何官方评分容器；镜像实际可用性、容器资源行为和目标仓库测试能否执行由独立镜像／环境准备记录负责，不能由这份 CPU 回执代替。

## 2. 对实际 wheel 合同的核对

本次核对的是上述 wheel 安装后的真实文件，不是浮动 GitHub `main`：

- `harness.utils.make_test_spec` 直接使用 `image/eval_script/log_parser/eval_type`，F2P/P2P 接受列表，也兼容字符串。官方函数会解析 eval 脚本并增加测试命令退出状态记录；包装不改写这个处理。
- `harness.run_evaluation.run_instance` 接收现成 `TestSpec`，可直接跳过远端 dataset alias 入口。其日志实际写入当前工作目录下的 `logs/run_evaluation/<run_id>/<model>/<instance_id>/`。
- `create_container` 在本地镜像不存在时有 `images.pull` 分支；本轮包装必须显式拒绝该分支。
- `_stage_image_assets` 有远端 URL 获取路径。固定的这 500 项均无此资产；包装对未来出现的非空资产直接报告待准备，不遗漏资产，也不访问 URL。
- 官方 `cleanup_container` 使用 `docker stop/kill/rm` 子进程。已把服务器 `/usr/bin/docker` 原字节复制到新 scorer 的 `bin/docker`，在私有 CPU 用户态内实际执行版本命令成功。正式调用同时固定 `DOCKER_HOST` 到本项目私有 socket，避免 CLI 清理落到默认共享 daemon。
- 官方已有 `report.json` 时会直接返回旧报告。包装在运行前创建独占的新身份目录，存在即拒绝，不依赖官方缓存判断候选是否变化。

安装后源码 SHA、解释器、有效依赖版本和包装源码 SHA 共同写入 `installation-manifest.json`。全部 500 个 task contract 只发布任务身份、镜像、parser、eval type 和可信材料 SHA；不发布隐藏测试名、脚本正文或修复答案。

## 3. 新的可信评分入口

实现为 `src/proworksim/software_benchmark_scorer_v054.py`。它是可信后端的一次一进程入口，既不是 actor 工具，也不进入工具 schema。

入口只接受已经固定 SHA 的本地完整 500 行 JSON 投影，执行时不调用远端 `load_dataset`，不启动原官方 `main` 的远端加载或构建流程。每项实际 `TestSpec` 仍由未修改的官方函数构造，候选应用、测试输出解析及 resolved 判据仍由官方 `run_instance/get_eval_report` 完成。

执行的身份包含：

- 原 `instance_id/base_commit`，REF／MATCH／PROJECT 和 code／delivery 端点；
- 固定 dataset revision、parquet SHA、可信投影文件 SHA 和该完整评分记录 SHA；
- 补丁原字节 SHA、基线完整树 SHA、候选完整树 SHA；
- 官方 manifest digest、config digest、本地 image ID 和 linux/amd64；
- 评分器完整安装 manifest SHA、官方 wheel SHA、配置 SHA；
- 明确的测试超时、CPU、内存、进程数限制、网络关闭状态；
- 单独的评分 attempt 编号，以及 preparation-only 标识。

`run_id` 含条件、端点及上述规范 JSON 的 SHA 前 40 个十六进制字符。改变补丁、树、配置、数据、镜像、评分器、条件、端点或 attempt 都会得到不同目录。原目录保留；重复调用同一身份明确失败，不静默读取旧 `report.json`。技术修复后的重试必须保持原候选并增加单独 attempt；这个入口没有恢复模型、重选候选或把结果反馈模型的通道。

PROJECT 正式候选还会重新读取 v054 的唯一 episode closure，校验实际 terminal-code／last-legal-delivery lock、完整树及补丁回执是否与请求一致。没有合法交付时不制造一个空的 delivery 候选。REF／MATCH 的生成端闭合规则仍需由其原生运行器落实；评分入口固定其传入的补丁、树和配置身份，不把这些生成端工作宣称为已经完成。

空的最终补丁使用官方 `skip_patch=True` 运行原始树，以避免 `git apply` 单纯因为输入为空而制造技术失败；这不会注入 gold patch。环境预检可使用 preparation-only 身份，但其结果不计模型成绩。

若官方没有返回报告、没有可信测试执行／解析证据，或报告标记 `infra_failure`，包装结果为 `technical_unknown`、`resolved=null`；原始官方结果保留。正常解析的 resolved/unresolved 不重写。本包装不根据项目公开测试、退出码或自定义通过率替代官方终评。

## 4. 本地执行和材料隔离

包装只接受已存在的私有 Unix Docker socket；Python 审计钩子拒绝 DNS 及其他 socket 连接，代理环境清空，同时设置 HF 离线与禁用 dotenv 自动加载。Docker SDK 使用显式 socket URL，CLI 使用同一个 `DOCKER_HOST`。

评分容器按已准入的完整 image ID 创建，校验本地 config ID 和 linux/amd64；代理对象拒绝 pull、不同 tag、宿主挂载及设备映射，强制 `network_mode=none`。CPU／内存／进程数由请求中明确冻结的正整数限额控制；本报告没有替正式实验选出一个已验证的最终资源限额。官方自己的容器创建参数和评分脚本语义保持。

完整 parquet、trusted-evaluation JSON、评分脚本、隐藏测试清单和评分日志仅供可信后端使用，不挂载到 actor 容器。可信输出目录建立为 0700，后续新文件使用 0077 umask。该宿主程序与 actor 的真正文件系统边界仍由运行器／容器挂载配置保障；单纯给宿主文件设 0600 不能被表述为对同 UID 进程的隔离。

准入后每个评分子进程可由以下形式调用：

```bash
/data0/zhuxinrui/proworksim-runtime/run-cpu.sh --write-project \
  /usr/bin/env PYTHONPATH=/data0/zhuxinrui/projects/ProWorkSim/src \
  /data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v054/scorer-venv/bin/python \
  -B -m proworksim.software_benchmark_scorer_v054 \
  --request /absolute/trusted/scoring-request.json
```

准备工具为 `tools/prepare_scorer_v054.py`，本次已执行一次真实 500 题合同及合成评分控制；不需要为了报告重复执行。

## 5. 证据位置

| 文件 | 内容 |
| --- | --- |
| `artifacts/software-benchmark-v054/scorer/wheel-reuse.json` | 本地旧缓存与目标 wheel 身份 |
| `.../dependency-reuse.json`、`.../install-report.json` | 依赖复制条目与实际离线安装报告 |
| `.../installation-manifest.json` | 65 个官方源码 SHA、197 个有效依赖版本、解释器和包装身份 |
| `.../task-contracts.json` | 全部 500 个实际官方 TestSpec 的无正文身份回执 |
| `.../preparation-receipt.json` | 真实控制时间、结果、网络／容器／模型计数及来源引用 |
| `.../synthetic-*.log` | 三个纯人工解析控制的原始输入 |

`installation-manifest.json` SHA256 为 `4610e567b83fa51a5f5e7525edad898b2d7c8716a46fac0367fa59ea29df7c7e`；`task-contracts.json` SHA256 为 `2fb41247825f073cdb2c54639f907602d0b02ec5e0419f05999eee612fd3d831`。

随后与并行镜像准备统一了输入 schema：`image_name` 不带 tag，`tag` 单列，平台是 `{"os":"linux","architecture":"amd64"}`，且必须 `status=loaded`。仅重跑受影响的身份控制，1 passed；没有重复 500 个规格或三个合成评分控制。该阶段包装身份为 `installation-manifest-r2.json`，SHA256 `939e102f20784a428c442d703872db850ed09d8192295dab3a5b302013f70b90`。初始 manifest 和控制回执原件保留，差异见 `adapter-alignment-r2.json`。

wheel 和本地虚拟环境不纳入 Git；只保留来源、身份、代码、必要控制和客观报告。

## 6. 已启动的一次性真实 CPU 评分接缝控制

合成控制不能替代实际 Docker 接缝。本次另在看到任何任务评分前固定了完整 500-ID 字典序的第一题 **`astropy__astropy-12907`**，只做一次原始空候选的官方评分。配置于 22:24:48 声明：测试超时 1800 秒、4 CPU、16 GiB、16384 进程上限、`network_mode=none`；没有 gold patch、模型、GPU 或换题规则。该控制用于验证容器、官方脚本、评分调用及 CLI 清理能否闭合，结果不进入任何 REF／MATCH／PROJECT 模型分母。

固定镜像身份：

- 官方 manifest：`sha256:7485c1e3c8861efd0c6a4a78b952857592e541031039000d25e9481f045dc4a3`。
- config／本地 image ID：`sha256:9b1cabf7bcd83a28469f67e3852d8e2207e90d45aa71f436bb7e600bdee8bae2`。
- base commit：`d16bfe05a744909de4b27f5875fe0d4ed41ce607`。

官方 `run_instance(skip_patch=True)` 会创建容器、执行原 eval 脚本并调用 `get_eval_report`；它不会因为候选补丁为空就跳过测试。本控制使用该入口，避开官方 `main` 中可能过滤空预测的路径。

为避免再开一个只读检查容器，r3 包装仅在 preparation-only 路径中，对**同一个实际评分容器**的 `start()` 后增加 HEAD、Git tree、工作树是否干净及 Docker 限额的记录；记录发生在测试脚本进入前。准备候选身份明确标为 `preparation_image_config_and_base_commit`，不是生成出的 PROJECT 完整仓库树 manifest。正式模型候选仍使用自己的完整树与闭合证据。另清除 Docker context/TLS 环境，保持 SDK 与官方清理 CLI 指向同一个私有 daemon。

当前实际控制使用 `installation-manifest-r3.json`，SHA256：

`c4516f5fec0cfcab771fff1041aa901d294a4cc5331e2beb6d23b47c485ef465`

一次性服务 **`proworksim-v054-scorer-preflight-r1.service`** 已于 **22:32:25** 启动；启动核验为 active/running，MainPID 3994107，stderr 0 bytes。其 `controller-claim.json` 使用排他创建；每 30 秒只读首题镜像 inventory，最长等 96 小时。只有固定摘要的该镜像达到 `status=loaded` 才执行一次评分；不反复调用 Docker 预检，不等待全 500 镜像才触发。触发前还核对控制源码、评分包装、manifest 和配置未变化；变化、超时或技术故障均保存明确状态并停止，不自动重试或换题。

**22:32 的状态仍是 `waiting_for_fixed_image`，实际官方容器评分尚未执行，不能写成接缝已通过。** 首镜像准备完成后，可信结果将写入 `runs/software-benchmark-v054/scorer-preflight-r1/controller-status.json`，完整评分材料留在该目录的 `official-output/`，不挂给 actor。公开的启动快照为 `artifacts/software-benchmark-v054/scorer/preflight-launch.json`，冻结配置副本为 `preflight-config.json`。后续结论必须依据实际完成回执，不能用服务已启动代替成功。

### 等待源切换：r2

镜像准备随后确认首镜像旧队列已遇到 registry HTTP 429，其失败的 `first-image-control-r1` 不会继续加载；同一固定镜像将由全量 `preparation-r1` 管线加载。因此在**仍为 0 次实际评分**时停止了上面的旧 waiting 服务，保留其 claim、状态及配置原件；没有删除排他标记或把旧记录改成成功。

新服务 `proworksim-v054-scorer-preflight-r2.service` 于 **22:47:19** 启动，初始核验 active/running、MainPID 485065，状态仍为 `waiting_for_fixed_image`。它监控 `runs/software-benchmark-v054/images/preparation-r1/image-inventory.json` 中同一个 `astropy__astropy-12907`，不等全部 500 题加载完成才触发。首题、manifest/config digest、空候选、配置原字节、scorer r3 源码、96 小时等待和一次执行规则均未改变；这只是未执行等待源的迁移，不是一次评分重试。

**当前应读取 `runs/software-benchmark-v054/scorer-preflight-r2/controller-status.json`**。公开证据为 `preflight-wait-source-r2.json` 和 `preflight-launch-r2.json`；原 r1 等待证据保持。下载限额或等待不计模型失败，尚未执行的真实 Docker 接缝仍为待验证。
