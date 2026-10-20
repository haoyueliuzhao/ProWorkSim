# v0.5.4 PROJECT：完整仓库 provider 与文件清单

日期：2026-10-20。范围是用户授权的 PROJECT 文件能力修复及必要 CPU 控制，不授权模型评测。本文描述新 `repository_sources_v054`，历史 v051/v052 模块和冻结实验快照没有改写。

## 问题与变更

旧 `repository_sources_v051` 将初态限制为不超过 200 个文件、总源码不超过 2,000,000 bytes，并要求候选始终保持原文件集合；这会在进入受管 World 前拒绝较大的通用仓库，也会阻断合法新增、删除和重命名。

新 provider 从可信后端已隔离、无并发写入的公开工作树摄取完整条目，保存初态文件、类型、权限及哈希清单。它不读取 gold patch、隐藏测试补丁或评分测试名单，也不按扩展名、gold 涉及路径、预期成绩或编辑文件白名单筛选源码。唯独工作树根目录的 `.git` 控制元数据不进入文件工具清单；空目录不属于可提交文件树。

“完整”指提供给 capture 的公开工作树，而不是自动证明上游镜像已经隔离。镜像、base commit、公开工作树和隐藏材料隔离的资格仍由可信准备后端完成；provider 不能用一次目录遍历代替它。

## 可接入的 API

实现位置为 `src/proworksim/repository_sources_v054.py`。

```python
manifest_path = capture_repository(
    public_worktree,
    new_snapshot_directory,
    task_id=instance_id,
    problem_statement=original_problem,
    source_identity={
        "instance_id": instance_id,
        "repo": repository,
        "base_commit": base_commit,
        "dataset_revision": dataset_revision,
    },
    file_policy=deployment_policy,
)
provider = RepositorySources(manifest_path, runner=confined_public_test_runner)
case = provider.build_case(instance_id)
```

`build_case` 提供 managed S1 所需的 `files`、`entry_metadata`、`editable_paths`、`file_policy`、`family`、`root_goal`、`source_contract` 和 `initial_binding`。初态大文件保留在宿主版本化 bundle 中，`source_contract` 和 `initial_binding` 仅携带整体身份，不复制全文件正文或全部路径哈希到 prompt。新 World 通过分页目录及按需正文读取暴露文件；`editable_paths` 是初态信息，不作为新增路径永久白名单。

World 的每次变更必须先调用：

```python
provider.validate_files(case_id, files, entry_metadata=entry_metadata)
```

验证允许通用合法创建、删除、重命名和正文修改；指定只读路径或前缀的内容、存在性、类型和模式必须保持。新 World 同时版本化文件和元数据，候选导出调用相同的校验与清单 helper，避免模块间采用不同树语义。

## 完整条目表示

`files` 始终是 `path -> string`，完整 `entry_metadata` 与它具有完全相同的键集合。

| 文件类型 | `files[path]` | `entry_metadata[path]` |
| --- | --- | --- |
| 无 NUL 的 UTF-8 常规文件 | 原始正文，保留换行字节语义 | `kind=file, encoding=utf-8, mode=100644` 或 `100755` |
| 其他常规文件 | 规范 base64 | `kind=file, encoding=base64, mode=100644` 或 `100755` |
| 符号链接 | 原始相对 target | `kind=symlink, encoding=symlink-target, mode=120000` |

`decode_entry` 还原原始字节；`tree_manifest` 对路径排序后记录 kind、encoding、mode、原始字节数与 SHA256，并给出整体 `tree_sha256`。这个哈希是项目清单身份，不冒称 Git 原生 tree object ID。

二进制和符号链接不是被静默丢弃的源码：它们保留在版本及导出清单中。文本 read/write/replace 只适用于 UTF-8 常规文件，其他类型由 World 显式告知不支持该正文操作；合法重命名和删除仍需完整保留/移除其元数据。新的普通文本文件默认为 `100644`。

路径须规范、相对，不能进入 `.git`。不遍历符号链接；验证相对目标及完整链接链，不允许借中间链接和 `..` 逃逸。文件/链接不能同时成为另一条目的祖先。特殊设备、FIFO 等不属于本轮文件操作表示，遇到时明确拒绝整个摄取，不跳过条目。

## 部署资源上限

默认 policy：

```json
{
  "version": "repository-file-policy-v054",
  "readonly_paths": [],
  "readonly_prefixes": [],
  "max_files": null,
  "max_source_bytes": 1073741824,
  "max_file_bytes": 268435456
}
```

文件数没有默认 200 之类的数量门槛。默认总原始字节上限为 1 GiB，单条目为 256 MiB，是保护宿主内存与存储的显式部署熔断；三项均可在准备前配置为其他正整数或 `null`。这不是任务抽样规则，也不是已测得的服务器极限。JSON、base64、内存副本及版本历史会有额外开销，因此这些原始字节值不能直接当作 RSS 上界。

超限抛出 `RepositorySourceError`，`category=deployment_limit`，保留具体超限项；既不裁剪文件、正文或路径，也不留下“部分成功”的 snapshot。错误应作为部署未准备状态报告，不能计作模型失败。调整资源配置后须另行记录准备身份，不能看到模型成绩后改变规则。

## 测试与评分隔离

provider 只接受一个独立注入的公开测试 runner：

```python
runner(files=files, entry_metadata=metadata, task=public_task_spec, run_root=path)
```

返回的 `execution.input_tree_sha256` 必须绑定此次完整候选清单。`task` 仅含公开身份、初态 SHA 和部署 policy，不含 gold、`test_patch`、F2P/P2P 或官方隐藏 eval 脚本。公开测试结果保持执行/未执行区别。

本 provider 没有把旧 SWE-smith 的公开 F2P/P2P 流程搬到 Verified，也没有实现或声称完成官方最终评分。Verified 官方 judge、最终候选锁及其执行授权由新的可信后端另行绑定。

## 必要 CPU 控制

针对性测试位于 `tests/test_repository_sources_v054.py`：

- 210 个条目、3 MB 单个源码文件完整摄取，覆盖公开隐藏配置、CRLF、二进制、可执行位和符号链接；不注入全量正文到初态元数据。
- 合法新增、删除、重命名可通过，受保护前缀拒绝变更。
- 显式部署上限整体拒绝，关闭相应上限后保留全部内容。
- 初态哈希变化、符号链接链逃逸及父子文件冲突拒绝。
- 公开测试必须绑定完整候选，隐藏字段不能混入公共身份。

这些是合成目录与 CPU 合同控制，不是 500 题数据准入、官方镜像验证或模型成绩。真实 managed S1 和候选导出的组合控制由对应新模块及集成测试单独记录。
