# VS Code 文件监视排除补充（2026-10-25）

## 问题与证据

用户报告“无法监视文件更改。请按照说明链接来解决此问题”。当前远端日志
`~/.vscode-server/data/logs/20261024T153147/remoteagent.log` 第 43 行记录：

```text
2026-10-25 09:53:30.671 [error] [File Watcher ('parcel')] Inotify limit reached (ENOSPC) (path: /home/zhuxinrui/datatmp/projects/ProWorkSim)
```

这是文件监视额度错误。读取到的 `max_user_watches` 为 1,048,576，
`max_user_instances` 为 128，`max_queued_events` 为 16,384；本次没有修改这些值。

项目和父工作区已有虚拟环境、Python 缓存、`runs`、`datasets` 的排除配置，
但未排除 `artifacts`。该目录包含实验运行环境、来源副本和执行证据。
处理前，以当前普通用户 UID 1021 只读检查 VS Code fileWatcher PID 3175046，
其 inotify 描述符共有 6,338 条 watch，包含 `artifacts`、`src`、`tests` 的目录 inode。

该采样晚于报错时间，不能重建报错瞬间的占用，也不能证明此前全部额度由
`artifacts` 消耗。此时监视进程仍有有效订阅，因此不将历史报错解释为当前所有监视均已停止。

## 本次改动

- 项目 `.vscode/settings.json` 新增 `"**/artifacts/**": true`。
- 实际父工作区 `/home/zhuxinrui/datatmp/projects/.vscode/settings.json` 新增
  `"**/ProWorkSim/artifacts/**": true`。

两处均只补充 `files.watcherExclude`，保留原配置，覆盖直接打开项目和打开父目录的情形。
父工作区配置不属于 ProWorkSim 仓库，不随本次 Git 推送同步；迁移环境时应在实际打开的
工作区恢复相应设置。当前远端 Machine 设置没有修改。

被排除的实验产物仍可打开、编辑，外部变化可能需要手动刷新。源码、测试、脚本、工具、
配置和文档没有新增排除项。本次未使用 root、修改系统参数、向进程发送信号、重启服务、
删除数据或启动实验；项目原有实验暂停状态保持。

## 必要核验与结果

仅核验两个配置的 JSON 格式、新规则以及同一运行中 fileWatcher 的订阅变化：

| 观测项 | 修改前 | 修改后 |
| --- | ---: | ---: |
| PID 3175046 的 inotify watch 条数 | 6,338 | 477 |
| `artifacts` 根目录 inode 在 watch 中 | 是 | 否 |
| `src`、`tests` 根目录 inode 在 watch 中 | 是 | 是 |

修改后也确认 `docs` 根目录仍被监听。同一进程的订阅变化表明新配置已被自动加载，
无需为此次配置更改重启 VS Code Server。两次计数是非原子采样，不作为内核额度的精确余额。

未访问客户端通知界面，因此不宣称已直接确认旧告警消失。若窗口仍显示旧通知或资源管理器
不刷新，可在保存工作后执行一次 `Developer: Reload Window`（开发人员：重新加载窗口）。
不以清空历史日志或没有新错误作为恢复证据。

本次仅改编辑器配置与说明，没有运行项目测试套件或额外的递归目录统计。

## 官方依据

- [Linux 文件监视 ENOSPC 排障：排除大型目录](https://code.visualstudio.com/docs/setup/linux#_visual-studio-code-is-unable-to-watch-for-file-changes-in-this-large-workspace-error-enospc)
- [工作区设置](https://code.visualstudio.com/docs/configure/settings#_workspace-settings)
- [VS Code 工作区监视器：排除配置变化时刷新订阅](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/files/browser/workspaceWatcher.ts)

此前处理背景见 [2026-10-21 记录](vscode-file-watcher-20261021.md)，历史观测保持原文。
