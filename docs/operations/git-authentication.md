# 本仓库的 Git 认证

GitHub 连接器与服务器命令行 Git 使用不同的认证入口。连接器已经登录，并不意味着服务器拥有可供 `git push` 使用的凭据；GitHub 官方也区分浏览器、API 和命令行认证。[官方说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)

本仓库提供 `tools/git_vscode_askpass.py`，通过当前远程 VS Code 会话已有的 Git 认证通道取得凭据。它根据本终端的 `VSCODE_IPC_HOOK_CLI` 找到同一进程的 Git socket，自动定位当前 VS Code 版本，不固定会随重连变化的 socket 名称，也不从其他会话中猜选账户。

仅在本仓库配置 `core.askPass`；不改系统或用户全局 Git 配置。helper 不保存 token，不打印凭据，也不修改任何实验配置、进程或服务。可以先执行 `tools/git_vscode_askpass.py --check` 检查程序和当前会话连接，此检查不会请求凭据；实际登录是否有效，仍须由 GitHub 认证和推送结果确认。

使用时需要保持已登录 GitHub 的 VS Code 远程会话连接。若 VS Code 要求登录或授予 Git 扩展访问权限，应在编辑器／GitHub 页面完成。无 VS Code 会话的独立后台任务仍需另行配置标准 Git 凭据；这个 helper 不把连接器的认证导出到服务器。

仓库迁移后，可将本地 `core.askPass` 重新指向迁移后的脚本绝对路径。回退本次仓库设置使用 `git config --local --unset core.askPass`，不删除 VS Code 登录状态。原有提交按正常 fast-forward 推送，提交内容和身份保持。
