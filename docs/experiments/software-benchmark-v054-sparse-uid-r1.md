# v054 原始高 UID/GID 的宿主映射适配

日期：2026-10-21。此修订属于任务环境准备；不产生模型成绩，不改变原始容器文件所有者的数值。

## 实际触发条件

`matplotlib__matplotlib-25479` 的 Actor 根文件系统已经完整导出并解包。既有清单记录 253,136 个条目，归档为 7,307,562,496 字节，普通文件内容合计 7,126,560,821 字节。`testbed/build/qhull-2020.2` 下 338 个条目的原始 UID 为 `197609`、GID 为 `197121`，超过原固定 guest `1..65536` 映射范围。旧所有权阶段因此拒绝准入。

该失败发生在正式槽位认领、模型加载之前。完整导出及原始逐文件摘要继续使用；修复不再次下载镜像、导出根文件系统或计算全部文件内容摘要。已失败准备记录和旧源文件字节均保留。

## 映射规则

宿主已有的 `subuid/subgid` 分配仍为 `558752:65536`，文件没有被修改。guest root 继续映射为宿主 UID `1021`、GID `1022`。

新的 bootstrap 从原始 manifest 的完整条目集合分别提取 UID 和 GID。已观察的低 ID 保持原 `host = 558752 + guest - 1` 映射。对每一个大于 65536 的已观察 ID，按数值顺序从高到低选取一个未被原始条目使用的低 ID 槽位，将其宿主 ID 用于该高 ID；其余低 ID 的映射不变。没有高 ID 的历史模板仍使用完全相同的旧映射。

本题对应的 UID/GID 映射为：

```text
UID:  0      -> 1021
      1..65535 -> 558752..624286
      197609 -> 624287

GID:  0      -> 1022
      1..65535 -> 558752..624286
      197121 -> 624287
```

guest `65536` 在这份特定映射中不再映射；它未出现在该原始文件清单中。此限制写入 `unmapped_unobserved_uids/gids`，不宣称支持任意新增数值身份。映射数量或长度超过内核限制、已观察 ID 超过现有分配容量、原始数值非法等情况均在任何 `chown` 之前拒绝。

## 所有权与执行的一致性

`ownership` 阶段将完整确定性映射写入返回回执的 `uid_gid_mapping`。既有根文件系统准备流程将其保存在 `rootfs-manifest.json` 的 `ownership_receipt` 中，并保留原 guest UID/GID 字段。

原生 worker 启动器向 bootstrap 传递已存在的公开环境清单和根文件系统路径。bootstrap 核对公开清单绑定的 rootfs manifest SHA、实际根路径、所有权已完成标志和映射回执，再向新 user namespace 写入相同映射。篡改后的映射或不匹配的所有权回执不得启动。clone 同样核验映射回执。

旧纯低 ID 模板没有新增映射字段时，只有其旧 `uid_map/gid_map` 文本与重新推导的低 ID 映射完全一致才可继续。旧控制证据没有改写；新机制准入需要同时保留旧来源和新窄控制证据。

## 必要验证与范围

唯一新增运行控制使用三个合成文件（root、低 UID/GID、高 UID/GID），实际执行一次 user/mount/PID namespace。控制确认：

- namespace 内 root 为 `0:0`，三个文件保持原始 guest 数值。
- 高 ID 文件在 namespace 内为 `197609:197121`，宿主为 `624287:624287`。
- 低 UID `1000`、低 GID `100` 保持原映射。
- 实际 `/proc/self/uid_map`、`gid_map` 与记录映射一致。
- 修改映射回执会被拒绝；被借用的未观察 guest ID 不会与高 ID 别名重叠。
- 纯低 ID 清单仍生成原两段映射。

控制回执：`artifacts/software-benchmark-v054/native-environment/sparse-uid-control-r1.json`，SHA256 `c541eac7776d504cee2dfbab4d2082b942fbb97de956914dfa97e5cf73a6b599`。原始回执与改前源文件保存于 `runs/software-benchmark-v054/native-sparse-uid-control-r1/`。

Python 静态检查和 launcher shell 语法检查通过。没有重跑三组旧 CPU 控制、官方评分或 GPU 测试。上述合成控制证明映射机制；Matplotlib 已导出实例的所有权继续与其真实公开运行时初始化须另外由准备入口完成，不能由合成控制替代。
