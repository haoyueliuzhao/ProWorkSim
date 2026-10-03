# VS Code 文件监视额度耗尽排查与配置（2026-10-03）

## 原因与证据

本次用户报告“无法监视文件更改。请按照说明链接来解决此问题”。远端 VS Code Server 日志明确记录 `Inotify limit reached (ENOSPC)`；当前用户的实际监视占用接近系统上限。这条错误指向 Linux inotify 文件监视额度，不能仅根据 ENOSPC 将其解释为磁盘容量不足。

排查时的非原子采样如下，进程号与占用可能随后变化：

| 指标 | 观测值 |
| --- | ---: |
| `fs.inotify.max_user_watches` | 1,048,576 |
| `fs.inotify.max_user_instances` | 128 |
| `fs.inotify.max_queued_events` | 16,384 |
| 当前 UID 可见 inotify 描述符数 | 12 |
| 当前 UID 可见 watch 项合计 | 1,048,562 |
| fileWatcher PID 627891 | 1,048,027 |
| fileWatcher PID 733434 | 437 |

统计来自当前 UID 的 `/proc/<pid>/fdinfo`。继承或共享描述符可能重复计数，统计期间其他进程也可能增减监听；这些数字不是内核原子配额快照，不应将与上限的差额当作可靠余量。

日志 `~/.vscode-server/data/logs/20261002T095833/remoteagent.log` 在 2026-10-03 18:32:00（Asia/Shanghai）报告 `/data1/zhuxinrui/projects/Data-Synthesis` 的 inotify ENOSPC。

通过 inode 对照确认，PID 627891 同时监听 ProWorkSim 和 Data-Synthesis 中的目录，并包含 Data-Synthesis 已有项目设置明确排除的 `.codex-worktrees`、`raw_financial_data_lake/data`、`trusted_data_synthesis/artifacts`、虚拟环境和缓存目录。PID 733434 未监听这些排除目录的根，并保有 Data-Synthesis 的源码等目录监听。

因此，本次存在一条没有应用这些项目排除项的实际监听路径。尚未取得该进程所有监听请求及有效配置的完整记录，不能断言具体由哪个窗口设置、扩展请求或配置加载顺序引起，也不能把日志中的项目路径等同于唯一占用来源。

## 修复配置

1. 新增本项目 `.vscode/settings.json`，通过 `files.watcherExclude` 排除 `.venv`、`.train-venv`、Python 缓存、`runs` 和 `datasets`。保留源码、测试、脚本、文档和 examples 的正常递归监视。
2. 在当前用户的远端 `~/.vscode-server/data/Machine/settings.json` 中合并排除规则，覆盖该服务器上的 VS Code 远程窗口：虚拟环境及缓存、`.codex-worktrees`、`raw_financial_data_lake/data`、`trusted_data_synthesis/artifacts`，以及仅限 ProWorkSim 的 `runs`、`datasets`。此配置属于服务器上的个人设置，不随本仓库 Git 推送同步。
3. 修改远端设置前保留备份 `~/.vscode-server/data/Machine/settings.json.before-watcher-fix-20261003`。原内容为空对象；写入时仍采用合并方式。

被排除目录的外部变化可能不再自动刷新，需要时可手动刷新；文件仍可打开和编辑。扩展自行建立的监听不保证遵循 `files.watcherExclude`。Git 忽略规则也不能替代文件监视排除规则。

系统 watch 上限已经高于官方文档示例的 524,288，因此本次没有修改 sysctl。采用的是官方建议的排除大型目录方式，未删除产物、修改实验代码或终止实验进程。

## 验证与生效

JSON 解析用于核验配置格式；本次只有编辑器配置与排查文档变更，不运行 pytest、模型 API 或 GPU 实验，也不将本次排障表述为模型或训练收益。

配置落盘后的首次复查中，PID 627891 仍占用 1,048,027 项，当前 UID 合计仍为 1,048,562。这说明当时旧监听尚未释放，不能把配置写入等同于运行中的告警已经消失。

若运行中的窗口未自动加载配置，保存编辑后，在连接该服务器的相关 VS Code 窗口运行命令面板 `Developer: Reload Window`（开发人员：重新加载窗口）。两个项目都在同一用户下共享额度，只重载其中一个窗口可能保留另一个窗口的旧监听。重载会重启窗口扩展宿主，应在当前交互任务结束后操作。

恢复应结合实际监听占用下降、源码的外部变更能够刷新、客户端警告状态判断。历史日志中的旧错误不会删除，缺少新错误也不单独证明恢复。

## 参考

- [VS Code 官方 Linux 文件监视排障](https://code.visualstudio.com/docs/setup/linux#_visual-studio-code-is-unable-to-watch-for-file-changes-in-this-large-workspace-error-enospc)
- [VS Code 官方 File Watcher Issues](https://github.com/microsoft/vscode/wiki/File-Watcher-Issues)
- [VS Code 官方 File Watcher Internals](https://github.com/microsoft/vscode/wiki/File-Watcher-Internals)
