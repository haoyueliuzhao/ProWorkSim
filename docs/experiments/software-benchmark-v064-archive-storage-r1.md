# v064 完整控制器记录的流式无损存储

PROJECT 为每次编辑保留完整版本，因此不能把控制器输出先全部展开成临时 tar，再留一份展开目录。新接口直接接收归档字节迭代器，将压缩数据写入本轮新建的 `.zst` 文件，同时累计原始流和压缩流的 SHA-256 与字节数。不保存巨大 `raw.tar`，不删除或覆盖已有文件，也不解释模型使用量字段。

压缩器是 `/usr/bin/zstd` 1.4.8 的同字节普通用户副本，存放于 `runs/software-benchmark-v064/archive-codec/zstd`。源码与副本哈希、版本输出和参数封存在同目录 `manifest.json`；运行只执行该固定副本，不改系统安装。压缩参数固定为 `--long=27 -3 -T1 -q -c`。每份归档最多 256 GiB 原始字节、16 GiB 压缩字节；超过任一界限就失败，不裁剪成一个看似完整的归档。

```python
codec = prepare_zstd_codec()
storage = export_compressed_stream(
    chunks, output / "controller.tar.zst", allowed_root=output,
    codec_manifest=codec,
)
with open_verified_archive(storage) as raw:
    with tarfile.open(fileobj=raw, mode="r|") as archive:
        # 仅展开评分、费用和终态候选需要的预声明文件。
        # 完整历史仍保存在可恢复的压缩归档中。
        ...
# 只有以上上下文成功退出，调用方才能另存 round_trip_verified=True 的凭据。
```

`export_compressed_stream` 返回与旧 gzip 接口兼容的 storage 字段：`blob` 是压缩文件引用，`decompressed_sha256`／`decompressed_bytes` 是收到的原始流身份。生产阶段的正常压缩退出不冒称完整往返，默认 `round_trip_verified=False`。消费者完成所需文件读取后，`open_verified_archive` 会继续读取未消费尾部，核对全部原始 SHA 与长度，并检查解压器退出状态。这样实际提取与完整验证合用一次解压；尾部损坏也不能因只读取了前面的结果 JSON 而漏过。原 gzip 和基线 hardlink 接口继续可用。

编码进程通过非阻塞管道和 selector 同时接收输入、输出，没有后台搬运线程。故障只保留本次新建的部分压缩文件，不返回成功 storage；清理只使用本次 `Popen` 对象停止自己的编码子进程，不扫描或控制共享服务器的进程。调用方仍负责为原始字节生产者设置其既有传输截止。

新增三项合成 CPU 控制通过（0.17 秒），对应 Ruff 通过；已通过且未改变的四项 gzip／hardlink 用例未重跑。覆盖顺序 tar 读取、未消费尾部验证、两种容量上限、已存在文件保护、编码子进程退出，以及压缩帧／原始哈希损坏拒绝。测试只使用合成字节，没有 Docker、模型 API、GPU 或系统配置操作。证据见 [validation.json](../../artifacts/software-benchmark-v064/archive-storage-validation-r1/validation.json)。
