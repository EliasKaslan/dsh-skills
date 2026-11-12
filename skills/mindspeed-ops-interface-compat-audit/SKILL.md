---
name: mindspeed-ops-interface-compat-audit
description: MindSpeed-Ops 仓面核查：跨仓接口兼容（AST 盘点/周边仓实跑/缺口报告）+ 算子增量（近 N 天新增哪些算子、四件套判定）。
whenToUse: 模型看不到本节；触发词全在 description。跨仓接口兼容核查与报告发送时加载。
---

# MindSpeed-Ops 跨仓接口兼容性核查

## 何时调用

**加载本 skill 当：**
- 用户说"检查 MindSpeed-Ops 最新 master 对周边组件调用的接口是否正确 / 周边仓有没有用 Ops 接口 / 这些调用兼容吗 / 出一份接口兼容报告发黄区"。
- 下游仓（MindSpeed-Bridge、FSDPTurbo、MindSpeed-MM）升级 Ops 前要判"会不会坏"。
- 要复现"AST 盘点 + 下游仓 import 校验 + NPU 栈实跑"这条链路，或对比 master 与 26.2.0 的公开签名。
- 有人说"这个形状/这个 TA 版本必炸"，要判是 Ops 缺陷还是本方探针构造不当（见 §6.1）。
- 静态扫出一堆"模块/符号缺失"，要判是不是解析器的假阳性（见 §4.1）。
- 要回答"Ops 仓最近一个月/这个版本有没有新增算子、新增了哪些"，或核对算子清单增量（见 §10）。

**不要用本 skill（转交）：**
- 要装 CANN/torch_npu/triton 环境、跑 UT 或 ATK 精度 → `mindspeed-ops-smoke`
- 要给 Ops 仓提 PR、判门禁 → `gitcode-pr-flow`
- 只审单个 PR 改动是否等价 → `pr-change-equivalence-audit`

**前置**：能 `git clone` gitcode 的 Ascend 仓；有一台装好配套栈的昇腾机（默认 192.168.13.188，Windows 侧 ssh 用 admin 会被拒，走 `_recon/rsh.py` 的 paramiko 通道）。／ **后继**：报告落 `reports/`，按黄区转发格式发 `xumingzhe4@huawei.com`。

## 1. 取基线（只读）

```bash
git -C <repo> fetch origin master 26.2.0
git -C <repo> worktree add --detach <ws>/_master  origin/master
git -C <repo> worktree add --detach <ws>/_v2620  origin/26.2.0
git -C <repo> log -1 --format='%H %ci %s' origin/master
```

判据：master 的 commit 时间必须晚于 26.2.0 分支头；仓库只有 `v26.1.0` 标签，26.2.0 只是分支。

坑：**`--depth 1` 克隆会让版本归因失效。** 动手前先确认

```bash
git -C <repo> rev-parse --is-shallow-repository    # true = 浅克隆
```

`true` 时 `git log`/`git blame` 只看到 1 个 commit，**无法归因"版本何时从 X 退到 Y"**；此时只比对 `_master` 与 `_v2620` 两侧树内容（§2、§7 本来够用），报告里对"何时/被谁改的"一律标「未归因」。确需归因再 `git fetch --unshallow`（体积大，别默认做）。

## 2. 盘点 Ops 对外部组件的调用面

对 `_master/mindspeed_ops/**/*.py` 做 AST 扫描，收集根节点为 `torch`、`torch_npu`、`triton`、`tl`、`tle`、`tilelang`、`atb` 的属性链与 import，输出「文件 → 路径 → 行号」的 JSON。

要点：
- 只扫 Python；`csrc/` 是 C++/CMake，单独看版本门。
- 统计 `torch.ops.mindspeed_ops.*`（本仓注册）与 `torch.ops.npu.*`（torch_npu 自带）要分开，前者缺 `.so` 时不存在（判"存在"的口径见 §4.1-4）。
- 属性路径**条数随 master 演进，不能写死**：只把它当量级参照（`tl.*` 占大头，`tle.*` 极少），结论里写"涉及哪些组件族"，不写具体条数。
- 属性链解析优先「属性取用」而非 `import_module`（`triton.runtime.driver` 这类实例名会被误判成子模块，见 §4.1-3）。

## 3. 调研周边仓（真实调用面，不是字符串）

固定清单（均为 `master`）：MindSpeed、MindSpeed-LLM、MindSpeed-MM、MindSpeed-RL、MindSpeed-Bridge、FSDPTurbo、MindSpeed-Agent、ModelZoo-PyTorch、MindSpeed-Core-MS、FSDPTraining。

```bash
git clone --depth 1 https://gitcode.com/Ascend/<repo>.git <callers>/<repo>
git -C <callers>/<repo> grep -n -I -E '^\s*(from|import)\s+mindspeed_ops' -- '*.py'
git -C <callers>/<repo> grep -n -I -i 'MindSpeed-Ops' -- .
```

坑：
- **MindSpeed 仓里 `mindspeed_ops` 全是局部变量**（`mindspeed_ops = XxxOpBuilder().load()`）或文档，真实 import = 0；它用的是自己的 `torch.ops.mindspeed.*` 命名空间，别混。计数必须行首锚定 `^\s*(from|import)`，否则会把局部变量和文档数成消费方。
- 只看 install 文档/CI 的仓（FSDPTraining、MindSpeed-Agent）不算消费方。
- 消费方名单与"import 条数/符号数/调用点数"每轮都会变：**名单可以进结论，计数只作形态参照**（典型形态：Bridge 数量最多且会伸到 `arch32/arch35` 内部模块；FSDPTurbo 全走 `api.triton`；MM 只碰 `causal_conv1d` 默认路径）。

## 4. 校验 import、符号与签名

用 AST 而非 import（Windows 侧没有 torch_npu）：解析每个消费方文件里 `from mindspeed_ops... import ...`，在 `_master/mindspeed_ops/` 里按模块路径找文件，核对：

1. 模块是否存在（`x/y.py` 或 `x/y/__init__.py`）；
2. 符号是否存在——**模块顶层 `Assign`/`AnnAssign` 也算导出**（否则 `partial(...)` 形式的函数会误报缺失，见 §4.1-1）；
3. 调用点关键字参数是否被目标签名接受——**同名符号若在 `arch32`/`arch35` 各有一份，必须逐分支各自判定**，不能"任一接受即通过"（见 §4.1-2）。

判定口径：`missing modules = 0`、`missing symbols = 0`、`unknown kwargs = 0`（**先按 §4.1 排掉假阳性再计数**）才算名称级兼容；再对消费方所用的公开函数做 master↔26.2.0 签名差分，只允许私有 helper 变化。名称级兼容 ≠ 运行期可用，实跑要求见 §5.1。

## 4.1 静态解析的假阳性清单（会直接把结论写反）

AST 结论落地前先过这六道闸，否则"缺失/未知 kwargs"大半是解析器的错：

1. **顶层 `Assign` 必须算导出。** `mindspeed_ops/api/triton/utils.py:228-229` 的 `autocast_custom_fwd/bwd = functools.partial(torch.amp.custom_fwd, ...)` 是模块级赋值，不是 `def`；只收 `FunctionDef`/`ClassDef` 会把它们误报缺失。口径：模块顶层 `Assign`/`AnnAssign` 的所有 `Name` target 都算导出。
2. **同名符号在 `arch32`/`arch35` 各一份时，kwargs 必须逐分支判定。** `prepare_wy_repr_bwd` 在 `arch32/triton/gdn/wy_fast.py:343`（**有** `chunk_size`）与 `arch35/triton/gdn/prepare_wy_repr_bwd.py:198`（**没有** `chunk_size`，多 `chunk_indices`/`use_exp2`；而且**位置参数顺序不同**——arch32 第 3 位是 `g`，arch35 第 3 位是 `beta`）各一份。旧口径"对每个候选都试、任一接受即通过"是错的：运行时只走一个分支，必须按设备/分支逐个绑定、逐分支各记一行 PASS/FAIL，否则会把真缺陷吃掉。
3. **`triton.runtime.driver` 是 `DriverConfig` 实例，不是子模块。** 按 `import_module("triton.runtime.driver")` 解析会假报 MISSING。解析顺序改「属性优先、模块其次」：先 `hasattr(父模块, 名)`，再 `import_module`；纯静态时先看父模块源码里有没有 `driver = ...` 赋值。
4. **`hasattr(torch.ops, "mindspeed_ops")` 为 True 只是惰性命名空间，不代表算子存在。** 必须以「`getattr(torch.ops.mindspeed_ops, <op>)` 不抛」或 `.so` 已加载为准，否则会把没编译的自定义算子记成"存在"。
5. **TA 里 `extract_slice`/`insert_slice`/`get_element` 在 `triton.language.extra.cann.extension`，仓内 shim 会回挂到 `tl`。** 直接读 `tl/__init__.py` 的导出名会误报几十次"缺失"；命中 shim 即视为可用。已知 shim：`arch32/triton/solve_tril.py:9-20`、`arch32/triton/convolution.py:19-22`、`arch32/triton/mhc/post_bmm2.py:8-11`（都是 `from ...extension import ...` + `tl.xxx = xxx`）。判定：先 grep `tl\.(extract_slice|insert_slice|get_element)\s*=`，命中的文件不算缺失。
6. **`mindspeed_ops` 也可能只是局部变量**（MindSpeed 仓），见 §3 的锚定 grep；不锚定会把文档与 `xxxOpBuilder().load()` 数成 import。

> 行号会随版本漂移：判定时以符号名 grep 为准，file:line 只作定位线索。

## 5. 运行时冒烟（配套栈）

```bash
source /home/x00886548/ms2620/activate_ms2620.sh
export PYTHONPATH=/tmp/msops_master   # git clone master 到远端
python -c "import mindspeed_ops, sys; print(mindspeed_ops.__file__); print(sys.path[:3])"
python - <<'PY'
import importlib, os
mods=[]
for d,ds,fs in os.walk("/tmp/msops_master/mindspeed_ops"):
    ds[:] = [x for x in ds if x not in {"__pycache__","csrc"}]
    mods += [os.path.join(d,f)[:-3].replace("/",".") for f in fs if f.endswith(".py") and not f.startswith("__")]
fail={}
for m in mods:
    try: importlib.import_module(m)
    except Exception as e: fail[m]=f"{type(e).__name__}: {e}"
print(len(mods), "modules", len(fail), "fail", fail)
PY
```

**先确认 `mindspeed_ops.__file__` 指向 `PYTHONPATH` 里的源码目录**（如 `/tmp/msops_master/mindspeed_ops/__init__.py`）。若指向 `site-packages` 或某个 whl 解出的目录，说明环境里装过 whl 且优先级高于源码 → 这一轮测的是旧 whl，**整轮实测无效**；处置：`pip uninstall -y mindspeed_ops` 或把源码目录放到 `PYTHONPATH` 最前，再复核一次。

期望：**整树模块导入，唯一预期失败是 tilelang 可选依赖**——未装 tilelang 时 `arch32.tilelang.*` 报 `ModuleNotFoundError` 属预期，不是缺陷；`api.*` 应全通过。**判口径是「失败集合 ⊆ {tilelang 相关}」，不是「N 个模块里仅 X 失败」**：模块总数每轮都不同，写死数字会让下一轮把正常增长误判成回归。

再跑三个真实算子（形状照抄下游，别自己编）：

```python
from mindspeed_ops.api.triton.l2norm import l2norm_fwd
l2norm_fwd(torch.randn(2,128,4,64, dtype=torch.bfloat16, device="npu"))
from mindspeed_ops.api.triton.cumsum import chunk_local_cumsum
chunk_local_cumsum(torch.randn(2,128,4, device="npu"), chunk_size=64)
from mindspeed_ops.api.triton.convolution import causal_conv1d
causal_conv1d(x=torch.randn(2,128,64, dtype=torch.bfloat16, device="npu"),
              weight=torch.randn(4,64, dtype=torch.bfloat16, device="npu"), activation="silu")
```

坑：
- `import mindspeed_ops` 会打印「未找到 `mindspeed_ops_C*.so`」WARNING，源码方式这是预期，不是失败。
- A3 设备名 `Ascend910_9382`；`is_arch35()` 返回 False 才对（决定走 `arch32` 分支，见 §4.1-2）。
- 机器负载常年 200+，一次只跑一小段，别起全量 UT。

## 5.1 运行期才暴露的三类接口断点（静态检查永远看不见）

"模块在 + 符号在 + kwargs 能绑"只等于**名称级兼容**。下面三类必须实跑才现形，本 skill 的增量主要在这里：

| 类型 | 长什么样 | master 实例（行号会漂移，按符号名找） |
|---|---|---|
| ① 签名保留但实现无条件抛错 | 形参还在、默认值还是 `None`，"按默认值调"能过；一按消费方真实用法传值就抛 | `chunk_gated_delta_rule_fwd_h` 的 `initial_state` 仍在签名第 6 位（`arch32/triton/gdn/chunk_gated_delta_rule_fwd_h.py:246`），实现 `:253` 直接 `raise ValueError("... does not support initial_state.")`；同函数 `gk`(`:256`)、`save_new_value=False`(`:259`) 同样抛 |
| ② 参数未实现 | 形参在、声明在，函数体直接 `NotImplementedError`；消费方还显式传这个值 | `chunk_local_cumsum(head_first=True)` → `api/triton/cumsum.py:178` `raise NotImplementedError("head_first is not supported")`；FSDPTurbo 的 `chunk_local_cumsum_auto` 在**Triton 回退分支**原样透传（`fsdp_turbo/ops/npu/chunk_gdn_ascendc.py:201-207`），调用方 `:340`/`:583` 显式传 `True` → 回退即炸，走 AscendC 分支则绕过 |
| ③ tiling 预算超限 | 签名与 dtype 都正常，只有"形状 + dtype"的**合取条件**才触发 UB overflow / 编译失败 | `prepare_wy_repr_bwd` 的 `chunk_size=64` 且 fp32 `beta` 且 `K=V≠128`，见 §6.1 |

**同一个调用点挂不挂，取决于它内部的哪条分支被走到**（表里 ② 就是：AscendC 分支绕过、只有 Triton 回退分支才炸）。写"必挂"之前先确认该分支真的会走——同一函数里的 `_auto` 包装、`if _should_use_*` 分流都会让静态结论失效。同理，表里的行号会漂移，以符号名 grep 为准。

**做法：每个消费方挑 2~4 个真实调用点（不是自己编的形状）**

1. 从下游文件里**原样抄** kwargs 与形状，连同 `beta`/`g` 的 dtype、device、是否非连续一起抄；
2. 每个调用点验四件事：**返回结构**（元组长度、`None` 在第几位、各元素 dtype/shape）、**是否原地改写输入**（调用前 `clone()`，调用后比对）、**是否接受非连续输入**（传 `.transpose()`/切片视图，别先 `.contiguous()` 掩掉问题）、**异常原文**（`raise` 的文案整句抄进报告，回给上游时比"报错了"有用）；
3. 没实跑过的符号，报告里一律标「名称级」，不许写"兼容"。

## 6. 低版本组件核对

消费方常把 Ops master 装进更老的栈，要单独核对：
```bash
pip download --no-deps --dest /tmp/ta triton-ascend==3.2.1 \
  --extra-index-url https://triton-ascend.osinfra.cn/pypi/simple
unzip -q /tmp/ta/triton_ascend-3.2.1-*.whl 'triton/language/*' -d /tmp/ta321
```

用 AST 解析 `triton/language/__init__.py`、`core.py`、`standard.py`、`math.py`、`extra/cann/extension/__init__.py` 的导出名，与第 2 步的 `tl.*` 集合比对（shim 回挂规则见 §4.1-5）。torch_npu 2.9.0 同理下载 wheel 查 `torch_npu/utils/custom_ops.py` 里 `npu_rms_norm`、`npu_rms_norm_backward`、`npu_rotary_mul` 是否定义。

## 6.1 按 TA 版本分栈实跑（必做，兼容性不是单调的）

同一份 master、同一形状，换 TA 版本结论会翻转（A3 + CANN 9.2.0 实测）：

| TA | Bridge GDN 反向 | 现象 |
|---|---|---|
| 3.2.1 | FAIL | `chunk_gated_delta_rule_bwd_dhu` 模块级 `@triton.autotune` 报 `ValueError: Number of parameters exceeds the number of available axes.` |
| 3.2.2 | PASS | 与 `requirements.txt` 的 `triton-ascend==3.2.2` 一致 |
| 3.6.0 | FAIL（**仅合取条件**） | `prepare_wy_repr_bwd`：`chunk_size=64`（即 `BT`，`arch32/triton/gdn/wy_fast.py:361`）**且** `beta` 为 fp32 **且** `K=V≠128`，三者同时成立才报 UB overflow（fp32-beta 探针实例 requires 2,891,776 > 1,572,864 bits）。`beta` 换成与张量同 dtype 后 K=V=64/128 全 PASS；`chunk_size` 取 32 也可绕过。根因：`:364-365` 硬编码 `BK=128`/`BV=64`（对比同文件 fwd 路径 `:306-307` 的 `BK=BV=128`）。T/H/B/varlen/`g` dtype 全无关 |

做法：每个版本建 `python -m venv --system-site-packages /tmp/taXXXvenv`，`pip install --no-deps triton-ascend==X`，同一 harness 换 venv 的 python 跑；`triton.__version__` 在 3.2.x 都报 3.2.0 属正常。下游声明栈（Bridge 钉 3.2.1）必须单独跑，不能拿配套栈的结果替代。

**任何"某形状必炸"的结论，必须先做单变量扫描再写进报告。** 做法：固定其余变量，一次只改一个（`K`/`V`/`chunk_size`/`beta` dtype/`T`/`H`/`B`/varlen/`g` dtype），列出几十格 PASS/FAIL 矩阵找出真实触发条件（常常是**合取**而不是单点），再用"只把可疑变量改回去"的对照组确认一次；最后回仓内 UT 看该形状用的 dtype/布局是否与你一致。否则会把"我方探针构造不当"写成 Ops 缺陷——真实发生过：探针传 fp32 `beta`，而仓内 UT 传的是与张量同 dtype 的 `beta`，于是一个"合取条件触发"被误记成"V=64/chunk=64 必炸"。

`fla_npu` 依赖同理：wheel 的 `manylinux_2_34` 在本机 pip 被拒，改用 `manylinux_2_17` 的 a3 wheel；AscendC 算子报 `aclnn...GetWorkspaceSize failed: 161002` 属 fla_npu/环境问题，不要记到 Ops 头上。

## 7. 版本契约核查（最容易被忽略，也最容易出问题）

把八处声明摆到一张表里**逐字比对**（同一行只放同一个组件，值不同即登记）：

| # | 来源 | 看什么 |
|---|---|---|
| 1 | `requirements.txt` | `triton-ascend` 的 `==` 钉法、`torch-npu` 有无约束 |
| 2 | `pyproject.toml` | 与 requirements 是否同值（同组件两处不同值 = 契约自相矛盾） |
| 3 | `docker/Dockerfile` | `BASE_IMAGE_VERSION`、`TORCH_VERSION`、`TORCH_NPU_VERSION`、`TRITON_ASCEND_VERSION` 默认值 |
| 4 | `docker/OVERVIEW.md`、`OVERVIEW.zh.md` | 参数表默认值是否与 Dockerfile 一致（中英两版也要对齐） |
| 5 | `docs/{zh,en}/install_guide.md` | 配套表与示例 tag |
| 6 | `docs/{zh,en}/release_notes_ops.md` | 已发版配套声明 |
| 7 | `mindspeed_ops/csrc/version.info` | `Version=` 与 required 下限 |
| 8 | `mindspeed_ops/csrc/cmake/config.cmake:198-199` | `option(CHECK_COMPATIBLE ... ON)` 紧跟 `set(CHECK_COMPATIBLE OFF)` = 校验分支永远进不去，是死代码 |

高概率命中的问题：
- 同一组件在八处写成多个值（CANN、TA 都出现过）；
- `config.cmake` 的兼容性自检是死代码（第 8 行）；
- 包没有 `__version__`，`setup.py` 的 `version=os.environ.get("MINDSPEED_OPS_VERSION", "26.2.0")` 让 master 仍自称 26.2.0；
- `mindspeed_ops/api/__init__.py`、`api/triton/__init__.py` 都是 0 字节，没有 `__all__`，下游全靠深路径 import。

**"master 停在旧基线、文档却已写新配套"是常态，别急着记成文档错误。** 判据只有一条：**同一处的同值，在 26.2.0 分支上是否已是配套值**——在分支 worktree 上跑

```bash
git -C <ws>/_v2620 grep -n -E 'CANN|9\.2\.0|triton-ascend|3\.6\.0' -- requirements.txt pyproject.toml docker docs
```

- 分支上已是配套值、master 不是 → **master 落后**（版本回退或未合入），报告写"master 落后于 26.2.0，需回补"，不写成文档错；
- 两侧同值却与官方配套表不符 → 才是文档/契约真错；
- 两侧都拿不到归因（浅克隆，见 §1）→ 只写"与分支不一致"，不猜原因。

## 8. 出报告并发黄区

报告落 `reports/YYYY-MM-DD-mindspeed-ops-master-interface-compat.md`：结论摘要 → 基线 → Ops→组件 → 组件→Ops → 问题清单（P0/P1/P2，每条带 file:line）→ 建议 → 复现命令。接口断点按 §5.1 三类分栏，实跑过的标"实跑"，其余标"名称级"。

发信固定只发 `xumingzhe4@huawei.com`（黄区）；要回环验证就 BCC `3248569436@qq.com`。**必须是转发形态**（普通格式会在收件侧被拦，而工具照样返回成功）：

- 主题：`转发：<报告名>（YYYY-MM-DD）`
- `text` 首行 `【AI 代发】`，紧跟 `-------- 转发的邮件 --------` 四要素（发件人 / 发送时间 / 收件人 / 主题），**发送时间用发送当下的真实时间，别手写估计值**；
- `html` 用同一份结论渲染成表格；
- 附件挂报告 `.md`。

发完验证：`Sent Messages` 有副本（uid + 体积）+ `INBOX` 有 BCC 回环；工具返回 `已发送` 不等于对方已收到。

## 9. 判定口径（写结论时照这个说）

- **兼容**：模块/符号存在 + 关键字可绑定（逐分支）+ 位置参数不越界 +（公开函数）26.2.0→master 签名无变化 + **已按消费方真实 kwargs/形状实跑通过**。
- **名称级通过**：只验证了符号存在，没实跑——报告里必须标「名称级/未实跑」，不能写成"兼容"。
- **运行期断点**：签名能绑但实现抛错/未实现/预算超限（§5.1），单列，不算"兼容"，也不算文档缺失。
- **未验证**：aclnn/catlass 自定义算子依赖编译产物 `.so`；ATB 依赖 cann-nnal JIT。没有构建证据就不要下结论。

## 10. 算子增量核查（时间窗内新增/删除了哪些算子）

触发："Ops 仓最近一个月有没有新增算子 / 这个版本新增了哪些算子 / 算子清单变没变 / 转测说明里该写哪些新算子"。
与 §2 的区别：§2 盘的是"Ops 调用外部组件"的面，本节盘的是"Ops 自己对外提供了哪些算子"的增量。

### 用整树集合差分，不要用 `--diff-filter=A`

```bash
git -C <repo> fetch origin master
git -C <repo> rev-list -1 --before="<窗口起点> 00:00" origin/master   # 取基线提交
git -C <repo> ls-tree -r --name-only <base>        > old.txt
git -C <repo> ls-tree -r --name-only origin/master > new.txt
```

差集交给 Python 做（`set(new) - set(old)`）。坑：**`git log --diff-filter=A` 会把重命名的另一半也报成 A**，直接数会把"整目录搬家/改版式重写"算成"新增算子"；整树差集没有这个噪声。PowerShell 侧不要用管道统计（会插 CRLF/BOM，且 `Measure-Object -Line` 跳过空行）。

### "一个算子"的判定口径（四件套）

Triton 算子必须同时具备，缺一即视为半成品/占位，不得写进"已交付新算子"：

- `mindspeed_ops/api/triton/<name>.py`（对外入口）
- `mindspeed_ops/arch32/triton/<name>.py`（kernel；部分放 `arch32/triton/<family>/` 下）
- `tests/unit_tests/triton/test_<name>.py`
- `tests/atk_tests/triton/<name>/`（`<name>.yaml` + `generate_<name>.py` + runner）

AscendC 算子看 `csrc/<op>/`：`op_api/` + `op_host/` + `op_kernel/`，多形态按 `stages/<stage>/` 分，入口为 `api/aclnn/__init__.py` 导出的 `npu_<op>`。

### 三处交叉核对，避免把"变体"说成"新算子"

1. 首次提交：`git -C <repo> log --reverse --format="%h|%ad|%an|%s" --date=short origin/master -- <op_path> | head -1`，拿日期/作者/标题。
2. 是否进对外清单：`git -C <repo> grep -n -i "<op>" origin/master -- docs/zh/supported_operators.md`。**没进表 ≠ 不存在**，只说明尚未登记；报告里要分开说。
3. 同族是否已在库内：对比 `ls-tree ... -- mindspeed_ops/api/triton` 的前后清单。已有 `chunk_gated_delta_rule`、`fwd_h` 时再出现 `..._fwd_kkt_solve`，属"已有算子族的新阶段"；`inplace_rope`、`layer_norm_fwd_1pass` 属"常见算子的新实现/变体"。结论必须标归属，不能一律写成"全新算子"。

### 分支口径必须先钉死

同一批新算子常常只在 master：`git -C <repo> ls-tree -r --name-only origin/26.2.0 | grep <op>` 全 0（2026-11 实测就是 master 有、26.2.0 一个没有）。"Ops 仓有没有新增算子"这句话，**先确认是 master 还是发布分支**，否则结论正好相反。

### 时间边界

写绝对日期（`--before="2026-10-12 00:00"`），不要用 `--since="1 month ago"`（随执行日漂移、报告不可复现）。卡在边界当天的算子要显式提示"按严格 30 天则不计入"。

报告落 `reports/YYYY-MM-DD-ops-new-operators-<窗口>.md`：结论 → 清单表（算子名/形态/首次提交+日期/作者/实现位置/配套是否齐全）→ 口径（边界、分支、变体归属）→ 可复现命令。
