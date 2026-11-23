# 参考依据

底本：`D:/workspace/share/raw/ascend-server-layout/` 与 ascend-env，2026-11-16 重新审查。旧 init-home-layout.sh 的 `--root` 不会传入生成 env.sh 的硬编码 XH；一次性 _tmp_migrate_188.sh 涉及 mv 和共享布局修改；npu-free.py 会丢弃某些只有 NPU ID 的双 chip 进程映射，且按静态 HBM 阈值判空。三者仍留在 `../scripts/` 作墓碑（调用即以 `BLOCKED_LEGACY_ENTRY` 失败、退出码 2），不再作为可执行工具。

权重头部格式：[Safetensors 官方格式](https://github.com/huggingface/safetensors#format)。本工具不读取整份 payload，不声称替代官方 loader/文件 checksum。历史模型路径、分片数、大小留在原材料，查询目标模型时按“主机+绝对路径+revision+所有分片”重采。
