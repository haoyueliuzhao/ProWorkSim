# v053：官方镜像基线身份修订

日期：2026-10-20。本修订处理正式模型运行前的镜像初始化错误；不调整题单、种子、模型或采样，也不把失败的初始化当作模型失败。

## v2 的共同错误

v2 首批八个仓库均在 `git reset/checkout <profile.commit>` 阶段报告无法解析该对象。八个镜像的 config/image ID 此前已经与官方 registry 发布资产逐一匹配。此时模型调用为 0，实际测试节点为 0。

`runs/software-panel-v053/v2-common-checkout-fault.json` 保留原始流水线状态和停止原因，SHA-256 为：

`f0756c2f10100fd99583440636eaab6a2d0971f2c6157ca4c932f04193a6c905`

这些原始 `false` 记录属于共同接入错误的历史证据，**不能作为最终来源排除依据**。不能据此跳过前八个仓库，或者重新抽取看似更容易接入的任务。后续修订应使用单独环境记录，保留原记录及未进入模型的事实。

题单中的完整上游 commit 没有提取错误。`scripts/software_panel_v053.py:83–103` 直接读取固定官方 profile 类中的 `owner`、`repo`、`commit` 常量。问题在于把这个上游身份误当作官方镜像 Git 历史中的可检出对象。

## 固定官方代码的真实规则

以下位置均指 SWE-smith 固定 revision `9b74ac08118a85c39c356802f7961893af73e07f`：

- `swesmith/profiles/base.py:364` 先检出上游 `profile.commit`；`:374–386` 删除原 `.git`，初始化新 Git 仓库，创建 `Initial commit`，将主分支命名为 `main`，再建立 `swesmith/<owner__repo.commit前八位>` mirror。
- `swesmith/profiles/python.py:54–66` 从 `mirror_url` 克隆到 `/testbed`，随后创建依赖环境并执行 `install_cmds`。因此上游 commit 不必存在于镜像中的 mirror Git 对象库。
- `swesmith/harness/valid.py:102–108` 做来源验证时，只传入原始任务 patch，没有传 `commit`；`swesmith/harness/utils.py:173–205` 只在显式传入 commit 时才 fetch／checkout。来源 clean 基线因而是新镜像的真实初态，bug 是在该初态应用原始任务 patch。
- `swesmith/profiles/base.py:493–520` 的原生 agent 容器入口检出 `instance_id` 分支。`swesmith/harness/gather.py:448–551` 从 mirror main 应用缺陷 patch，创建 `Bug Patch` commit，再删除 FAIL_TO_PASS 文件并创建 `Remove F2P Tests` commit。
- 正式官方评分入口 `swesmith/harness/eval.py:60` 传入 `instance_id`，`swesmith/harness/utils.py:193–199` 再退到 `HEAD~1` 恢复隐藏的 F2P 测试。这个 `HEAD~1` 规则针对已经确认的任务分支，不能直接套到镜像默认 main。

上述官方代码解释了上游 SHA 与 mirror commit 分离的原因，但不能据此推定历史镜像的每个构建细节都与当前代码逐字相同。例如实际 Faker 镜像仍保留 `.github/dependabot.yml`，而当前 `create_mirror` 中有删除该文件的命令。因此应冻结实际镜像身份和实际文件树，不能仅按当前清理规则猜测历史镜像内容。

## 两个实际只读镜像诊断

backend 在原始官方镜像上完成了两个只读、无网络容器的 Git 元数据核查，未执行测试命令或模型。汇总为 `runs/software-panel-v053/mirror-base-diagnostic-v1/summary.json`，SHA-256：

`d2e220fc6135012b0f8441d937c41af06bb7f216ae5f7856c4932625e81c5d74`

| 仓库 | 上游来源 U | 镜像 mirror commit C | mirror tree T |
| --- | --- | --- | --- |
| `joke2k/faker` | `8b401a7d68f5fda1276f36a8fc502ef32050ed72` | `a225b71e4979d5414eb9b38768621c7ee26e4dac` | `9b924f5645898ad3341cbc5a8b7eeae954b9b990` |
| `pydantic/pydantic` | `acb0f10fda1c78441e052c57b4288bc91431f852` | `f62e04832924116e3969698d81fdad6b0f5c5ead` | `c43e64f6ab95f0f67e82142716b5360d0c92de44` |

两例中 `HEAD/main/origin/main` 一致，HEAD 是唯一 `Initial commit`，tracked 与普通 untracked 状态均为空，官方 mirror remote 对应题单仓库；上游 U 对象均不存在。首个预选任务的远端分支存在。

这两个结果不能外推为所有官方镜像都具有 pristine 工作树。

## 必须另外冻结真实镜像工作树 B

对固定前 24 个候选仓库的官方 profile 作只读静态检查，发现明确反例：第 13 个 `facebookresearch/fvcore` 的 `swesmith/profiles/python.py:401–407` 在安装阶段执行：

```text
pip install torch shapely
rm tests/test_focal_loss.py
pip install -e .
```

这证明镜像构建步骤可以主动删除仓库文件。盲目恢复 mirror main 的全部文件，可能把官方构建刻意移除的测试带回，改变真正的测试环境。前 24 个其他 profile 未发现显式 `sed/patch` 改写 `pyproject/setup` 的命令；Pydantic 使用 `make install`，其他多数使用 editable pip 安装。这不等于证明其安装过程没有文件副作用。

因此身份必须区分：

- **U：上游来源 commit**，来自固定官方 profile，仅作为来源身份。
- **C/T：镜像内部 mirror commit 与 Git tree**，从已锁定原始 image ID 的新容器读取，保留 main／HEAD／remote 对应证据。
- **B：镜像真实初始工作树**，包括安装造成的 tracked 删除／修改及实际环境所需文件。B 与 T 是否相同必须依据实际证据，不能预先假定。

v3 初始化／来源资格应以同一已锁定镜像的 B 为基线。clean 保持 B；bug 在 B 上严格应用固定任务 patch；gold 反向恢复并核对回到 B。需要 reset 时，也应恢复已绑定的 B，而不是无条件把全部文件恢复成 T。官方任务分支存在时，可以核对其 bug 阶段与重建缺陷状态的一致性，但不能无证据地猜测分支拓扑，不能在正式回合中 fetch 一个变化中的远端 main。

Actor 的新单提交 Git 历史与评分测试恢复仍须建立在已经绑定的任务初态上，避免把正确祖先或隐藏测试暴露给模型。不能以解决初始化错误为由改变最终候选选择规则、原始测试分母或 200／40／280 设计。

本文件记录已确认的官方语义、两例只读证据和基线身份要求；不宣称 200 题来源资格已经通过。后续每个仓库的 B、缺陷／反向恢复身份和实际测试结果应由新的环境回执分别报告。
