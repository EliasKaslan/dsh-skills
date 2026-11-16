# Python、torch_npu 与 Triton

## 解释器与依赖

用目标 Python 绝对路径运行 `$PY -m pip`，记录 `sys.executable`、`sys.prefix`、metadata 及 import 路径。conda 通过它自己的 conda.sh 和绝对前缀 activate，或直接调用解释器；不要伪造 CONDA_PREFIX 来掩盖激活错误。新前缀与缓存放到已核实的盘，保留用户的 channels；排障先 `conda config --show-sources`、`$PY -m pip config debug`，不要改共享 root 的全局配置。

pip 是逐选项合并配置：CLI 优先于环境变量、环境变量优先于配置；命令 section 覆盖 global。site / PIP_CONFIG_FILE 也可覆盖用户配置，所以 XDG 用户文件不是绝对最高。见 [pip 配置](https://pip.pypa.io/en/stable/topics/configuration/)。约束文件要在实际安装命令 `-c`/PIP_CONSTRAINT 生效，并检查子进程；“盘上有 constraints”不代表生效。build isolation 的约束与运行依赖分开检查。

从目标 torch_npu wheel METADATA/官方矩阵取 torch 约束，不机械拼相同主版本；CPU wheel 后缀和架构按目标平台确认。torchvision/torchaudio 仅在任务需要或目标依赖要求时安装，版本不一定与 torch 同号。安装前 dry-run/report 或 download 检查将选哪些 wheel、是否会替换受保护栈。

2026-11-16 本轮 PyPI 查询确认 torch-npu 2.10.0.post6/post7 均存在；上游 vllm-ascend main 当次要求 post7 和 triton-ascend 3.6.0.post2。这只推翻旧“post4 最新/post6 不存在”，不代表新环境应直接装最新包。实际从目标 checkout 求解。

## Triton 同名文件

部分 triton-ascend 发行版依赖社区 triton 并覆盖同一个 `triton/`。distribution 版本与 `triton.__version__` 可能不同，且 x86/arm 依赖不同。按当前 wheel METADATA/RECORD 核对依赖和重叠文件，不能将 3.2.0/3.2.2 写成通用验收串。参考 [官方安装说明](https://github.com/Ascend/triton-ascend/blob/main/docs/zh/installation_guide.md)。

单独更新/卸载社区 triton 可能留下 backend 孤儿文件或删掉共享文件。受影响时在独立前缀恢复整套匹配版本；若必须就地修复，先记录包和文件来源、明确影响，再按该发行版官方恢复方式操作。修复后重测 import 与真实 kernel，不只看目录。

版本对比用干净环境，不用 `--system-site-packages` 加半套 `--no-deps` 叠加。用 sys.path、所有模块/扩展来源和 RECORD 验证；`triton.__file__` 单项相同不能证明没有混合。`--no-deps` 仅在依赖已经独立满足且核对过时用。

查 API 缺失时同时看目标 SHA 下 Python 层、`third_party/ascend/language/`、backend/compiler 与构建映射。2026-11-16 主线构建映射在仓根 setup.py；不要假定路径永久如此。缺 triton.experimental 可能是 vLLM/plugin 配对或初始化路径问题，不能承诺“装完插件自动修好”，也不先升级 triton。

最小 kernel 需覆盖尾块 mask 和非整齐长度，核对 shape/dtype/设备、同步及有限值；报告只声称该 kernel 通过。失败时保存原始栈与编译日志，区分 Python API、二进制混合、CANN 编译与运行阶段。
