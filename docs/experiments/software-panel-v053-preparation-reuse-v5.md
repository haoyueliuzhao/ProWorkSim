# v5 准备配置与 v4 不可变环境证据复用

本记录对应 v5 启动前的配置与证据链接构造步骤。该步骤没有执行任务测试、模型或 GPU 操作，没有生成正式 200 题 panel；后续运行状态以 `pipeline-v5/pipeline-state.json` 为准。

## 接续原因和范围

v4 停在环境准入阶段。`projected_task_trees` 将 `git apply --cached` 的 stderr 空白警告与 stdout tree SHA 拼接后交给后续 Git 命令，造成公共准备故障；其实际根因和窄修见 [Git 输出修订记录](software-panel-v053-git-output-v5.md)。已经正确闭合的来源资格语义、原测试口径、镜像、资源和缓存政策不因该输出解析修订改变。

v4 原目录和全部记录原样保留。v5 不复用 v4 最终环境总表，也不把公共故障摘要当作来源不合格结论；新总表必须由 v5 准入流程形成。候选库存、固定抽样种子、原始模型及数值配置、SDK、8 路环境准备、32 个指定镜像等待名单和 7200 秒等待参数保持不变。仅切换新的环境、流水线、模型准入及报告路径，并绑定 predecessor/transition。

## 实际构造

新根为 `runs/software-panel-v053/environments-v5`。全部父目录是真实目录，每个复用普通文件单独用绝对 symlink 指向原 v4 文件；不将任何父目录整体链接到旧根，避免新文件写入 v4。

| 内容 | 数量 |
| --- | ---: |
| v4 原普通文件 | 2451 |
| v5 逐文件 symlink | 2443 |
| v5 真实目录，含根目录 | 971 |
| 不放入新根的旧公共故障摘要 | 8 |
| 已有仓库资格 | 16（10 准入、6 拒绝） |
| 已有任务资格 | 167 |
| 已有 completed 回执 | 370 |
| 链接内容总字节 | 141209741 |

这 8 个 `common-system-fault-*.json` 仍保存在 v4，transition 逐个记录原 path/SHA/bytes。其他旧失败 attempt 证据也原样保留为文件链接；没有 completed 的 attempt 不因此变成完成记录。

逐文件复用清单为：

`runs/software-panel-v053/environment-reuse-v4-to-v5.json`

SHA256：`cef29c37dd8b3c60307d71944614d9364f287a88af1ba39fe1f8b8e50df79047`

清单在创建链接时对原文件内容计算一次 SHA，并检查读取前后 stat 一致；没有重复执行原任务。接续说明为：

`runs/software-panel-v053/preparation-transition-v4-to-v5.json`

SHA256：`4d7e6d2f368534d96c4af7a1aeb1a0d783575c92761629ace30bb6e6728bbf09`

## 写入边界

后端持久写入入口 `write_new` 使用 `open("xb")`。已有文件链接会拒绝覆盖；已闭合 qualification/completed 分支读取旧证据并沿用原身份核验。未完结相位使用新的 UUID attempt 目录，因此新进入和新输出落在真实 v5 目录中，不继续写入旧 attempt。

本次对相关 host 持久写路径的检查未发现通过这些链接原地写穿旧目标的 `write_bytes`、`write_text`、普通覆盖 open 或 `.replace` 路径；业务容器内的文件写入与这些宿主证据链接无关。旧引用本身保持原 v4 path 和原 SHA，不能把现场重新生成的 hash 当成新的权威。

读取复用回执不产生新的原测试执行。统计 CPU 执行费用时也应按旧物理回执身份去重，不能因为它们出现在 v5 的资格链中就再次累计。

## 新配置

- `runs/software-panel-v053/backend-config-v5.json`
- `runs/software-panel-v053/host-prepare-base-config-v5.json`
- `runs/software-panel-v053/pipeline-config-v5.json`

配置生成时核对了 backend 除 `environment_root` 外完全一致、host base 除内嵌 backend 外完全一致，候选库存路径和原正式 panel 目标路径未变，32 镜像等待名单未变。模型、数值、任务和种子没有搜索或替换。

配置创建时，正式 panel 目标文件仍不存在，`pipeline-v5` 尚未创建或启动。配置构造新增模型调用、模型加载、任务测试与 GPU 操作均为 0。用户已经取消 GPU 占位，本步骤没有建立占位、恢复服务、交接 watcher 或释放路由。
