---
name: mindspeed-ops-whl-build
description: 把 MindSpeed-Ops 源码打成可安装 whl 并逐层验收——cmake≥3.16、Python3_EXECUTABLE 注入、gcc8 必须换 clang-11、cmake 包装脚本会被 setup.py 按前 128 字节含 python 拒掉、SOC_VERSION 决定 aclnn 与 arch、CATLASS 需 MINDSPEED_BUILD_CATLASS=1；whl 非 manylinux、无 Requires-Dist。适用于"打 MindSpeed-Ops 的 whl / pip wheel 报 cmake_minimum_required / 报 too old version of GCC / 报 No module named regex / 验证 whl 能不能用 / whl 装完 import 找不到 torch"。不适用：装 CANN → 用 `ascend-cann-env`；torch 栈 → 用 `ascend-torch-npu`；给仓提 PR → 用 `gitcode-pr-flow`。
whenToUse: 要产出 MindSpeed-Ops 的 whl、判断某个 whl 能不能用、或 whl 构建中途报错时用：构建环境三件套（cmake / 编译器 / python 解释器）+ 八项验收矩阵 + 单测分片跑法。模型看不到本节。
---

# MindSpeed-Ops whl 构建与验收

## 0. 何时调用

- **起点**：手上是 `https://gitcode.com/Ascend/MindSpeed-Ops.git` 的某个分支（`master` / `26.2.0` / `26.1.0`），要一个能 `pip install` 的 whl，并证明它真能用。
- **输入**：分支名或 commit；宿主已装 CANN（任意 9.1.0 / 9.2.0 小版本皆可，见 §5）。
- **口径**：whl 必须**装进干净 venv、从 site-packages 解析**再验，不能在源码树里 `python -c import` 自证。
- **依赖**：CANN → `ascend-cann-env`；torch/torch_npu/triton → `ascend-torch-npu` / `ascend-triton-ascend`；从 Windows 驱动远端（别内联复杂引号，脚本推过去）→ `ascend-env`。

## 1. 构建（u91 = `/mnt/share/vllm/conda_envs/xmz_0921`，py3.12 + torch2.10 + cmake4.4）

```bash
git clone -b <branch> https://gitcode.com/Ascend/MindSpeed-Ops.git src/<label>
cd src/<label>
source /mnt/share/x00886548/cann/cann_9_1_0/ascend-toolkit/set_env.sh
export SOC_VERSION=ascend910_9382     # 芯片 910/9382 → 内部归一成 ascend910_93 / arch32
export MINDSPEED_BUILD_CATLASS=1      # 只有 ascend910b / ascend910_93 生效
export MAX_JOBS=16
python -m pip wheel . --no-deps --no-build-isolation -w dist -v
```

- `setup.py:440` 的 `version=os.environ.get("MINDSPEED_OPS_VERSION","26.2.0")` ⇒ **任何分支都打 26.2.0**，文件名不带 commit / 日期，只能靠 sha256 区分。
- `SOC_VERSION` 为空时 `ext_modules=[]` ⇒ 静默产出**纯 Python whl**（没有 `mindspeed_ops_C*.so`），必须回读 whl 成员确认。
- 目录名 `dist/mindspeed_ops-26.2.0-cp312-cp312-linux_x86_64.whl`：tag 是 `cp312-cp312-linux_x86_64`，**不是 manylinux**。

## 2. 四个必踩的坑（原始报错 → 修法）

| 报错原文 | 根因 | 修法 |
|---|---|---|
| `CMake Error at CMakeLists.txt:1 (cmake_minimum_required): Compatibility with CMake < 3.5 has been removed` | 系统 `/usr/bin/cmake` 是 3.13 | PATH 前置一个 cmake 4.4.3 包装脚本（`conda env` 自带那份） |
| `ModuleNotFoundError: No module named 'regex'`（在 `csrc/cmake/scripts/util/ascendc_impl_build.py`） | ACLNN 子构建的 `find_package(Python3)` 挑走了机器上最新的 python3.14 | 包装脚本给**非 `--` 开头的调用**注入 `-DPython3_EXECUTABLE` 与 `-DASCEND_Python3_EXECUTABLE`（变量名可拆成 `K=Py; K="${K}thon3_EXECUTABLE"` 拼，避免脚本里出现连续字面量 python） |
| `c10/util/C++17.h:14: #error "You're trying to build PyTorch with a too old version of GCC. We need GCC 9 or later."` | 系统 gcc 只有 8.3 | 用 `/usr/bin/clang-11`：该守卫是 `#if !defined(__clang__) && __GNUC__ < 9`，clang 分支只要求 `__clang_major__ >= 9` ⇒ 只在**根工程**那次 configure 注入 `-DCMAKE_C_COMPILER=clang-11 -DCMAKE_CXX_COMPILER=clang++-11` |
| 包装脚本完全没被用上，仍走 `/usr/bin/cmake` | `setup.py:113-128` `_find_cmake_binary()` 会跳过「前 128 字节以 `#!` 开头且含 `python`」的 cmake，判为 pip 的 wrapper | 包装脚本前 128 字节里**不要出现字面量 python**，改用 `$WORK/bin/py3` 这类间接路径 |

## 3. 验收矩阵（八项，缺一项都不算"能用"）

1. **静态审计**：zip 完整性、成员数、`mindspeed_ops_C*.so` 在、`lib/libmindspeed_catlass_*.so` 两枚在、`_cann_ops_custom/` 48 个文件在（含 `libcust_opapi.so`）、`csrc/atb/*.cpp` 在、`pyc`=0、`Requires-Dist` 空、`Tag` 是什么。
2. **离线安装**：`python -m venv` + `pip install --no-index --no-deps <whl>`（证明不依赖网络与源码树）。
3. **导入与注册**：`mindspeed_ops.__file__` 落在 site-packages；**注册表用 `torch._C._jit_get_all_schemas()` 过滤 `mindspeed_ops::`**——`dir(torch.ops.mindspeed_ops)` 是懒加载，不能当判据（本轮实测它返回 1 个且两次不同）。
4. **算子冒烟**：ACLNN（`add_rms_norm_bias`）、Triton（`rmsnorm_without_weight`）、CATLASS（bf16 matmul，注意该 kernel 只收 bf16）各一条，带数值误差。
5. **仓内单测**：`tests/unit_tests` 全量（见 §4）。
6. **跨 CANN**：换 9.2.0 再跑第 3、4 项 ⇒ 证明不锁死 CANN 小版本。
7. **ELF 兼容**：`readelf -d` 看 `NEEDED` 与有无 `RPATH/RUNPATH`；`strings | grep GLIBCXX` 看最高符号版本（本轮 ≤3.4.21，glibc ≤2.14）。
8. **裸装行为**：无继承的 venv 里 `pip install` 后再 `import` ⇒ 会 `ModuleNotFoundError: No module named 'torch'`，而 `pip check` 仍说 `No broken requirements found`（`install_requires` 恒空）。

## 4. 单测怎么跑才不假阴性

- 测试里有 `from tests.utils import ...` ⇒ **必须把 `tests/` 拷贝到工作目录**，从该目录用 venv python 跑（这样才证明走的是 site-packages）。
- 采集数（2026-11-03）：`master` **1353**（aclnn 126 / atb 15 / catlass 29 / tilelang 24 / triton 1159）、`26.2.0` **1083**。
- **别用 `-n N` 把多 worker 压在同一张 die 上**：torch_npucaching 每个 worker 会占几 GB，6 worker 实测把 64 GB die 撑满，后半程整片 `torch.OutOfMemoryError: NPU out of memory ... 6.11 MiB free`，进程虽在但不再推进（表现为日志长时间停在同一进度）。
- 正确姿势：**按测试文件分片，一片一张 die**（`find . -name 'test_*.py' | sort` → `split -n r/N` → 每片 `ASCEND_RT_VISIBLE_DEVICES=<chip>` 独立进程），片内串行。triton 的 dqkwg / kkt_solve / l2norm 单例就要 2–5 分钟编译，别按普通单测估时。
- 判失败性质：`NPU out of memory` 属环境（多人共用 die 被抢），**单独在空闲 die 上重跑该文件**即可定性；本轮 5 例失败 5/5 重跑通过。
- 采集/统计：`pytest --collect-only -q | grep -c '::'`；进度按日志里 `^[.FEsx]+$` 行累加字符数（traceback 里的点会让 `grep -o '\.'` 严重高估）。

## 5. 已核实的事实

- `install_requires` 恒空、`package_data` 只带 `lib/*.so` + `csrc/atb/*`；`_cann_ops_custom/` 是在 `setup.py:349-355` 显式 `copytree` 进去的（不是 `find_packages` 带出来的）。
- ext `.so` **没有 RPATH**：靠 `mindspeed_ops/__init__.py` 里 `ctypes.CDLL(..., RTLD_GLOBAL)` 预加载同目录 catlass so 才能解析 `NEEDED`；绕过包 `__init__` 直接 dlopen 会失败。
- `ASCEND_CUSTOM_OPP_PATH` 在 import 时被改写成 `<site-packages>/mindspeed_ops/_cann_ops_custom/vendors/mindspeed_transformer`，无需外部设置。
- `26.2.0` 分支的 whl 是 `master` 的严格子集（本轮 master 多 13 个 py：4 个新 triton api + arch32/arch35 变体）；两个 whl 的 7 个 `.so` 同名同大小但 ext 的 sha256 不同。
- `CANN 9.1.0` 上跑时会看到 `libstdc++.so.6: version GLIBCXX_3.4.26 not found (required by .../opp/vendors/batch_invariant/.../libcust_opmaster_rt2.0.so)` —— **非致命**，算子照常工作（换 9.2.0 即消失）。
