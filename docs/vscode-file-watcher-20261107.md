# VS Code 文件监视额度耗尽修复（2026-11-07）

## 这次确认的故障

当前 VS Code Server 为 1.145.0，安装版本标识
`a717861c07586a53d83b80d742cd3f59b20a6273`。
日志 `~/.vscode-server/data/logs/20261106T214236/remoteagent.log`
于 2026-11-06 23:24:24 记录 Parcel 对本项目的
`Inotify limit reached (ENOSPC)`，2026-11-07 11:14:11 又记录多处普通
`fs.watch()` 因额度耗尽失败。上述日期与时间按本机日志的北京时间记录。

修复前，对当前普通用户 UID 1021 的可见 inotify 描述符做一次只读采样：

| 指标 | 观测值 |
| --- | ---: |
| `fs.inotify.max_user_watches` | 1,048,576 |
| `fs.inotify.max_user_instances` | 128 |
| 当前 UID 可见 watch 条数合计 | 1,048,576 |
| VS Code fileWatcher PID 1688856 的 watch 条数 | 1,048,534 |

采样不是内核原子快照，共享描述符可能重复计数；结合实际 ENOSPC 和单进程
占用，已明确定位到本用户的 VS Code 文件监视子进程，而不是实验进程。
其实际订阅包含 `.venv`、`.train-venv`、`artifacts`、`runs` 等目录的 inode，
尽管项目、父工作区及远端个人配置中的原有 glob 排除规则均完整保留。
这次不是上次缺少 `artifacts` 配置的问题，继续补同一 glob 没有意义。

## 改动及实现依据

保留已有 glob，在三层配置补充直接目录排除：

- 项目 `.vscode/settings.json`：`.venv`、`.train-venv`、`artifacts`、`runs`、
  `datasets`，各设置为 `true`。这些相对路径随项目迁移。
- 父工作区 `../.vscode/settings.json`：对应 `ProWorkSim/<目录>`。
- 当前账号远端 `~/.vscode-server/data/Machine/settings.json`：对应
  `/data0/zhuxinrui/projects/ProWorkSim/<目录>` 的裸绝对目录路径，不追加 `/**`。

本机 Parcel wrapper 将不含 glob 元字符的值转换为相对于订阅根解析的
`ignorePaths`；直接目录排除可在遍历目录树时剪枝。远端物理绝对路径还覆盖
订阅根位于大型目录内部时，相对 glob 无法匹配祖先目录名的边界。
不将物理绝对路径写入可移植的仓库设置。

远端原设置备份为同目录 `settings.json.before-watcher-fix-20261107`；
写入前检查未发生并发编辑，保持原权限并原子替换。
项目设置随本次 Git 提交保存，父工作区和远端个人设置位于仓库外，迁移时需另行配置。

安装版还存在同路径请求合并取排除项交集、扩展请求缓存排除项等行为，
Parcel 目录树缓存也可能影响范围；这些只是源码层面的可能机制。
本次没有完整重现导致原有 glob 未被实际遵守的内部请求序列，
不能把某一个机制或某个扩展认定为唯一根因。

## 实际恢复与必要验证

新增配置后，同一 PID 1688856 的 watch 条数从 **1,048,534 降至 471**，
上述四个实际存在的大型目录的 inode 已不在其订阅中。
配置热更新已释放异常监听，因此取消了原先考虑的单独 watcher 重建：
**没有发送 SIGTERM，也没有重启任何进程或窗口。**

随后对这个实际运行中的进程做一次动态检查，而非另起一个监视器代替它：

1. 在 `src`、`artifacts` 各创建一个唯一临时空目录，等待约一秒。
2. 读取同一 PID 的 inotify 记录，源码探针目录已被自动订阅，产物探针未被订阅。
3. `src`、`tests`、`docs`、`config`、`tools` 根目录均仍被监听；
   探针期间为 472 条 watch，符合新增一个源码目录。
4. 两个临时目录均已清理。

三份设置均通过 JSON 解析，远端与备份的差异严格为五个新增排除项。
仅完成上述必要检查，未运行项目测试、模型、API、GPU 或 Docker 实验，
也未递归统计海量实验目录。未使用 root、修改 sysctl 或操作共享服务。

这些结果确认运行中的递归监视器恢复了预期范围并能处理源码目录新增。
没有直接访问客户端通知界面，不能声称已看到旧通知消失。
若只剩旧通知，可关闭通知；如果资源管理器仍不刷新，保存工作后执行一次
`Developer: Reload Window`（开发人员：重新加载窗口）。
被排除产物仍可打开和编辑，其外部变化可能需要手动刷新。

## 参考

- [VS Code Linux 文件监视 ENOSPC 排障](https://code.visualstudio.com/docs/setup/linux#_visual-studio-code-is-unable-to-watch-for-file-changes-in-this-large-workspace-error-enospc)
- [Parcel 2.5.6 的目录与 glob 排除实现](https://github.com/parcel-bundler/watcher/blob/v2.5.6/src/Watcher.cc)
- [上次处理记录](vscode-file-watcher-20261102.md)，历史观测保持原文。
