# v057 评分专用NAT helper：实现与准入状态

本helper只为四个已固定requests镜像的评分环境提供真实HTTP／HTTPS访问，Agent不加入网络，不改变候选、官方测试或评分规则。接口为：

```python
start_registry(fresh_root)       # 返回不可变registry引用
validate_registry(registry_ref)  # 校验两lane keeper与slirp身份仍然有效
close_registry(root)            # 仅清理本root精确拥有的资源
```

命令入口为`tools/manage_grader_nat_v057.py start|inspect|close --root <独立v057目录>`。应在宿主执行，不能在评分chroot里间接管理宿主NAT。

## 作用域与生命周期

每个registry恰有两个lane。keeper仅从已固定requests-1921镜像运行`/bin/sleep infinity`，0.1CPU、64MiB、32进程上限、只读根、全部capability移除、no-new-privileges；无host挂载或GPU。默认AppArmor保持，DNS使用slirp提供的10.0.2.3。

各lane使用独立root systemd单元运行slirp，仅配置该keeper的network namespace。正式grader以`container:<keeper ID>`方式加入对应lane，由评分适配器另外验证镜像、标签、namespace和资源。没有host network、端口转发、主机iptables或路由配置。

记录包括完整container ID、keeper PID/start_ticks/netns inode、slirp单元InvocationID/MainPID/start_ticks，以及独立netns地址证明。释放前先确认没有运行中grader仍加入此namespace；对被替换的单元InvocationID拒绝执行stop，不根据模糊进程名杀进程。

## 首次准备失败及收口

初次root slirp 1.0.1启动时，lane0曾成功创建tap0，随后lane1出现AppArmor profiles不可见；下一次记录为设备cgroup挂载点缺失。只读检查发现宿主和私有dockerd视图中的`/sys/fs/cgroup`与`/sys/kernel/security`挂载缺失。全部本次创建的keeper和slirp单元已按精确身份清理，三份独立准备根均保留closed证据。

旧slirp的[官方sandbox实现](https://raw.githubusercontent.com/rootless-containers/slirp4netns/v1.0.1/sandbox.c)在创建mount namespace后仅将根挂载改为private，随后pivot_root并递归脱离旧根；原有子挂载传播是本次事件需要防范的机制。没有通过再次触发事件来证明因果。不得将后续AppArmor／cgroup症状永久固化成放宽评分容器权限的配置。

三次准备使用的helper精确源码已按各自intent SHA核对归档，见[源码索引](../../artifacts/software-benchmark-v057/revisions/nat-helper-pre-private-wrapper-r3/index.json)。首次清理中的Docker“no such object”大小写识别问题也已修正；容器实际已移除，后续静止回执完成了记录收口。

## 新实现的额外边界

后续源码在slirp自身sandbox外，另增加systemd `PrivateMounts=yes`和`unshare --mount --propagation private`，先建立递归私有mount namespace。还要求：

- 启动前宿主cgroup2/securityfs挂载视图存在。
- slirp的mount namespace与宿主不同。
- 每个lane就绪后，宿主关键`/sys`挂载记录与启动前完全一致。
- slirp自身的sandbox、seccomp与host-loopback禁止继续保留。

两个纯CPU契约测试通过：拒绝host network／host挂载／GPU／privileged／错误owner；不关闭被替换InvocationID的root单元。当前没有重新启动任何NAT或评分容器。

**真实网络及生命周期准入尚未完成，helper继续硬暂停。** 本次网络验证确实造成共享服务器挂载异常。用户逐项明确授权后，已恢复全部已确认的原挂载可见性；这不构成重新启动NAT或实验的许可。新增隔离代码只通过有限CPU检查，未证明实际运行安全，不在共享服务器上自动重试。当前状态及核验边界见[事故恢复报告](software-benchmark-v057-shared-server-incident-recovery-r1.md)。

状态及失败／清理引用见[implementation-validation.json](../../artifacts/software-benchmark-v057/grader-nat-helper-r3/implementation-validation.json)。无模型调用，无候选内容或既有评分变化。
