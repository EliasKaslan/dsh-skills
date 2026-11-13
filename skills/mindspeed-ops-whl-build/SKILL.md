---
name: mindspeed-ops-whl-build
description: 打 MindSpeed-Ops whl 并验收：cmake/clang、SOC_VERSION、CATLASS。适用于"打 ops 的 whl / cmake 版本报错 / GCC 太旧 / 验证 whl"。
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
source /home/x00886548/env/cann/cann_9_1_0/ascend-toolkit/set_env.sh
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

- 还有一类**不报错**的构建缺陷（下载第三方依赖时静默不校验证书 / 哈希加错分支）：见下方「第三方依赖下载（ExternalProject_Add）：TLS 校验与 URL_HASH」节——**别以为"删掉 `TLS_VERIFY OFF` 就修好了"**。

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

## CI 门禁不产 whl；SOC_VERSION 为空不等于纯 py

## 门禁只做就地编译，不产 whl

- 仓内 `.gitcode/` 只有 `PULL_REQUEST_TEMPLATE.md` 与 `pr-pipeline-mindspeed-ops.yml` 一个 workflow；该 workflow 里 `wheel|bdist|dist` **零命中**，`ci/` 也只构建 docker 镜像。
  ⇒ **合任何 CI 相关 PR 都不会让流水线开始产 whl**。要 whl 只能自己跑 `python -m pip wheel ...`（§1）。
- 门禁真实动作（`ci/MindSpeed_Ops_ut.sh`）：`pip install -e . --no-deps --no-build-isolation` → `pytest -x tests/unit_tests/catlass`（rank1）→ `python ci/access_control_test.py --rank N`。它证明的是"能在该栈下就地编译并跑过 UT"，**不证明 whl 可用**。

## 修正：`SOC_VERSION` 为空不等于"一定静默纯 py"

- 26.2.0 分支 `setup.py:96-99`：`SOC_VERSION` 未设时先调 `get_chip_type()` **自动探测**——内部执行 `npu-smi info -t board -i <n> -c 0`，取 `Chip Name` / `Chip Type` / `NPU Name` 拼成 soc 名；探测成功就照常编扩展（`setup.py:419-421` 仅在 `if _env_soc_version` 时追加 `ext_modules`）。
- 所以"whl 里没有 `.so`"要分两种成因：①机器无 NPU 或 `npu-smi` 不可用 → 探测返回空 → 静默纯 py whl；②**有 NPU 时即使不显式 export 也会编**。
  判定只能看 whl 成员，不能看"有没有设环境变量"。
- CI 容器探测得到（runner 带 `npu=1`，driver / dcmi / npu-smi 都 bind-mount 进去），因此门禁里从不设 `SOC_VERSION` 也能正常编。

## 在 CI 镜像里构建时先核镜像架构

```bash
docker inspect --format '{{.Architecture}}' <image>   # 必须 arm64
```

`ci/build.sh` 的默认 tag 用 `uname -m` 推架构，但 `-i` 显式给镜像名会**绕过**这层保护 → 在 x86_64 机器上能产出"名字写 aarch64、内容其实 x86_64"的镜像；推到 SWR 后门禁 runner 拉下来跑不起来，且从 tag 上看不出问题。

## 第三方依赖下载（ExternalProject_Add）：TLS 校验与 URL_HASH（实测）

**① 不写 `TLS_VERIFY` ≠ 会校验证书。** 官方文档 `TLS_VERIFY <bool>` 原文：`If this option is not provided, the value of the CMAKE_TLS_VERIFY variable or the CMAKE_TLS_VERIFY environment variable will be used instead (see file(DOWNLOAD)). If neither of those is set, certificate verification will not be performed.`；而 `CMAKE_TLS_VERIFY` 自己的文档写着 `Changed in version 3.31: The default is on. Previously, the default was off.`

⇒ **"删掉 `TLS_VERIFY OFF`" 在 3.31 之前的 CMake 上是无效修复**（什么都不填=默认不校验），必须**显式写 `TLS_VERIFY ON`**。本仓 `pyproject.toml:4` 只要求 `cmake>=3.26`，**不能依赖 3.31 才有的新默认值**。
- 实例：`mindspeed_ops/csrc/cmake/third_party/json.cmake` 的 `ExternalProject_Add(third_party_json ... URL <gitcode 的 include.zip> TLS_VERIFY OFF)`。
- **同目录已有正确范式**：`third_party/makeself-fetch.cmake` 里 `URL_HASH SHA256=...` → 证明"加校验/加哈希"在本仓可行，删掉 `TLS_VERIFY OFF` 是**局部疏漏**而非技术不可行。

**② `URL_HASH` 只对"同一个制品"成立，别无差别加。** 本仓 `ascend_protobuf.cmake` 有 3 条地址分支：本地随包 `.../protobuf/protobuf-all-25.1.tar.gz`、`.../pkg/${PROTOBUF_VERSION_PKG}`，远端 `.../releases/download/v25.1/protobuf-25.1.tar.gz`——**文件名都不同，是不同文件**；给所有分支加同一个哈希会让**本地构建直接失败**（本地随包存在时走 file:// 分支）。
⇒ 只给**远程下载分支**注入哈希，用一个空的 list 变量拼接（空变量在 CMake 参数列表里展开为 **0 个参数**，已实测）：

```cmake
set(HASH_ARGS)                                    # 默认空
if(<该 PR 走远程下载>)
    list(APPEND HASH_ARGS URL_HASH SHA256=<hash>)
endif()
ExternalProject_Add(<name> URL ${REQ_URL} ${HASH_ARGS} ...)   # 引用时不要加引号
```

- **坑**：写成 `"${HASH_ARGS}"` 会塞进 **1 个空参数**（不是 0 个）→ 参数错位报错。只要空值就**不加引号**。

**③ 判"该不该加"用对照法，不靠推测**：一条命令列出同目录现状（实测输出只有 `json.cmake:51: TLS_VERIFY OFF`、`makeself-fetch.cmake:23: URL_HASH SHA256=...`）：

```bash
git grep -n -E 'URL_HASH|TLS_VERIFY' -- mindspeed_ops/csrc/cmake/third_party/
```

- 同目录有正确范式 = 疏漏（要求统一修复）；一处都没有，才需要论证可行性。
- 漏洞报告侧的定级口径（无 hash / TLS 关掉该维持高危还是降级）→ `vuln-scan-report-verification` §5，本节不重复。

