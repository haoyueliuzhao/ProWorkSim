# 归档r3：标准会话辅助进程的严格身份例外

r1真实执行因两个普通用户会话辅助进程的cwd/fd等不可读而停止，0完成、0原文件释放；原失败及源码、计划保持。r2先固定这两个PID并通过3项分类控制，但只读真实探针又发现另一个合法sshd会话，按静态名单正确拒绝，仍0归档。r2原件也保留。r3是新的包装器、计划和输出身份，没有修改已seal的模型运行闭包或r1源文件。

r3不再声称完整扫描所有本用户进程。只排除符合以下严格类别的**不可读字段**，可读字段仍必须检查，任何指向历史model-ledger的实际路径引用仍会拒绝：

- SSH会话辅助进程：Name与comm均为sshd、四项Uid均为1021、父进程Name/comm均为sshd且Uid均为0、父子同属严格匹配的 `/user.slice/user-1021.slice/session-N.scope`、父starttime严格早于子、父PPid必须为冻结master1957852。
- 冻结master身份为sshd、Uid全0、PPid1、starttime767726512、`/system.slice/ssh.service`；实际master整个身份必须匹配。master换代或PID复用不能自动放行。
- PAM仅保留已核实的(sd-pam)1247270/start786511124及其systemd父1247269/start786511123的完整精确见证。

每次例外均双读子、父与SSH master身份，变化即拒绝，完整记录进程、父进程、master、不可读字段与实际可读检查数量。其他未知进程、实验worker不可读字段继续失败；不会通过root去读取受限fd，也不会控制或停止任何会话进程。所读root父/master的status/comm/starttime/cgroup只是普通用户可读的身份元数据，不是使用root权限。

真实普通用户只读探针观察18个本用户进程、1249条可读引用，记录两个sshd和一个PAM例外；`all_own_process_fields_were_inspected=false`，没有已读历史路径引用。此结论不能外推为不可读字段没有文件引用。归档准入还独立要求原result已结束、quiescence全owned removed、无active资源claim、源inode稳定，并在释放前完成原字节流SHA和全档解压回读验证。详细证据在session-helper-identity-witness.json、process-inspection-exclusions.jsonl与real-process-probe.json。

3项CPU控制通过，包括新合法SSH会话、伪造UID/name/cgroup/父链、master PID/starttime变更、PAM父变更、可读历史引用优先拒绝和未知worker不可读拒绝；没有重复执行此前压缩/恢复控制。r3只复用r1已有的历史文件身份清单，实际每回合开始和释放前仍重新核对；未重复读取大JSON。本子任务尚未执行r3真实归档或unlink。

r3仍是688个回合、151367个JSON、潜在258.5907GiB；默认先v066，主盘free达到180GiB停止新回合，最多2并发与2CPU，其他压缩、保护清单和恢复规则沿用r1。新输出唯一位于 `/data1/proworksim-zhuxinrui/passive-history-v203-2-1/r3`。

主任务可执行：

```bash
.venv/bin/python -B tools/archive_passive_pilot_history_v203_2_1_r3.py --run --workers 2 --target-free-gib 180
```

恢复使用同r3入口及该回合verified.json：

```bash
.venv/bin/python -B tools/archive_passive_pilot_history_v203_2_1_r3.py --restore /data1/proworksim-zhuxinrui/passive-history-v203-2-1/r3/<item-id>/verified.json --member request-0001.json
```

将来若master或受限会话身份已改变，准入会拒绝并需要新的身份审阅，不会默默放宽；归档原字节和单文件恢复依据仍完整保留。旧历史分析依然需要先restore，不能称为透明文件替换。
