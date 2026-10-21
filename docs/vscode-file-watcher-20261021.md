# VS Code 父工作区文件监视修复（2026-10-21）

## 本次原因与证据

用户再次报告“无法监视文件更改。请按照说明链接来解决此问题”。远端 VS Code 日志
`~/.vscode-server/data/logs/20261021T203510/remoteagent.log` 在北京时间
20:37:43、20:40:46 明确记录 Parcel watcher 的 `Inotify limit reached (ENOSPC)`，
监听路径为 `/home/zhuxinrui/datatmp/projects`。

当前打开的是父目录 `projects`，原排除规则只存在于
`ProWorkSim/.vscode/settings.json`。VS Code 的单目录工作区设置从打开的根目录加载，
不会把子仓库的 `.vscode/settings.json` 作为父工作区配置。排查时父目录的配置文件和
当前远端 `~/.vscode-server/data/Machine/settings.json` 均不存在。
2026-10-03 报告描述的是当时环境，不能据此认为当前环境仍保留远端配置。

| 指标 | 本次观测值 |
| --- | ---: |
| `fs.inotify.max_user_watches` | 1,048,576 |
| `fs.inotify.max_user_instances` | 128 |
| `fs.inotify.max_queued_events` | 16,384 |
| `ProWorkSim/runs` 目录数（包含根目录） | 1,410,923 |
| `ProWorkSim/runs` 文件数 | 10,173,587 |
| 排查时当前 UID 可见 inotify 描述符数 | 9 |
| 排查时当前 UID 可见 watch 项合计 | 79 |
| 旧 fileWatcher PID 1620800 的 watch 项数 | 0 |

目录统计采用不跟随符号链接的单次遍历；实验仍在运行，数字为非原子观测，随后可能变化。
仅 `runs` 的目录数已超过单用户 watch 上限。错误后的低占用不代表报错瞬间没有耗尽额度；
失败后 watcher 释放资源是可能解释，本次没有捕获报错瞬间的原子配额快照。

同一日志随后还记录了运行临时目录在建立监听期间消失的 `EUNKNOWN` 错误。
排除 `runs` 同时避免递归监视这些高频创建、删除的实验临时目录。

宿主路径检查确认 `/home/zhuxinrui/datatmp/projects`、
`/data1/zhuxinrui/projects`、`/data0/zhuxinrui/projects` 解析到同一目录，设备号和 inode 相同。

## 已实施的配置

新增两个本机配置文件，合并效果仅针对 ProWorkSim：

- `/data0/zhuxinrui/projects/.vscode/settings.json`：覆盖当前父工作区。
- `~/.vscode-server/data/Machine/settings.json`：覆盖当前账号在该远端的窗口。

通过 `files.watcherExclude` 排除 ProWorkSim 的 `.venv`、`.train-venv`、
`__pycache__`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`runs`、`datasets`。
规则带 `**/ProWorkSim/` 前缀，不把其他项目的同名目录统一排除。
源码、测试、脚本、文档和 examples 保留正常监视；现有仓库内配置继续用于直接打开仓库的场景。

两个新增配置都在本仓库之外，不随本仓库 Git 推送同步。换服务器或重建 VS Code Server 后，
需在实际父工作区或远端用户设置中重新部署。核心规则为：

```json
{
  "files.watcherExclude": {
    "**/ProWorkSim/runs/**": true,
    "**/ProWorkSim/.venv/**": true,
    "**/ProWorkSim/.train-venv/**": true
  }
}
```

未改动 sysctl 上限；未删除实验产物、修改实验代码或操作实验进程。
被排除目录的外部变化可能需要手动刷新，文件仍可打开和编辑。

## 必要核验与当前生效边界

使用当前 VS Code Server 自带的 `@parcel/watcher` 2.5.6、inotify backend 和实际父工作区
排除配置进行一次事件检查，同时解析并比较父工作区和远端配置：

- 在 `ProWorkSim/src` 创建唯一临时文件，成功收到 create 事件。
- 在 `ProWorkSim/runs` 创建唯一临时文件，没有收到该文件事件。
- watcher 回调没有错误；测试订阅和两个临时文件均已清理。

这验证了已落盘排除规则能够建立有效的源码监视，不等同于客户端已经加载新配置。

为恢复旧监听，仅对确认身份的 fileWatcher PID 1620800 发送一次 SIGTERM。
已安装的 VS Code 代码会自动重建该子进程并回放内存请求；日志在 21:00:12 记录重启，
新进程 PID 1650642 已出现。没有重启 VS Code 主服务或扩展宿主。
重启后首次采样的 watch 数仍为 0，尚不能宣称运行中窗口已恢复。
自动重建回放已有请求，本身不会强制客户端重新读取 settings。

完成当前交互后，在相关 VS Code 窗口执行命令面板的
`Developer: Reload Window`（开发人员：重新加载窗口），使客户端重新加载排除规则。
本次未主动重载窗口，避免中断正在运行的扩展宿主会话。
客户端告警是否消失、资源管理器是否能刷新源码变化，仍需在窗口重载后确认。
不通过清空历史日志或仅观察无新报错来宣称恢复。

本次只涉及编辑器配置和说明，未运行项目测试套件、模型 API、训练或 GPU 实验。

## 官方说明

- [VS Code Linux ENOSPC 排障](https://code.visualstudio.com/docs/setup/linux#_visual-studio-code-is-unable-to-watch-for-file-changes-in-this-large-workspace-error-enospc)
- [Workspace settings.json 的位置](https://code.visualstudio.com/docs/configure/settings#_workspace-settingsjson-location)
- [File Watcher Issues](https://github.com/microsoft/vscode/wiki/File-Watcher-Issues)
