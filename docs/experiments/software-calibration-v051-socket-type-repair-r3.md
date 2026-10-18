# v051 CAL2 共享隔离器的 socket 类型窄修

r2实际boltons回执出现确定的共同环境错误：原 `tests/test_funcutils_fb_py3.py::test_wraps_async` 导入asyncio，继而在ssl定义 `class SSLSocket(socket)` 时发生 `TypeError: function() argument 'code' must be code, not str`。当时共享runner将 `socket.socket` 类全局换成 `make_socket` 函数，破坏了随后模块的继承协议。原两个TCP节点本身能通过，先前仅检查这两个节点的控制没有覆盖此组合。故障归因基于原源码与实际异常链，不归于模型补丁。

首批只读审计保存在 `artifacts/software-calibration-v051/cal2-r2-first-execution-audit/report.json`。本修订不修改r2冻结源码、在途工作、原轨迹、原测试或评分；也不重新验收任何已经生成的候选。其他测试表现按其原件报告，不从本次三个节点控制推断整个任务通过。

## 唯一源码变化

只修改主仓 `software_calibration_repo_tests_v051.py` 的有限loopback适配。`socket.socket` 继续是原来的真实类对象，保留后续ssl及其他模块的正常继承能力。只在原类的 `__init__`、`bind` 和 `listen` 上作窄方法适配；保留原方法引用，并将不属于两个指定测试首次listener的构造、全部显式fileno语义和普通bind/listen直接交给原方法。原构造的 `family/type/proto=-1` 默认推断保持。

只有两个原TCP测试的首次默认AF_INET/SOCK_STREAM listener构造可以取得事前绑定的listener FD；弱引用身份表限制只有这一实际listener对象可使用固定localhost bind和backlog100的既有描述符桥接。`create_connection`继续仅消费原有限4+1个预连接client FD。新的socket/connect/bind/listen系统调用仍受原seccomp限制，真实accept/send/recv/close/timeout保持。没有增加连接、扩大路径或网络权限，也没有用预先import ssl来回避类型错误。

修改前模块、SHA和原审计引用另存 `artifacts/software-calibration-v051/socket-type-repair-r3/first-source.py` 与 `first-source-manifest.json`；原冻结版本不动。

## 一次必要真实控制

从原冻结 `cal2-boltons-1` 缺陷初态取得原字节和runner配置，使用同一个formal isolated pytest child，仅选择以下三个原节点执行一次：

- `tests/test_funcutils_fb_py3.py::test_wraps_async`
- `tests/test_socketutils.py::test_socketutils_netstring`
- `tests/test_socketutils.py::test_socketutils_netstring_timeout`

结果3/3通过，worker与pytest均退出0；完整terminal与三节点齐全，missing/unexpected为空，112个输入文件bytes未变化。隔离回执确认Landlock ABI≥3与原seccomp网络禁令仍安装，登记进程存在。fixture记录确认 `socket.socket` 与原真实类是同一对象、仍为类型；原async节点真实导入ssl并执行通过，没有预import workaround。两个TCP节点恰消费两个listener及4+1个client FD，全部为原预连接真实loopback。

这是一项新增变更控制、一个真实CPU child、三个原测试节点执行，首轮通过，没有失败或重复控制。没有重跑完整412节点、六题三态资格、SDK、tokenizer或模型；没有补验旧业务候选，也没有新GPU、权重加载、反向或参数更新。

控制程序、完整回执、静态检查及独立摘要位于 `artifacts/software-calibration-v051/socket-type-repair-r3/`。未启动库存需由独立r3宿主冻结新准入后接续，本修订和控制本身不启动模型。
