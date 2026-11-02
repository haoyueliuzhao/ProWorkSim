# VS Code 文件监视排除补齐（2026-11-02）

## 现场与结论边界

用户报告“无法监视文件更改。请按照说明链接来解决此问题”。远端日志
`~/.vscode-server/data/logs/20261102T194212/remoteagent.log` 记录：

```text
2026-11-02 21:05:44.392 [error] [File Watcher ('parcel')] Inotify limit reached (ENOSPC) (path: /home/zhuxinrui/datatmp/projects/ProWorkSim)
```

该错误明确指向 inotify 监视额度，不是本次已证实的磁盘空间不足。
当前 `max_user_watches=1048576`、`max_user_instances=128`，未修改系统参数。

报错后的普通用户只读采样发现：

- VS Code fileWatcher PID 2501975 有 480 条 watch，包含 `src`、`tests`、
  `docs`、`config`、`tools` 等目录的 inode；不包含 `runs`、`artifacts` 根目录。
- 同 UID 可见进程合计 522 条 watch，远低于上述上限。这是非原子采样，
  共享或继承的描述符也可能重复计数，不能还原报错瞬间的额度占用。
- 项目和父工作区设置已经排除 `artifacts`；远端个人 Machine 设置缺少此项。
- 跳过已有排除目录及 `.git` 后，项目其余目录单次遍历计 288 个；
  未递归统计庞大的运行数据、环境或实验产物。

因此，本次确认的是历史 ENOSPC 和一处配置覆盖缺口，不能把远端个人设置缺项
认定为该次报错的唯一根因。当前工作区的排除规则原本已经生效；其它请求或
同 UID 的瞬时资源占用只是可能解释，本次没有对应的报错瞬间证据。

## 修改范围

在 `~/.vscode-server/data/Machine/settings.json` 中仅合并：

```json
"files.watcherExclude": {
  "**/ProWorkSim/artifacts/**": true
}
```

保留其余设置，原始内容备份至同目录
`settings.json.before-watcher-fix-20261102`，然后以原权限原子替换配置。
这补齐当前账号其它远端窗口缺少项目工作区设置时的排除覆盖。
项目 `.vscode/settings.json` 和父工作区 `../.vscode/settings.json` 已有对应规则，
不重复改写。远端个人设置位于仓库之外，本次 Git 提交只保存此说明；迁移环境时
仍需把上述一项合并到对应远端设置，不能用示例覆盖其它设置。

被排除产物仍可打开和编辑，其外部变化可能需要手动刷新。本次未使用 root，
未修改 sysctl、共享服务、实验代码或实验数据，也未发送进程信号、重启服务或启动实验。

## 必要核验

1. 解析三份配置，确认项目、父工作区、远端个人设置均排除 `artifacts`、`runs`
   及两套虚拟环境；与备份比较确认远端设置仅增加上述一项。
2. 使用当前 VS Code Server 自带的 `@parcel/watcher` 2.5.6、inotify backend，
   按远端与项目设置合并的排除规则，在实际项目根目录建立一次临时订阅。
   在 `src` 和 `artifacts` 分别创建唯一 `.tmp` 探针，观察 1.2 秒：
   收到源码 create 事件，未收到产物事件，watcher 错误为空。
   订阅与两个探针均已清理；没有执行项目测试套件。

该检查证实当前环境及已落盘规则可以正确监视源码、排除产物，不等同于已验证
运行中客户端的每条订阅或旧通知状态。工作区 watcher 通常随配置变化刷新，
既有扩展监听请求仍可能需要重建。若旧告警仍显示或资源管理器不刷新，在本次
交互结束且保存工作后执行一次 `Developer: Reload Window`（开发人员：重新加载窗口）。
本次未主动重载，避免中断当前扩展会话；也不以没有新增错误日志宣称客户端恢复。

## 官方依据

- [Linux ENOSPC 与排除大型目录](https://code.visualstudio.com/docs/setup/linux#_visual-studio-code-is-unable-to-watch-for-file-changes-in-this-large-workspace-error-enospc)
- [工作区 watcher 配置刷新](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/files/browser/workspaceWatcher.ts)
- [扩展文件监视请求](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/api/common/extHostFileSystemEventService.ts)

历史处理见 [2026-10-25 记录](vscode-file-watcher-20261025.md)，历史事实保持原文。
