---
name: tilelang-op-generator
description: >-
  This skill should be used when the user asks to write, generate, port,
  optimize, or fix the precision of a TileLang operator for Ascend NPU, from a
  natural-language description or an existing PyTorch/NumPy/Triton operator.
  Triggers include "write a softmax operator in TileLang", "generate a TileLang
  kernel for a [B, N] float16 input", and "migrate this op to Ascend with
  TileLang". Delivers the kernel, a layered golden test, and a Triton-Ascend
  same-NPU comparison.
version: 1.2.0
domain: ops
function: tilelang
tags:
  - tilelang
  - ascend
  - operator
  - code-generation
  - optimization
author: mindspeed-agent
compatibility: MindSpeed >= 0.1.0, CANN >= 9.1.0, TileLang-Ascend
targets-repo:
  - tilelang-ascend
---

# TileLang-Ascend 算子生成器

把用户的少量提示转成可直接在昇腾 NPU 上运行、精度通过且性能达标的高性能 TileLang 算子。

## 定位与边界

**做什么**：从一句自然语言需求出发，产出可在昇腾 NPU 上实跑验证的 TileLang 算子工程——
kernel、golden 分层测试、Triton-Ascend 同卡对比基线，四件产物成对交付。

**什么时候用**：用户要新写 / 生成 / 迁移 / 复刻算子到 TileLang；要把 PyTorch、NumPy 或 Triton
算子改写成 TileLang-Ascend；要修某个 TileLang kernel 的精度；要对已有 TileLang kernel 做性能优化。

**与兄弟 skill 的分工**（避免重复调用）：

| 兄弟 skill | 分工边界 |
| ----------- | --------- |
| `ops-design` / `ascendc-design` | 负责**方案与详细设计文档**（tiling 策略、内存规划、接口规格）；本 skill 负责把方案落成可跑的 TileLang 代码 |
| `triton-op-dev` | 负责 **Triton 算子本身的开发与调优**；本 skill 产出的 `{op}_triton.py` **只作同卡对照基线**，不替代、不接管 Triton 开发 |
| `ops-test-gen` / `ops-profiling` | 负责**独立测试用例生成**与**性能剖析**；本 skill 内建分层精度测试与性能冒烟，正式性能结论仍以 `msprof op` / ops-profiling 为准 |

## 0. 平台与验证范围（动手前先确认，别把一套数字套到所有卡上）

本 skill 的具体数字（UB 192KB / L1 512KB / L0C 128KB / 分形下限 / 物理核数 / 对齐要求）来自
**Ascend 910B 系列 + CANN 9.1.0 + TileLang-Ascend `ascendc_pto` 路线**的实测与源码取证。
换一个 SoC 或 die，这些数字**都不能默认沿用**——容量、核数、对齐都可能不同，套用会得到
"编译过但结果错"或"分配不超限却越界"这类最难查的故障。

所以生成代码前先取证，并打印一行证据：

```text
[HW-PROBE] soc=<型号> npu_arch=<架构号或 unknown> cores=<探测到的核数或 unknown>
           ub=<GetCoreMemSize(UB) 或 unknown> verified=<yes|no>
```

三个来源按可靠性排序：

1. **运行时接口**——`GetCoreMemSize(UB)` 返回该卡 UB 的真实可用字节数，比查表可靠。
2. **平台查询命令**——`npu-smi info -l` / `npu-smi info -t board` 取型号与 die。
   注意 `npu-smi` 的 Chip Name 是**商用名**，不能直接当架构号用。
3. **仓库内取证**——`tilelang/carver/arch/ascend.py` 的 `CHIP_SPECS`、`testing/` 下的分形断言脚本。

`verified=no` 时照常干活，但必须在交付说明里写明"未在本机复核平台差异"，
并把用到的容量/核数标注为"沿用 910B 口径"。

> 上游 CANN 的 TileLang 技能族把平台路由做成了独立能力（用 `get_npu_arch.py --json` 取
> `full_soc` + `npu_arch`，`2201 → Ascend910`、`3510 → Ascend950`，并禁止从目录名或 Chip Name 猜）。
> 本 skill 暂不内置该脚本（保持自包含）；若目标机装了那套工具，**优先用它取证再填 `[HW-PROBE]`**。

## 核心原则

1. **不凭记忆猜 API**。写任何 `T.*` 调用前先查 [references/api-reference.md](references/api-reference.md)；
   按算子类型先查 [references/op-patterns.md](references/op-patterns.md) 的配方。
2. **从配方入手，不从空白开始**。找到最接近的算子类别，改配方而不是新写结构。
3. **遵循硬件内存层级**。GM → L1/UB → L0A/L0B/L0C；UB 与 L1 之间没有通用直通路径，
   CV 交互走 GM workspace，少数专用直通路径见 [references/constraints.md](references/constraints.md)。
4. **默认 Developer 模式，性能关键路径用 Expert 原语（混合模式）**。
   mode/pass_configs 决策见 [references/programming-model.md](references/programming-model.md)。
5. **生成即验证**。kernel + test 成对产出，必须在 NPU 上实跑通过精度门槛才算完成；
   再跑 Triton 基线对比（同卡同数据）交叉验证精度并定位性能水位；性能目标另做一轮优化。

## 工作流

```text
需求解析 → 算子分类与方案设计 → 生成 kernel+test+Triton基线 → NPU 实跑验证 → Triton 同卡对比 → 性能优化(可选)
```

## 1. 需求解析：少量提示 → 完整规格

**只问缺失且无法推断的关键字段，其余全部用默认值**。用户给一句“写一个 softmax 算子”也要能直接产出。

| 字段 | 默认值 / 推断规则 | 何时才问 |
| ------ | ------------------ | --------- |
| 算子名 | 用户给出；或从功能描述推断，snake_case（目录名=函数名=文件名） | 无法确定时 |
| 数学公式 | 标准算子按语义推断（softmax/relu/gelu/silu/layernorm/rmsnorm/gemm/matmul/attention 等）；非标准/自定义公式无法推断 | 自定义公式时问一次 |
| 输入规格 | 未给 → `[B, N] float16`，B 为动态轴 | 用户明确要求特定 shape 才不覆盖 |
| 输出规格 | 与输入同 shape/dtype；公式另有规定时按公式 | 不明确且影响正确性时 |
| 编程模式 | Developer（或混合） | 仅当用户明确要求 Expert/手动控制 |
| 性能目标 | best-effort（与 PyTorch NPU 基线对比） | 用户给出目标则采用 |

解析完成后用 1 段话复述规格（算子名/公式/输入/输出/模式），再进入设计。不要长篇解释，直接干。

## 2. 算子分类与设计要点

| 类别 | 判别特征 | 核类型 | 配方位置 |
| ------ | --------- | -------- | --------- |
| 逐元素 | 无归约、无矩阵乘 | 纯 Vector（UB） | op-patterns.md §1 |
| 归约 | sum/mean/max/min over 某轴 | Vector（UB + reduce） | op-patterns.md §2 |
| 归一化 | softmax / rmsnorm / layernorm | Vector（reduce+广播） | op-patterns.md §3 |
| 矩阵乘 | gemm/matmul/linear | Cube（L1 + L0C + gemm_v0） | op-patterns.md §4 |
| 融合 | matmul+残差/bias/激活、attention | Cube+Vector 流水线 | op-patterns.md §5 |

设计时确定并记录（可简化为设计注释，不必单独文件）：block 大小（受 UB 192KB / L1 512KB / L0C 128KB
预算约束，**这三个数字与部分源码表冲突，取值前先读 constraints.md 的容量说明**）、
V 核切分（示例中惯用 `VEC_NUM=2` 行切分，注意它不是框架 API 而是各算子的局部常量）、
尾块策略（`T.ceildiv` + 动态切片，禁止 host padding）、循环结构（`T.serial`/`T.Pipelined`）、
同步策略（自动或手动）。

## 3. 代码生成

### 3.1 产物清单

| 产物 | 生成方式 |
| ------ | --------- |
| `custom/{op}/{op}.py` | 手写纯 kernel（`@tilelang.jit` + `pass_configs`），无 golden、无 `__main__` |
| `custom/{op}/test_{op}.py` | 复制 [assets/test_template.py](assets/test_template.py)，改算子名与 golden |
| `custom/{op}/{op}_triton.py` | 手写 Triton-Ascend 基线（同公式、同数据、同计时协议） |
| `custom/{op}/compare_{op}.py` | 复制 [assets/compare_template.py](assets/compare_template.py)，改算子名与 golden |
| `custom/compare_common.py` | 复制 [assets/compare_common.py](assets/compare_common.py)，**必做** |

**`custom/compare_common.py` 是必备公共资产**：`compare_{op}.py` 从它导入容差表、精度判定与计时函数，
缺了它对比脚本直接 `ModuleNotFoundError`。它在 `custom/` 下只放一份，各算子共用。
Triton 基线的写法要求、对比判定口径与实测坑位见 [references/triton-baseline.md](references/triton-baseline.md)。

### 3.2 模式与 pass_configs

按 [references/programming-model.md](references/programming-model.md) §2 的场景表选择。四个键**默认全为 False**，
不写就不开。前两个与算子类型无关，所有算子都开；后两个只在**同时含 Cube 与 Vector 工作**的算子上才有意义：

```python
# 含 Cube 的算子（GEMM / CV 融合 / FlashAttention）：四个全开
pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,        # 核内自动同步（所有算子）
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,  # 自动内存复用（所有算子）
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_COMBINE: True,  # 自动 C/V 分离（仅含 Cube 的算子）
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_SYNC: True,     # 核间自动同步（仅含 Cube 的算子）
}

# 纯 Vector 算子（elementwise / reduction / softmax / norm）：只开前两个
# 实测开 4 个与开 2 个输出逐字节相同（无收益）；而 CV_COMBINE 在 kernel 用到 T.alloc_var 时
# 存在"定义与使用被分到不同核"的已知风险 → 默认不开，遇异常先关它再排查。
pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
}
```

**判据只有一条：是否需要手动控制内存层级与同步**，不是"用了哪个 API"——`T.tile.*` 与
`T.reduce_*` 在两种模式下都能用。出现 `T.Scope` / `barrier_all` / `set_flag` / `workspace_idx` /
手动 `vid` 偏移即属于 Expert 或回退写法。

开 `AUTO_SYNC` 就不要手写 `T.barrier_all`；开 `AUTO_CV_COMBINE` 就不要手写 `T.Scope`。

### 3.3 正确性不变量（生成后逐条自查）

1. 内存层级合法：`T.copy` 走 GM↔L1/UB、L1→L0A/B、L0C→GM、UB↔UB；UB↔L1 没有通用直通路径，
   须经 workspace(GM) 中转，专用直通路径见 constraints.md。
2. 读写索引一致：V 核按 `vid * block_M // VEC_NUM` 切分时，load/compute/store 用同一基址。
3. 尾块安全：`T.ceildiv` 只决定块数、不裁剪 tile 内容；N 维与 M 维尾块都能由 lowering 自动裁剪
   （实测 N 尾块 `(64,130,block_N=128)` 与 M 尾块 9 组全 PASS）。显式写动态 region 时必须钳到非负
   `T.max(T.min(block, dim - off), 0)`——漏钳位且最后行块实际行数 `rem < block_M/2` 会得负 extent
   并报 507015（矩阵与错误原文见 constraints.md §9.1/§9.2）。
4. GEMM 分形：`block_M ≥ 16`、`block_N ≥ 16`；`block_K` 按 dtype 分档（fp16/bf16 ≥ 16、fp32 ≥ 8、
   int8 ≥ 32，见 [references/api-reference.md](references/api-reference.md) §4）。不满足会**结果错而不报错**。
5. host 侧只做：元数据视图（view/reshape/permute/expand）、输入准备（CPU 上生成数据）、kernel 调用、结果验证。
   禁止 `.contiguous()`/`.to(dtype)`/pad/cat 等真实数据搬运冒充算子实现。
6. **模板占位符必须全部替换**：`{op}` 未替换会 `SyntaxError`；`test_configs` 留空 = 模板直接打
   `[PRECISION_FAIL]` 并退出码 1（模板已把"零用例"判失败），但仍须自己确认用例表非空、
   且数出了 `[PRECISION_PASS]` 行——"判失败"只保证不会假通过，不保证你填的用例够。
7. **`T.Kernel` 的网格必须是一维**（三维网格不可用），多轴任务自己折算成一个轴；矩阵乘用 `T.gemm_v0`，
   `T.gemm` 在本分支可能不支持；`T.Pipelined` 的循环边界必须是编译期常量，动态边界改用 `T.serial`。
8. **`tilelang.disable_cache()` 只在 `main()` 内或 `if __name__ == "__main__":` 之下调用**——放文件顶部
   会连带影响同进程的其它算子，`cache.clear_cache()` 也不要用。
9. **`T.Parallel` 里不要用 `T.if_then_else`**：它阻止向量化，整段 `T.Parallel` 会静默退化成串行标量
   （不报错，只是慢几十倍）。条件逻辑用 `compare` + `select`，或有闭式解时做数学等价变换后全用 `T.tile.*`。

细节与坑位见 [references/constraints.md](references/constraints.md)；交付前的完整门禁见
[references/acceptance-checklist.md](references/acceptance-checklist.md)。

## 4. NPU 实跑验证

**测试必须真正在 NPU 上跑过**，不准只交付代码。

1. 本地能 `import tilelang` → 直接运行。
2. 本地无 NPU 环境 → 用 [scripts/remote_run.py](scripts/remote_run.py) 部署到远程昇腾机执行。
   目标机与运行环境由参数或环境变量给出（`--host`/`TILELANG_NPU_HOST`、`CANN_INSTALL_PATH`、
   `TILELANG_ASCEND_PATH`、`TILELANG_ENV_DIR`；各自默认值以 `python scripts/remote_run.py --help`
   为准，共享机与自有机器路径不同，**不要照抄别人的路径**）。三个路径可这样现查：

   ```bash
   # CANN toolkit（env_check.py 不给 --cann-path 时直接判该项 FAIL，
   # 只在失败后列出候选；不会替你自动选中）
   ls -d /usr/local/Ascend/ascend-toolkit/latest ~/Ascend/ascend-toolkit/latest \
         /mnt/share/*/cann/*/cann-*/ 2>/dev/null
   # TileLang-Ascend 仓库（找 set_env.sh）
   find / -maxdepth 4 -name set_env.sh -path '*tilelang*' 2>/dev/null
   # 远程 python venv（找 bin/activate）
   find / -maxdepth 4 -path '*bin/activate' -path '*tilelang*' 2>/dev/null
   ```

   运行前先 `npu-smi info` 选一张空闲卡，用 `ASCEND_RT_VISIBLE_DEVICES` 指定：

   ```bash
   export TILELANG_NPU_HOST=10.0.0.1                 # 昇腾机地址
   export CANN_INSTALL_PATH=/usr/local/Ascend/ascend-toolkit/latest
   export TILELANG_ASCEND_PATH=/opt/tilelang-ascend  # TileLang-Ascend 仓库路径
   export TILELANG_ENV_DIR=/opt/tilelang-env         # 远程 python venv 路径

   python scripts/env_check.py                       # 先自检：能 import tilelang、能看到 NPU 设备
   python scripts/remote_run.py --deploy custom/{op} \
     --cmd 'ASCEND_RT_VISIBLE_DEVICES=0 python test_{op}.py --level all'
   ```

   脚本会把 PATH 补全与 CANN / TileLang-Ascend / venv 的激活语句写进远程 bash 脚本，
   `--cmd` 里只写真正要执行的命令，避免在命令行里拼接长 `export ... && source ...`。
   远端落地目录默认取 `--deploy` 的最后一级（`custom/{op}` → `{op}`），
   需要自定义时用 `--workdir-name` 覆盖，它与 `--cmd` 的工作目录是同一个。
3. 判定标准（`--level` 取值 `l0`|`l1`|`l2`|`boundary`|`perf`|`all`，默认 `l0`）：
   **用例表非空**且数得出 N 行 `[PRECISION_PASS]`、退出码 0 = 通过。
   空表已由模板判失败（打印 `[PRECISION_FAIL]` + 退出码 1），所以**不该**再出现"只有 `Test Passed!`
   而没有任何 `[PRECISION_*]` 行"的日志；真看到了就是模板被改坏了，必须回填用例重跑。
   数得出的 `[PRECISION_PASS]` 行数必须**等于本次 `--level` 实际执行层的用例数**
   （`--level l0` 即 `len(test_configs["l0"])`，`--level all` 即 L0+L1 之和），少一行就说明有用例没跑到。
   退出码口径：`--level l0` 只把 L0 计入退出码，`--level l1` 只把 L1 计入；`--level all` 把 L0、L1
   与性能冒烟（perf）三层都计入，`perf_config` 未填时 `--level all` 直接失败并退出码 1；
   L2 与 Boundary 为非阻塞层，任何时候都不计入退出码；但**"非阻塞"不等于"可以不写"**：
   L2 至少要有 1 个非法 shape 与 1 个非法 dtype 用例（正确拒绝 = `[BOUNDARY_PASS]`，静默接受 =
   `[BOUNDARY_WARN]`），浮点算子的 Boundary 至少要有 1 个特殊值（±Inf/NaN）与 1 个接近 dtype 上界的极值。
   确实留空时打印 `[BOUNDARY_SKIP]`（而非 `PASS`），并**在交付说明里记为已知缺口**。
   性能冒烟在 `--level perf` 与 `--level all` 执行：预热 3 次、计时 20 次、wall-clock 并用
   `torch.npu.synchronize()` 包夹，输出一行 `[PERF]`。它**只是冒烟、不是性能结论**——单次 wall-clock
   数值随机器/卡/并发漂移，正式结论一律用 `msprof op`（见 §5）。
   **性能哨兵必须用最大 dtype + 最大 shape 的用例跑**，不得只测最小 case，也不得因耗时长而跳过——
   跳过就等于没有性能结论。
4. **覆盖维度是否达标由脚本判，不靠人工数**（在 NPU 上跑通之后、宣称"完成"之前必须过）：

   ```bash
   python scripts/check_coverage.py --test custom/{op}/test_{op}.py --category <类别>
   ```

   退出码 0 = 覆盖达标，1 = 有强制维度缺失（打印缺失清单），2 = 脚本自身错误。
   维度定义、各类别最低要求与 GEMM 的三轴非整除规则见
   [references/coverage-matrix.md](references/coverage-matrix.md)。**覆盖未达标不得宣称完成。**
   容差表、NaN/Inf 处理与"绝对 us 不可当达标线"的原因见 [references/testing.md](references/testing.md)。
5. 失败时按错误类别修复：编译错→API/参数；运行错→索引/同步；精度错→golden/容差；
   查 [references/constraints.md](references/constraints.md) 的故障速查。
6. 交付前逐条过 [references/acceptance-checklist.md](references/acceptance-checklist.md)，
   并打印其中的 `[DELIVERY]` 结论行——缺字段视为未交付。

## 4.5 Triton 同卡对比（交叉验证）

test 通过后，部署整个 `custom/` 目录并在 `{op}/` 下跑 `compare_{op}.py`：两实现各自对 golden 达标、
逐点互比 `matched_ratio ≥ 0.99`、并输出性能比值（TileLang/Triton）。全部 `[COMPARE-PRECISION_PASS]`
且退出码 0 = 通过。
填 `compare_configs` 时必须与 `test_{op}.py` 的 L0+L1 **逐条同值同序**——脚本开跑前会 import
`test_{op}` 核对，不一致或留空都直接失败；矩阵乘类算子还要同步扩 `make_inputs` / `run_case` /
`run_perf` 的签名。Triton-Ascend 的写法要求与实测坑位见 [references/triton-baseline.md](references/triton-baseline.md)。

## 5. 性能优化（用户要求高性能时）

先精度、后性能，一次只改一个优化点，改完立即复测精度+性能；性能用 `msprof op` 计时（禁止 Python/Torch
计时当结论）：

```bash
msprof op --kernel-name="main_kernel" --output=./msprof_output python <你的脚本>.py
```

对比基准优先用 Triton 基线（同协议实测，见 triton-baseline.md 的性能参考表）；
纯 Vector 算子差距大时先扫 block 大小（TileLang）与 BLOCK/num_warps（Triton），两边都调到各自最优再比。

**达标不是"感觉快了"，是五项可度量门禁**（完整表与度量方法见
[references/programming-model.md](references/programming-model.md) §6）：冗余搬运 = 0、单次 DMA 传满
（无逐行循环）、每 tile 算满 ≥ 80%、各级 buffer stage ≥ 2、实际参与计算的核数 / 可 launch 核数 ≥ 90%。
最后一项的两个方向都要防：任务数远大于核数时按核数 launch + 核内循环，任务数小于核数时
`min(block_num, core_num)`——**物理核数现场探、不要写死**。

常见优化点，按收益从高到低：

1. V 核并行（Developer 用 `threads=2` 自动并行；回退写法才是 `VEC_NUM=2` 行切分）——几乎所有算子都要做。
2. 消除 host 侧全量拷贝：`permute+contiguous` / `.to(dtype)` 下沉到 kernel 的三维分解与 `cast`。
3. 多级流水线（`T.Pipelined(range, num_stages=N)`，边界须为编译期常量）+ 双缓冲——GEMM/融合算子。
   注意**只分配两份 buffer 不等于双缓冲**，stage 之间必须配 `set_flag`/`wait_flag`。
4. C/V 自动分离 + 核间同步（4 个 pass_configs）——含 Cube 的算子。
5. 归约遍数融合（softmax 类 3-pass → 2-pass，GM 读量约 −33%）。
6. 分形对齐与 block 调优（在内存预算内把 block 调到分形倍数，并把每 tile 有效占比抬到 80% 以上）。
7. 减少 GM↔片上搬运、用 `T.tile.*` 复合原语（`mul_add_dst`/`axpy`/`relu`/`rsqrt`）替代多条基础指令
   与标量循环。融合会改变舍入路径，fp16/bf16 必须**重跑精度**。

**多个优化点同时待做时先写 `[ORDER-PLAN]`**，顺序规则：布局依赖（改 layout 的排在其消费者之前）→
数量依赖（涉及预算的排在改 buffer 数量的之后）→ 配置依赖（`pass_configs` 留到功能生效后再调）。

记录每轮 `[RESULT-#N] 优化点 | 精度 pass/fail | 性能 X us | 对比 +/-X%`，连续 3 轮无提升即停并上报。
逐条反模式（症状/根因/做法）见 [references/perf-antipatterns.md](references/perf-antipatterns.md)；
配方见 [references/op-patterns.md](references/op-patterns.md)。

## 子目录索引（按需加载，勿一次全读）

| 文件 | 何时读 |
| ------ | -------- |
| [references/api-reference.md](references/api-reference.md) | 写 kernel 时查 API 用法/签名 |
| [references/op-patterns.md](references/op-patterns.md) | 确定算子类别后取对应配方 |
| [references/programming-model.md](references/programming-model.md) | 选模式/pass_configs、Expert↔Developer 转换、五项性能门禁 |
| [references/constraints.md](references/constraints.md) | 生成前核对硬件约束；编译/运行/精度报错时排查 |
| [references/coverage-matrix.md](references/coverage-matrix.md) | 定测试用例、判断"测够了没"、GEMM 三轴非整除 |
| [references/acceptance-checklist.md](references/acceptance-checklist.md) | **交付前必读**，逐条勾选并打印 `[DELIVERY]` 结论 |
| [references/perf-antipatterns.md](references/perf-antipatterns.md) | 做性能优化、找瓶颈、优化后不见效 |
| [references/testing.md](references/testing.md) | 写测试、定精度标准、远程环境与运行方法 |
| [references/triton-baseline.md](references/triton-baseline.md) | 写 Triton 基线/对比脚本、解读对比结果、排查 Triton-Ascend 报错 |
| [assets/test_template.py](assets/test_template.py) | 生成 test 文件时复制模板 |
| [assets/compare_template.py](assets/compare_template.py) | 生成 compare 对比文件时复制模板 |
| [assets/compare_common.py](assets/compare_common.py) | 生成 `custom/compare_common.py` 公共资产时复制（对比流程必需） |
| [scripts/check_coverage.py](scripts/check_coverage.py) | 交付前校验覆盖维度是否达标（退出码 0/1/2） |
| [scripts/env_check.py](scripts/env_check.py) | 跑测试前自检远端环境（CANN / TileLang-Ascend / venv / NPU） |
| [scripts/remote_run.py](scripts/remote_run.py) | 本地无 NPU、需要远程部署运行 |
