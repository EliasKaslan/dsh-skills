---
name: ascend-server-layout
description: 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。
whenToUse: 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。
---

# 昇腾共享工作区与权重

## 磁盘和目录

对目标路径先 `readlink -f`、`findmnt -T`、`df -h`，不存在时检查最近的已存在父目录。目录名 share/home/weight 不证明独立大盘或 NFS，跨主机同名路径不证明同一份数据。按下载、解压、编译、Docker layer 与缓存峰值一起估算写入。

沿用用户已有布局；需要新布局时可采用 `<个人根>/{env,work,agent,data,tmp,logs}`，权重/数据集用明确的公共入口。不要为统一目录搬动工作中的 conda/CANN 或改共享 shell 配置。CANN 安装树可能内嵌绝对路径，软链也不能证明可搬迁。

将 TMPDIR、PIP_CACHE_DIR、CONDA_PKGS_DIRS、HF_HOME、ModelScope 缓存按目标盘显式配置。`/home` 在大盘上并不保证 Docker root 也在大盘；查 `docker info` 的根目录和对应挂载。挂容器时包含软链的真实目标，核对容器内可见设备、驱动库及路径；不要默认需要 privileged 或挂所有人的目录。

## 挑卡

用户的共享机约束：有别人进程的物理卡整张不可用，不以剩余 HBM 为可用量。采集完整 `npu-smi info`、健康、进程和当前基线；发起任务前再采一次。A3 的物理 NPU、chip/die、运行时 logical ID 与 A5 的单 chip 映射可能不同，要用当前工具核实。`/dev/davinci*` 包含 manager，不能直接数作卡数。

Util=0、进程表为空、低 HBM 三者各自不足以判空。隐藏容器进程、未知映射、异常 HBM、解析失败、告警都标为 UNKNOWN/不可调度；不能把没解析到进程算作空闲。若进程行只有物理 NPU、无法分到两个 chip，保守排除整卡。旧 A3 3500 MiB/A5 6000 MiB 阈值只是历史筛选线，不能排除低占用任务。

先用无 NPU 上下文的工具筛选，确认资源归属后才对选定设备运行 torch 探针。`ASCEND_RT_VISIBLE_DEVICES` 在新进程 import 前设置，记录物理与重映射 logical ID。CPU load、磁盘和设备健康也需满足本轮任务。

## 权重验真

使用 [scripts/inspect_weights.py](scripts/inspect_weights.py)：

```bash
python inspect_weights.py /path/to/model > weights-report.json
```

它只读 config/index 和所有 safetensors 头部，检查 LFS 指针、分片存在性、张量索引映射、dtype/shape、offset 与文件长度，限制 header 分配。退出码 0 只表示这些结构检查通过；没有下载源校验和时不能证明 payload 正确，也不能证明模型可加载。退出码 1 表示完整性失败，2 表示输入错误或检查不完整（如缺配置、多分片缺索引、未知 dtype）；结合 JSON 的 verdict/errors/warnings 解读。

config 的 dtype 不证明每个张量的存储精度，首分片也不代表全部。结合所有分片的 dtype/shape、量化配置、scale/packed 权重布局和 loader 判断实际格式；U8 单独不证明量化类型。反量化 BF16 继承原量化误差，不能当作原生 BF16 基线。

下载固定模型 revision 和目标目录，记录唯一 PID、日志及失败列表；同目录单写者，失败重试不能删另一进程已完成的产物。完成以索引覆盖、结构和上游校验和为准，退出码/分片数量/目录名只是一部分证据。先读当前 CLI `--help`，不要继承旧 ModelScope 私有参数和固定镜像配置。

硬链只在同文件系统且分片保持不可变时复用；修改硬链会改到原文件，小 config/index/tokenizer 应实体复制。`du` 逻辑体积与新增物理占用分别报告。

长任务按需求保存 checkpoint/RNG、逐样本 uid 或追加结果，验证恢复点后再长跑。清理只针对本任务明确记录的 PID/文件；不 prune 共享 Docker、不 reset 他人设备。

历史现场线索与来源见 [references/site-and-sources.md](references/site-and-sources.md)。
