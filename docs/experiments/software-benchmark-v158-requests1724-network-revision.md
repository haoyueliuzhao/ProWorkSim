# Requests1724：独立评分网络环境修订

本修订只针对 `psf__requests-1724` 的官方评分环境，不改变 C0/C1/C2 通信、成员行为、模型配置、原候选或官方测试。实现文件为 `src/proworksim/software_benchmark_requests1724_v158.py`。当前证据仅包含 CPU 控制；尚未运行新的容器、端点探测或 gold/empty 控制，不能据此宣称该题已恢复。

既有真实控制中，Python2 的 CPU 亲和性观测已经恢复。Gold 与 empty 均得到 43 项失败、45 项通过，六个 FAIL_TO_PASS 均失败；保存的失败日志中，外部连接目标都是 `httpbin.org:80`，并出现 DNS 不可达。该题评分容器采用 `network=none`，因此这首先是环境缺口，不是模型修复失败。公开 HTTP 服务当前的内容与历史服务是否兼容，仍需要新的 gold/empty 控制回答。

本次保留原任务 Python2、原 CA、默认 TLS 认证、原测试命令和测试补丁。只使用镜像内已经存在的 `/opt/miniconda3/bin/python` 运行独立 TCP relay；容器启动时实际核验其版本至少为 Python 3.7，且支持 `os.set_blocking`。如果不满足，停止该环境，不安装其他解释器，也不把测试切换到 Python3。

网络边界如下：

- Docker `network=none`，仅私有命名空间、4 CPU / 16 GiB 等由调用方冻结的限额，无宿主目录、设备、端口映射或共享服务器配置修改。
- 只增加容器内 `NET_BIND_SERVICE`，用于绑定容器 loopback 的 80/443；不需要 `NET_ADMIN`、dummy 网卡或路由调整。
- 仅有容器配置 `extra_hosts={"httpbin.org": "127.0.0.1"}`，并核验容器实际只有 `lo`、没有网关。
- 普通用户 host 线程通过原项目 Docker exec stdio 转发到单个冻结的 `httpbin.org` 公网 IPv4 的 80/443；host 不监听端口，不做代理地址发现，不重定向至其他域名。
- 每个评分容器最多 512 次 TCP 连接、64 MiB 双向应用载荷、16 个活动连接、1800 秒。复用 v141 的已观测双边 EOF 处理，不把 TCP EOF 当作 HTTP、TLS 或测试成功。
- TLS 数据保持不透明透传，不替换 CA，不关闭证书或主机名验证。若以后实际出现 CA 验证错误，应另行记录信任材料修订；本实现不会自动放宽 TLS。

需要由调用方另行封存的新资源：gold/empty 各一个独立容器，建议串行，每个仍 4 CPU / 16 GiB；另一次最多四连接、64 KiB 的当前 HTTP/HTTPS 端点预探。预探只确认当前冻结地址及严格 TLS 可达，不证明 Python2 客户端的 CA 兼容性，也不证明参考修复能够通过。

## 新接口与评分接线

`cold_environment(policy, scope_ref=..., directory=..., resolution_ref=..., resolution_source=...)` 只构建私有对象，不发请求。`scope_ref` 和端点证据必须来自本次独立评分修订；`resolution_source` 默认 `v158_current_DNS_and_bounded_endpoint_probe`。端点证据格式沿用 v141：同一 scope、`httpbin.org`、80/443、固定公网 IPv4、该地址两端口的有效 GET 探测记录。调用 `prepare()` 后才可取得 `request_fields(task)`。

返回对象兼容官方评分器所需的这些接缝：

```python
provider = cold_environment(
    new_policy,
    scope_ref=new_scope_ref,
    directory=new_binding_directory,
    resolution_ref=new_endpoint_ref,
)
provider.prepare()                 # 只冻结本地 manifest
fields = provider.request_fields("psf__requests-1724")
```

官方评分器的 `environment` 必须绑定这个新对象；`Containers.create` 和 `validate_attrs` 必须在同一个新 namespace 使用该对象，不能只替换一个模块属性。原 v066 `Containers.create` 在核验上游 options 后会根据 `TLS_TASKS` 增加本题的 `extra_hosts` 和 capability；新 provider 的 `offline.validate_container_config` 精确核验这些实际值，不为其他任务放宽。

原 v066 资格检查包含两个不适用于本题的旧块：所有 Requests 都要求 `timeout_route.real_connect_timeout`，并导入旧 v060 TLS 证明。新独立 qualifier 应明确替换为：

```python
if task == "psf__requests-1724":
    environment.validate_control_environment(observed, identity)
    environment.validate_transport_evidence(
        receipt, quiet, observed, identity, folder,
    )
```

其余 pinned baseline、任务身份、gold 必须通过、empty 必须失败、官方报告及清理证明全部保留。不能伪造 timeout fixture 字段，也不能直接复用旧失败控制作为准入证据。

## 清理与闭包 evaluator

v157 的 selective-reset dispatcher 会把 evaluator 包成普通闭包。旧 v068 清理钩子要求函数 globals 含 `cleanup_container`，不能直接用于这个闭包。

新 `tls.run_official(..., tracking=...)` 不修改共享 harness globals。`EnvironmentContainer.stop/remove` 在调用真实容器删除前，先设置 relay 停止事件、等待 host 线程及 Docker exec 完成并保存 transport 证据；`run_official` 的 `finally` 处理 evaluator 在正常清理前抛错的情形。重复清理是同一个 wrapper 的幂等收尾，不能重开 relay。清理记录通过 `tracking["TLS_lifecycle"]`/现有 scorer 的 `quiet["TLS_lifecycle"]` 保存。

Host/provider 必须保留同一个 `tracking` 对象、`owned_container_ids` 和 `environment_container` wrapper。`tls.finish_transport` 与 `cleanup_transport` 已提供给官方 scorer 原有 `_score`/`cleanup` 调用点。环境资格检查同时核验实际连接预算、当前 IP、原 CA 哈希、relay 线程/exec 结束，以及 stop/remove 之前确已收尾。

## 已完成的 CPU 验证

`tests/test_requests1724_environment_v158.py` 三项控制已通过，覆盖独立 scope/manifest、精确容器 options、Python2 测试与 Python3 relay 分离、真实 wrapper.start 方法链、没有 `cleanup_container` globals 的闭包 evaluator、先结束 relay 再 stop/remove，以及新资格检查的实际字段。

这些控制使用假 Docker/relay 对象，没有任何真实 TCP 连接、容器、模型调用或费用。真实 gold/empty 是否合格仍未定；父调度器应让其保持第二波待处理身份，不换题，不把环境异常填为模型失败，不阻塞已经合格的第一波任务。

## 独立授权与执行顺序

`software_benchmark_scope_v158.py` 不改 v157 的正在运行源码或账本。其根目录是 `runs/software-benchmark-v158/requests1724-environment-r1`，只允许两个新的 `control-psf__requests-1724-{gold,empty}` 身份。评分串行，使用 v157 已冻结 CPU 清单的第 112–115 个位置；这些 CPU 位于 v157 的前 112 个位置之外。每个评分容器 4 CPU / 16 GiB，普通评分进程另占最多 4 GiB 地址空间并共用这四核，无新服务或系统资源组。

端点探测与评分授权分开，避免环境 manifest 等待端点、端点又等待 manifest 的循环：

1. 固定独立 `plan.json`、来源清单和 `config/v158-requests1724-probe-authorization.json`。探测授权只允许本题的当前 DNS、最多四个 HTTP/HTTPS 连接及 64 KiB 应用载荷；模型调用与 Docker 操作都为零。
2. 由调用方运行 `.venv/bin/python -B tools/check_httpbin_direct_v158.py --execute`。工具直接连接解析得到的公网 IPv4，不使用代理；HTTPS 保留 `CERT_REQUIRED`、主机名检查和 `httpbin.org` SNI。它只尝试预先限定的前两个地址、每个 80/443 一次，不自动重试。进入记录、结果或端点文件一旦存在就拒绝再次运行。
3. 仅当单个地址的 80 与 443 都返回有效 `/get` 契约，才写 `network-resolution.json`。探测失败保留记录，不伪造地址或放宽 TLS。
4. 生成当前 provider manifest 和标准 `request.json`，封存独立 `config/v158-requests1724-control-authorization.json`。该授权只含两个 control 资源、最多两个 relay session、合计 1024 TCP 连接／128 MiB，不含正式模型回合或候选评分。
5. 在真实 cold scorer 解释器中先做 `resolve_execution_request` 与 `validate_request` 的纯本地核验，再实际执行 gold/empty。只有其官方结果与新 transport/cleanup 证明都合格，才能将新环境修订单列为第二波准入依据。

增加了 `tests/test_requests1724_scope_v158.py` 的 CPU 控制，核对独立权限、精确两容器资源表、不重叠 CPU 位置，以及四个假 TCP 连接／严格 TLS 参数／单次探测拒绝重入。两份测试文件合计五项通过；全部网络对象都是测试替身，不是实际网络健康证明。
