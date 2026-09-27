# TeamBench D1/D2：v0.21 CPU 资产、评分与角色隔离准入

本轮取得了两个小型数据工程家族的完整任务资产，并把“可下载”推进到实际生成、运行和评分。**原生 D1、D2 评分均发现可复现阻断；一个只修正命令引号、增加 expected 准入检查的 D2 本地变体通过了 15 项预声明控制。角色隔离尚未通过，因此外部模型评价入口仍不可启动。**

没有模型调用、GPU 使用、参数更新、模型成功率或官方 benchmark 模型成绩。程序正反见证只检验资产和评分机制，不是目标模型协作轨迹，不产生 ID-VTDO 类别频数。

## 1. 范围与来源

- 官方仓库：[ybkim95/TeamBench](https://github.com/ybkim95/TeamBench/tree/d185aef1916fd86a9ba554d581fd256319a973af)。固定提交 `d185aef1916fd86a9ba554d581fd256319a973af`，未跟随 main。
- 子集：`D1_schema_drift`、`D2_data_quality`，各使用任务定义中的 seeds `0,1,2`。D1 阻断后只补看 D2，没有继续寻找有利的第三个家族。
- 34 个原始文件，共 182,889 bytes：两个 generator、公共 primitives/base/registry、workspace、setup、spec/brief、task.yaml、原 grade、grade_task、角色工具/编排代码、Docker Compose/镜像定义、LICENSE。完整清单及 URL、Git blob SHA-1、SHA-256 见 [资产清单](teambench-v021-assets.json)。下载字节的 Git blob SHA-1 与前轮固定官方 tree 相符。
- **这些是官方程序合成的 CSV/ETL 任务，不是真实企业数据、真实数据集迁移或 UCI 零售的派生数据。**两个 generator 使用固定随机数、名字/数值/部门池合成记录；此次没有启用任何真实数据缺失后的合成 fallback。不能用“官方 benchmark”替换“真实来源”的表述。
- 这些已经检查过答案和程序见证的 seeds 只用于入口开发。未来正式外测需另定未参与修复选择的实例、用途隔离与冻结配置；不能将本轮三种 seed 称为三个独立真实数据来源。

固定来源：[D1 generator](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/generators/gen_d1_schema_drift.py)、[D2 generator](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/generators/gen_d2_data_quality.py)、[D1 grader](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/tasks/D1_schema_drift/grade.sh)、[D2 grader](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/tasks/D2_data_quality/grade.sh)。

## 2. 执行边界与可复现入口

实现：[scripts/teambench_admission_v021.py](../../scripts/teambench_admission_v021.py)。脚本只允许预先逐文件审读、固定 SHA-256 的原始代码执行，复制到专用 reviewed-source 后导入；没有遍历导入其余 task、模型 adapter 或未知包。生成/评分子进程使用不含 API key 的最小环境，最多 20 秒 CPU、1 GiB 地址空间、16 MiB 单文件、30 秒 wall time。每个程序见证在独立目录运行。

这是一组**只执行审读过程序的受限 CPU 子进程**，不是 OS 文件系统/网络沙箱，不应据此执行任意模型生成代码。隔离容器没有启动。Docker 可用性只做只读探查，未修改 daemon、群组、用户、镜像或安装平台。

```bash
.venv/bin/python -m scripts.teambench_admission_v021 \
  --assets runs/assets/domain-v021/TeamBench \
  --output runs/teambench-v021-admission-new
```

输出目录必须不存在。脚本会重建两个家族的完整 seed 资产、运行原 grader 控制、本地 D2 变体控制、固定角色工具夹具，并分别给出状态。当前整体 `model_benchmark_launchable=false`、`final_external_evaluation_eligible=false`，没有连接模型评测队列。

原始最终产物：`runs/teambench-v021-admission-complete/`；已提交的[结果与证据记录](teambench-v021-admission.json)保留原报告路径和 SHA-256、每次 control 的路径、原生 score、expected/output SHA、错误日志与隔离探查。此前两次 CPU 脚本开发重放分别保留在 `runs/teambench-v021-admission/` 和 `runs/teambench-v021-admission-final/`；它们使用相同 seeds，不构成额外独立样本，也没有从中选择更有利的模型结果。

## 3. 原生评分：24 个控制与两个明确阻断

每个家族、每个 seed 固定四项：原始错误程序、按公开合同编写的程序见证、定向错误程序、正确程序配 `verdict=fail` 的 attestation。程序见证不读取 grader 的 expected.json；D1 的字段映射来自公开 spec，D2 使用原 CSV 字段与公开规则。

以下分数是**原脚本对程序夹具的检查数**，不是模型分数。D1 的 16 项包含 15 项产物/执行检查和 1 项 attestation 字符串检查；D2 的 11 项包含 10 项产物/执行检查和 1 项 attestation 字符串检查。

| 家族 / 控制 | seed 0 | seed 1 | seed 2 |
|---|---:|---:|---:|
| D1 原始错误 ETL | 3/16 | 3/16 | 3/16 |
| D1 按公开合同编写的 ETL | 15/16 | 15/16 | 15/16 |
| D1 错误地保留最后重复项 | 13/16 | 13/16 | 13/16 |
| D1 同一正确产物、fail attestation | 14/16 | 14/16 | 14/16 |
| D2 原始错误清洗程序 | 5/11 | 6/11 | 5/11 |
| D2 按公开合同编写的清洗程序 | 10/11 | 10/11 | 10/11 |
| D2 遗漏低分缺部门纠正 | 9/11 | 9/11 | 9/11 |
| D2 同一正确产物、fail attestation | 9/11 | 9/11 | 9/11 |

### D1：同一记录的 category 要求相互矛盾

generator 为 `id=3` 生成更高 value 的重复项，其 category 分别为 `design`、`research`、`logistics`；正确去重后应保留该项。同时，`expected.batch1_missing_category_ids` 仍包含 `3`。原 grader 一项要求该记录 category=`unknown`，另一项要求 category=`dedup_category`。这两个判断不可能在同一输出上同时成立。

三种 seed 的程序见证均仅因 `missing_category_fill_fail` 失分，原生 `pass=false` 原样保留，没有修改 expected、删检查或回填成功。这个反例支持拒绝所测 D1 评分合同，不是对整个 TeamBench 错误率的估计。

### D2：缺失值检查在 shell eval 阶段发生语法错误

原 `grade.sh` 的缺失值检查包含嵌套诊断字符串双引号。外层 shell 展开后，`eval` 解析命令时遇到未正确保护的 `r.get(col)`，报 `syntax error near unexpected token '('`；该 Python 内容检查没有运行。原 `check()` 抑制 stderr，因此通常只留下 `missing_values_not_replaced`，容易误认为产物仍有缺失值。

单点诊断复制**原检查表达式**，仅让 `eval` 的 stderr 可见，得到上述 shell 错误（退出码 2）。未改写原 grade，也没有把诊断运行当修复后的官方分数。逐行按公开合同从输入重建的本地完整产物核验显示：三个正确程序输出分别为 29、23、29 行，列、记录、排序与 Unix 行结束符均符合；三个定向错误程序均不符合。该完整产物核验是 ProWorkSim 的开发控制，不能替代原生分数。

### 缺 expected 的原生误放行

另用 seed 0 的错误 D2 程序移除 `expected.json`，原 grader 跳过内容检查，只剩执行、产物存在、attestation 三项，给出 **3/3、pass=true**。这不是合法降级模式。本地入口对此直接拒绝，绝不把缺资产误报为满分。

## 4. 最小 D2 本地修复变体：15/15 控制符合预期

变体名称为 `proworksim-d2-quote-failclosed-v0.21`，**不是未经改动的官方 TeamBench 评分入口**。没有改 expected、内容判断条件、任务题面或原文件。只做两类修改：

1. 从出错的诊断 f-string 中删除围住 `r.get(col)` 显示值的多余双引号；这只影响报错文字的引号，不改变缺失值谓词。
2. 在调用 grader 前要求 expected 存在、SHA-256 与原生成实例的冻结引用相同、所有必要字段及类型完整、列与去重映射一致。缺失和篡改直接拒绝，不生成有效分数。

[精确补丁](teambench-v021-d2-grader.patch)及源标识：

- 原 D2 grade SHA-256：`39e0b4726b21b34a2fbcd5b3987b1a193cdcb1028dc9d84dea766d7366f1d970`。
- 变体 grade SHA-256：`8b0a417ea3f810cfa07e376b80b869d479bf574305aef67c62903a738a9a096b`。
- 补丁 SHA-256：`2f268c44db9e517b117abb00dfbbf4857f2130c3a50cfd5d8faeb3349560b480`。

变体运行前已写入 `d2-local-variant/declaration.json`：固定 3 seeds × 下列 5 项，共 15 项；没有重采或替换失败。9 项实际执行 grader，6 项在 expected 检查处拒绝。

| 变体控制 | 三个 seed 的结果 | 解释 |
|---|---|---|
| 正确程序 + pass attestation 夹具 | 各 11/11，pass | 所测本地评分合同可接受正确产物 |
| 错误部门纠正 + 伪造 pass 夹具 | 各 10/11，fail | 声称 pass 不能绕过产物检查 |
| 正确产物 + fail attestation | 各 10/11，fail | 产物 10/10 与 attestation 0/1 分开保存 |
| 缺 expected | 3 次入口拒绝，score=null | 不以 3/3 的缩小分母放行 |
| expected 改一项、保留原冻结 SHA | 3 次入口拒绝，score=null | 不能把修改后的参考当原实例参考 |

**15/15 是预声明程序控制符合预期，不是 15 个模型 episode 成功。**attestation 均为测试夹具，脚本不会把 `verdict=pass` 解释为存在真实 verifier、独立运行过验证命令或完成合法交接。变体评分合同有了有限支持；角色和真实协作入口仍不准入。

## 5. 角色隔离分层结果

固定来源：[agent_interface.py](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/harness/agent_interface.py)、[docker-compose.yml](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/docker-compose.yml)。

使用原 Python 角色工具，针对仅含 fixture 文本的临时目录实际运行，没有读取账号隐私或调用模型：

| 原工具层控制 | 实测 |
|---|---|
| Executor read `/task/spec.md` | 允许；full spec 与 brief 所在父目录一起在允许根中 |
| Executor read `/shared/reports/expected.json` | 允许，取得 grader-only 夹具 |
| Verifier read `/shared/reports/expected.json` | 允许，取得 grader-only 夹具 |
| Verifier write 工具写 workspace | 拒绝 |
| Verifier run 工具执行固定 `printf fixture > marker.txt` | 允许，实际改写 workspace 夹具 |

这些是原 host 工具实现的可复现行为，不能称 OS 隔离已通过。原 Compose 另将 reports 挂载给 Executor（可写）和 Verifier（只读），而原 generator/grade_task 将 expected 放在 reports；**静态挂载合同会暴露参考答案**。没有启动容器，不声称复现了容器内行为。

当前 Docker client 存在，但访问 `/var/run/docker.sock` 返回 permission denied；`sudo -n docker info` 要求密码；podman 不存在。最初一次 Docker 探查误继承任务子进程的 1 GiB 地址空间限制，Go client 因线程创建失败尚未访问 daemon；原日志保留，随后在不施加任务代码地址空间上限的只读 client 探查中确认权限缺口。没有因该诊断更改任务执行资源限制。

后续若继续，必须先实现并实测：grader 参考目录不挂给任何工作角色；Executor 只取得 brief 和合法传递资料；Verifier 无法经任意执行写入提交源；角色命令的真实 OS 隔离与只读挂载成立。不能用 prompt、Python 读写 allow-list 或本次程序控制替代它们。本轮未修复整个第三方角色 harness，也未申请或突破 daemon 权限。

## 6. 最终准入与后继

| 资格 | 状态 |
|---|---|
| 两个小家族的固定资产 | 完整，SHA 已核对 |
| D1 原生评分合同 | 拒绝：矛盾 expected |
| D2 原生评分合同 | 拒绝：shell quoting 使一项内容检查不执行 |
| D2 显式本地 quote + fail-closed 变体 | 所测 15 项控制通过 |
| 原生 host 角色工具隔离 | 拒绝：参考/全 spec 暴露，verifier 可经 run 改 workspace |
| 原 Compose 参考答案隔离 | 静态合同不合格；尚未容器实跑 |
| 实际 OS 角色隔离 | pending：无已可用容器权限 |
| 官方原生协作 benchmark / 模型入口 | 不准入，模型调用 0 |

有针对性的代码校验为 **5 passed**，Ruff 通过；未重跑全仓测试。最终目录实际执行原生 grader 25 次（24 个主控制 + 1 个缺 expected 反例），变体 grader 9 次，另 6 项在调用前拒绝。不能把这些重复的程序见证次数作为协作任务数、独立来源数、模型成绩分母或训练支持量。

这一结果完成了“小而完整资产与可判定的显式评分变体”的工程推进，也把阻止外部协作评价的缺口定位到具体参考、引号及角色权限。下一步不需要扩散到更多平台；应冻结明确命名的修复变体与评分合同，再在合法可用的容器运行环境中完成角色隔离实证，并单独授权模型评价。
