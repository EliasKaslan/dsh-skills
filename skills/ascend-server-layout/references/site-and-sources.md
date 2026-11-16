# 历史现场与来源

底本：`D:/workspace/share/raw/ascend-server-layout/` 与 ascend-env，2026-11-16 重新审查。旧 init-home-layout.sh 的 `--root` 不会传入生成 env.sh 的硬编码 XH；一次性 `_tmp_migrate_188.sh` 涉及 mv 和共享布局修改；npu-free.py 会丢弃某些只有 NPU ID 的双 chip 进程映射，且按静态 HBM 阈值判空。三者不再作为可执行工具。

历史个人根 `/home/x00886548`：.188 曾软链到 `/home/vllm/x00886548`，.190 曾为真实目录。当前 A3 路径未复核；使用前查真挂载。不要据此新建目录。

2026-11-16 本轮四台 A5 均读到 aarch64 / 192 核 / 8×Ascend950DT / 每卡 98304 MB；`/home` 与 `/` 同盘；`/mnt/share`、`/mnt/weight` 分别来自 172.27.1.1 的 Share/Weight。177.8.21.1 的 `/` 可用为 0、100%；.25/.26/.27 的 `/` 分别 97%/99%/75%。这是采集时快照，不能用于下轮选卡/写盘。详细命令和输出在 `D:/workspace/share/codex-review/evidence.json`。

权重头部格式：[Safetensors 官方格式](https://github.com/huggingface/safetensors#format)。本工具不读取整份 payload，不声称替代官方 loader/文件 checksum。历史模型路径、分片数、大小留在原材料，查询目标模型时按“主机+绝对路径+revision+所有分片”重采。
