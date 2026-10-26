# 交付验收清单（逐项勾选，不得口头"已检查"）

本清单是"算子做完了"的唯一定义。**任何一项未通过就不得回复"已完成"**；确实做不到的项，
必须显式写成"已知缺口：<项号> — <原因> — <影响>"并一起交付，不能沉默跳过。

判定方式分三类，能自动化的不要靠眼睛：

- **grep 判据**：对 `custom/{op}/` 下的产物直接检索，命中即通过。
- **命令判据**：给出的命令退出码为 0 才算通过。
- **证据判据**：必须先打印规定的标记块，再执行后续动作。

---

## 0. 前置（最先确认，未过则不必往下走）

| # | 检查项 | 判定方式 | 不通过的后果 |
| --- | -------- | --------- | ------------ |
| 0.1 | 核心计算全部在 kernel 内 | 逐行读 host 侧代码；对照 [constraints.md](constraints.md) §6 六条红线 | 算子名不副实，对比与性能结论全部失效 |
| 0.2 | host 侧无隐式 aclnn 调用 | 检索 `.contiguous()`、`.to(`、`torch.cat`、`torch.stack`、`F.pad`、`.clone()`、`.copy_()`、`x[:] =` | 隐式 `aclnnCopy`/`aclnnCast` 污染性能与精度归因 |
| 0.3 | 输出侧无"切片后 reshape" | 若 kernel 输出 padded shape，检索 host 侧是否用 `y[...:S]` + `reshape` 裁剪 | 切片后非 contiguous，reshape 触发隐式拷贝；应让 kernel 直接输出原 shape（`T.copy` + `pad_value`） |
| 0.4 | 测试数据准备不走 aclnn | 随机数/特殊值/dtype 转换/物理重排均在 CPU 完成，链路只有 H2D→kernel→D2H | 报 `aclnnInplaceRandom` 一类错误时**不得归因 kernel**，那是测试准备错 |
| 0.5 | kernel 与测试分文件 | `{op}.py` 内检索 `def golden`、`if __name__`、`pytest` → 应为 0 命中 | 违反"四件套"约定，也让 kernel 无法被 compare 复用 |
| 0.6 | 模板占位符全部替换 | 检索 `{op}` 字面量 → 应为 0 命中 | `SyntaxError`，或更隐蔽的是用例表空转 |
| 0.7 | 打印 host 侧证据块 | 输出 `[HOST-METADATA-AUDIT]` 行，列出 0.1–0.4 四项的检索结果（命中数 + 判定） | 无证据即视为未检查 |

`[HOST-METADATA-AUDIT]` 必需字段（一行一条，缺失即视为未做）：

```text
[HOST-METADATA-AUDIT] contiguous=<n> .to= <n> cat/stack=<n> pad=<n> inplace=<n> out_slice_reshape=<n>
[HOST-METADATA-AUDIT] verdict=<PASS|FAIL> note=<命中的具体位置 file:line>
```

## 1. 功能正确性

| # | 检查项 | 判定方式 |
| --- | -------- | --------- |
| 1.1 | `out_idx` 与函数签名里输出参数的位置一致 | 数一遍签名参数下标与 `out_idx` 列表 |
| 1.2 | `T.Kernel` 是一维网格 | 检索 `T.Kernel(`，确认第一个实参是标量表达式、解包个数为 1 或 2 |
| 1.3 | V 核分工两种写法各自自洽 | Developer：`threads=2` + 单轴 `as (cid)`，全文无 `vid` 偏移；回退：`as (cid, vid)` 且 load/compute/store 用同一 `row` 基址 |
| 1.4 | 片上预算没超 | 按 dtype 字节数累加各层 buffer（含 `num_stages`、双缓冲、broadcast 临时 buffer），与 [constraints.md](constraints.md) §1 的容量逐层比 |
| 1.5 | 同步策略与模式匹配 | 开 `AUTO_SYNC` 时全文无 `T.barrier_all`；开 `AUTO_CV_COMBINE` 时全文无 `T.Scope`；Expert 模式则必须有 `T.Scope("V")` 与显式同步 |
| 1.6 | GEMM 首次累加清零 | 检索 `T.gemm_v0(`，确认有 `init=` 且形态为 `init=(k == 0)`／`init=True` |
| 1.7 | GEMM block 满足分形 | `block_M/block_N ≥ 16`，且 `block_K` 不小于该 dtype 的下限（[constraints.md](constraints.md) §2） |
| 1.8 | 没有静默标量回退 | 对每条 dtype 路径跑一次 `kernel.get_kernel_source()`，确认出现向量指令而非满屏 `GetValue/SetValue` |

## 2. Golden 与精度

| # | 检查项 | 判定方式 |
| --- | -------- | --------- |
| 2.1 | Golden 与算子语义一致 | 迁移类必须复用原算子的 golden 实现，不得"重新推导一版" |
| 2.2 | 输出 shape 与原算子对齐 | 需要 transpose 时在 golden 内处理，不在 host 侧改 kernel 输出 |
| 2.3 | 容差表两处逐值一致 | `assets/test_template.py` 的 `get_precision` 与 `assets/compare_common.py` 的 `TOL_TABLE` 逐行比对；未知 dtype 两处都必须抛错 |
| 2.4 | NaN/Inf 位置敏感验证 | 有限值 + 稀疏特殊值的混合输入；先比 NaN/±Inf 三个 mask，再在双方有限位置算容差；禁止全 NaN 或仅 `equal_nan=True` 作为唯一门禁 |
| 2.5 | 双门限都判 | `matched_ratio ≥ required` **且** `max_abs ≤ limit`，两个条件缺一不可 |

## 3. 覆盖矩阵

| # | 检查项 | 判定方式 |
| --- | -------- | --------- |
| 3.1 | 覆盖维度达到该算子类别的最低要求 | 按 [coverage-matrix.md](coverage-matrix.md) 的类别表核对 |
| 3.2 | 非对齐 shape 真实存在 | 有尾块余数为 1 的用例；GEMM 的 M/N/K **三轴**各自都有非对齐用例 |
| 3.3 | L2 负向用例非空 | 至少有 1 个非法 shape 与 1 个非法 dtype；正确抛异常 = `[BOUNDARY_PASS]` |
| 3.4 | Boundary 特殊值用例非空（浮点算子） | 至少 1 个 ±Inf 或 NaN 用例、1 个接近 dtype 上界的极值用例 |
| 3.5 | 空表不算通过 | 若某层用例表确实为空，打印 `[BOUNDARY_SKIP]`，并在交付说明里写"已知缺口：<层> 无用例" |

整型算子可豁免 3.4（无浮点特殊值），但必须在测试文件里写明豁免理由，不能只是不写。

## 4. 上库前收尾

| # | 检查项 | 判定方式 |
| --- | -------- | --------- |
| 4.1 | `tilelang.disable_cache()` 位置正确 | 只在 `main()` 内或 `if __name__ == "__main__":` 之下；文件顶部全局调用与 `cache.clear_cache()` 都不允许（会影响同进程其它算子） |
| 4.2 | 注释语言统一 | 交付代码里无调试期中文注释残留（对外产物用英文注释） |
| 4.3 | `T.Tensor` 参数带 `# type: ignore` | 避免 Pylance 误报，非功能问题但影响评审观感 |
| 4.4 | 分层异常隔离 | L0/L1 的 `except` 打 `[PRECISION_FAIL]` 并记 `ok=False` 但**不中断本层其余用例**；L2/Boundary 失败打 `[BOUNDARY_WARN]` 后继续 |
| 4.5 | 标记输出齐全 | 每个用例一行标记，含 shape/dtype 与数值；只打 `Test Passed!` 而无 `[PRECISION_*]` 行 = 用例表空转，判失败 |
| 4.6 | 退出码语义正确 | `--level l0` 只计 L0，`--level l1` 只计 L1，`--level all` 计 L0+L1+perf；L2/Boundary 任何时候都不计 |
| 4.7 | `[PRECISION_PASS]` 行数 = 本次执行层的用例数 | 数一遍：`--level l0` 对 `len(test_configs["l0"])`、`--level all` 对 L0+L1；少一行说明有用例没跑到 |
| 4.8 | 代码格式门禁 | `ruff check custom/{op}/` 与 `ruff format --check custom/{op}/` 均退出码 0 |
| 4.9 | 对比脚本可用（若交付） | `compare_{op}.py` 的 `compare_configs` 与 `test_{op}.py` 的 L0+L1 **逐条同值同序** |

## 5. 融合算子专项

| # | 检查项 | 判定方式 |
| --- | -------- | --------- |
| 5.1 | CV 交互写法与模式匹配 | Developer：无 `workspace_idx`、签名无 workspace 参数、C↔V 走片上 `T.copy`；回退：`workspace_idx` 与签名参数一致、C 核写 V 核读 |
| 5.2 | workspace 索引基准统一 | 回退写法里读写都用同一个 `actual_row = base + vid * rows_per_vec + row`；检索是否存在"写用 `actual_row`、读用不带 `vid` 的下标"这类错位 |
| 5.3 | Cube 核不参与 vid 切分 | Cube 侧 `T.copy` 读的是完整 `block_N`，不得出现 `vid *` 偏移 |
| 5.4 | 可忽略告警已识别 | `Warning: Cube loop times (...) is not enough to catch up vec loop times (...)` 在 `AUTO_CV_SYNC` 下属正常，不要为消它去改算法 |

---

## 6. 性能（仅在用户要求性能目标时适用）

| # | 检查项 | 判定方式 |
| --- | -------- | --------- |
| 6.1 | 精度先于性能 | 精度未全过时禁止开始调优 |
| 6.2 | 性能哨兵实跑 | 用**最大 dtype + 最大 shape** 的用例计时；不得只测最小 case，也不得因耗时长而 skip |
| 6.3 | 计时口径唯一 | 结论数字必须来自 `msprof op`；Python/Torch 计时只能用于粗筛，不得作为结论 |
| 6.4 | 一次只改一个点 | 每轮 `[RESULT-#N] 优化点 \| 精度 \| 性能 \| 对比`，多改点混在一轮里则结论不可归因 |
| 6.5 | 指标门禁达标 | 见 [programming-model.md](programming-model.md) §6 的五项可度量门禁 |
| 6.6 | 收敛后停 | 连续 3 轮无提升即停并上报，不要无限试 |
| 6.7 | 实施有顺序 | 多个优化点同时待做时先写 `[ORDER-PLAN]`（布局依赖 → 数量依赖 → 配置依赖） |

---

## 交付时必须附的一句话结论

按下面格式给出，缺字段视为未交付：

```text
[DELIVERY] op=<name> dtype=<dtypes> shape=<L0/L1 用例数>
           precision=<PASS/FAIL> boundary=<PASS/WARN/SKIP + 缺口>
           perf=<msprof 数值 or 未做> extra=<已知缺口列表 or none>
```
