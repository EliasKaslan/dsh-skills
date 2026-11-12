---
name: vllm-ascend-source-install
description: 源码装 vllm + vllm-ascend 配对版本：读 verified commit、注释 pin 复用 torch。适用于"重装 vllm-ascend / 按 commit 配 vllm / build deps 不满足"。
whenToUse: 要决定「怎么把 vllm 与 vllm-ascend 从源码装进已有环境」时用：按 verified commit 配对两仓、复用已装 torch 栈、编译 AscendC 算子。
---

# vllm + vllm-ascend 源码安装（配对 commit + 复用已有 torch 栈）

范围：只做 vllm 与 vllm-ascend 两个 `pip install -e .`。**前置栈的从零搭建见总纲 skill `ascend-env`**（它按顺序指向 `ascend-server-layout` / `ascend-cann-env` / `ascend-conda-env` / `ascend-torch-npu` / `ascend-triton-ascend`）；跑起来见 `ascend-vllm-serve`。

**默认机器：`root@192.168.13.188`（ssh 别名 `a3`）**；备用 `root@192.168.13.190`（别名 `a3b`）。两台都已配好公钥免密，密码 fallback 见 `ascend-env/credentials.txt`。两机差异（**尤其 gcc 版本**）会直接改变本流程的做法，见下。

## 何时调用

**加载本 skill 当：**
- 要把 vllm 与 vllm-ascend 用 `pip install -e .` 装进已有环境（或重装、换 commit），包括 `--no-build-isolation` 报 build dependencies 不满足。
- 要按 vllm-ascend 当次 checkout 的 `.github/vllm-main-verified.commit` 配对 vllm 版本。
- 不希望 pip 按 pin 换掉已装好的 torch / torch_npu / triton-ascend，或问要不要开 `VLLM_BATCH_INVARIANT`。

**不要用本 skill（转交）：**
- 服务起不来、离线推理 / 冒烟 / 权重校验 / 运行时排障 → 用 `ascend-vllm-serve`（本 skill 只管「装得上」，不管「跑得起来」）。
- torch 栈本身缺或装不上 → 用 `ascend-torch-npu`；triton-ascend 相关 → 用 `ascend-triton-ascend`；CANN → 用 `ascend-cann-env`。
- 判某模型在昇腾 / vllm-ascend 侧的适配程度与缺口 → 用 `ascend-model-adaptation-recon`。
- 上游仓库 docs 缺口审计（内部需求 vs docs 主线） → 用 `upstream-docs-refresh-audit`。
- 新增 / 移动 e2e 用例要进 CI、为什么报 MISSING → 用 `vllm-ascend-e2e-ci-wiring`。

**前置**：CANN 已装且每次操作前 `source` 过 toolkit 与 nnal/atb；环境里已有 torch / torch-npu / triton-ascend（见 §0）。 ／ **后继**：`ascend-vllm-serve`。

## 0. 前置（不满足先别往下走）

- Linux + 已装 CANN，且每次操作前 `source` 过 toolkit 与 nnal/atb 两段 `set_env.sh`；gcc/g++ ≥ 8（支持 C++17）**但编自带 C++ 扩展要 ≥ 9（见下一条与 §4.2）**；`MAX_JOBS` 按机器核数设，共享机别打满。
- **先确认 gcc 版本，它决定 §3 要不要加 `--arctic`、§4.2 要用哪个编译器、以及要不要做 GLIBCXX 兜底**：
  - `.188`（默认）：系统**只有 gcc/g++ 8.3**，且系统 libstdc++ **无 `GLIBCXX_3.4.26`** → §3 必须加 `--arctic`；**但 `--arctic` 只解决 `arctic-inference` 编不过的问题，编 C++ 扩展 `vllm_ascend_C` 时 gcc 8.3 会直接失败**（torch 头文件要求 GCC ≥ 9）→ 必须按 §4.2 换成 conda 工具链里的 gcc 10；运行时还要 compat_lib 兜底（见 §6 坑 8）。
  - `.190`（备用）：gcc/g++ 10.2，系统 libstdc++ 够用 → §3 不加 `--arctic`（反而要预装它，见 §6 坑 5），§4.2 也不用做。
- **硬条件：环境里已经有 torch / torch-npu / triton-ascend** —— 本流程会故意注释掉它们的 pin，不会去装它们。先确认：

```bash
python3 -c "import torch, torch_npu; print(torch.__version__, torch_npu.__version__)"
pip show triton-ascend | head -n 2
npu-smi info -t board -i 0 -c 0 | head -n 5     # -c 0 才有 Chip Name，setup.py 靠它探 SOC
```

- 缺 torch 栈：先按 vllm-ascend **改动前** `requirements.txt` 里的 pin 预装（§3 的脚本会把原 pin 打印出来），装完再进 §3：

```bash
pip install torch==<x> torchvision==<x> torchaudio==<x> --index-url https://download.pytorch.org/whl/cpu
pip install torch-npu==<x>
pip install "triton-ascend==<x>" --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple
# triton-ascend 不在 PyPI 上，必须带这个 --extra-index-url（2026-09-23 实测 osinfra 上只有 3.2.2/3.2.1）；细节见 skill `ascend-triton-ascend`
```

## 1. 取版本对（顺序关键：先 vllm-ascend，再据它取 vllm）

```bash
export SRC=<源码父目录>              # 如 /home/<user>/vllm_build
cd $SRC
git clone --depth 1 https://github.com/vllm-project/vllm-ascend.git   # 默认就是 main 最新
cd vllm-ascend
git submodule update --init --recursive        # 源码装必做：csrc/third_party/catlass（注意它在 gitcode.com/cann/catlass.git，不是 GitHub）
VLLM_COMMIT=$(cat .github/vllm-main-verified.commit)
cd $SRC
git init vllm && cd vllm
git remote add origin https://github.com/vllm-project/vllm.git
git fetch --depth 1 origin $VLLM_COMMIT && git checkout FETCH_HEAD
```

- 两仓是**配对**的：vllm 必须用 vllm-ascend 当次 checkout 里的 `.github/vllm-main-verified.commit`，不要用 vllm 自己的 tag 或最新 main。
- 已有 vllm-ascend 源码要跟最新主线：`git fetch origin main && git checkout FETCH_HEAD`，**再**读 commit 文件（内容随主线更新）；要 release 就切对应 tag/分支，vllm 仍按该 checkout 的 commit 文件取。
- **短 SHA 不能直接 `git fetch`**（2026-09-28 实测）：`git fetch <short-sha>` 报 `fatal: Couldn't find remote ref 9df651d`，`git ls-remote` 也列不出来（短 SHA 不是 ref）。取全 SHA 的办法：
  ```bash
  curl -s https://api.github.com/repos/<owner>/<repo>/commits/<short-sha> | grep -m1 '"sha"'
  ```
  拿到全 SHA 再 `git fetch --depth 1 origin <full-sha>`。
- **vllm 仓 origin 指向本地镜像（`file://…`）、且是浅克隆、0 tag** 时**不必删库重 clone**：直接
  ```bash
  git fetch --depth 1 https://github.com/vllm-project/vllm.git refs/tags/<tag> && git checkout -f FETCH_HEAD
  ```
  实测可用，**未**出现 `shallow update not allowed`（2026-09-28 在 `.188` 实测）。

## 2. 装 vllm（不编 C++）

```bash
cd $SRC/vllm
export VLLM_TARGET_DEVICE=empty
python3 use_existing_torch.py            # 必须先跑：删掉 requirements/*、pyproject.toml 里 torch 家族的行
pip install -r requirements/common.txt
pip install setuptools_rust setuptools_scm
pip install -e . --no-build-isolation
```

- `use_existing_torch.py` 必须在 `pip install -r` **之前**，否则 pip 会按 pin 换掉已装 torch。
- `VLLM_TARGET_DEVICE=empty` 使 `ext_modules=[]`，vllm 不编 C++，gcc 版本低也无所谓；rust 扩展是 optional。
- 此时 `import vllm` 可能报 `No module named 'triton.experimental'`，属预期，装完 vllm-ascend 自动消失（坑 3）。

## 3. 注释掉 vllm-ascend 里 torch 家族的版本 pin（等价 vllm 的 use_existing_torch.py）

vllm-ascend 仓没有 `use_existing_torch.py`，用本 skill 自带脚本代替（幂等、自动备份 `<file>.pinbak`、TOML 自校验并失败回滚）：

```bash
cd $SRC/vllm-ascend
python3 <本 skill 目录>/scripts/strip_torch_pins.py .                 # .190 等 gcc>=9 的机器
python3 <本 skill 目录>/scripts/strip_torch_pins.py --arctic .        # .188（gcc 8.3）必须加 --arctic
git diff -- requirements.txt pyproject.toml                # 确认只动了目标行
```

**`--arctic` 是干什么的**：额外把 `arctic-inference==0.1.1` 也注释掉。它的 C++ 扩展需要 C++20 `<span>`，**gcc 8.3 编不过**；该包只被 vllm 的可选 suffix-decoding 路径使用，vllm-ascend 源码不引用它，所以注释掉是安全的。默认不加这个 flag，`.190` 上的行为与以前完全一致（那里 gcc 10.2 能编，应改用 §6 坑 5 的预装法）。

它做的事（就是用户脚本里 `vim requirements.txt` / `vim pyproject.toml` 的目的）：

- `requirements.txt`：把 `torch==…` / `torch-npu==…`（含 `torch_npu`）/ `triton==…` / `triton-ascend==…` 整行注释掉；同族的 `torchvision` / `torchaudio` 一并注释（留 pin 会把 torch 反拉回来）。
- `pyproject.toml`：把 `[build-system].requires` 数组里同名的**整行元素**注释掉（TOML 无法只注释掉版本号，必须整行）。
- 为什么注释有效：setuptools 的 `_reqs.parse_strings` 会丢弃 `#` 行与空行（已核对源码），注释行不会进 `install_requires`；而 `--no-build-isolation` 下 pip 会校验 `build-system.requires` 每一项已安装，pin 留着就会因版本不一致报 build dependencies 不满足。
- 顺序：**必须先注释再 `pip install -e .`**。手工等价操作就是给这 6 类包整行加 `# `。
- 这些是本地构建旁路改动，**不要 commit/push**；还原用 `.pinbak` 或 `git checkout -- <file>`。

**脚本没动、但同样受 `--no-build-isolation` 校验的 build 依赖（2026-09-22 实测）**：`[build-system].requires` 里除 torch 家族外还有一批**带版本约束**的项——`transformers==5.14.1`、`fastapi<0.124.0`、`fastokens==0.2.0`、`arctic-inference==0.1.1`、`xgrammar>=0.1.30`、`compressed_tensors>=0.11.0`、`cmake>=3.26`、`setuptools>=64`、`setuptools-scm>=8`。脚本有意只注释 torch 家族（`--arctic` 时额外注释 arctic-inference），所以**环境里其余包的版本必须已经满足**，否则构建期会报 build 依赖不满足。最常踩的是 `transformers`：vllm 装完可能是 5.17，而这里要求 5.14.1——先 `pip install transformers==5.14.1` 再装 vllm-ascend（或在 `strip_torch_pins.py` 的 `TORCH_TARGETS` 里加上它，但那样会让 pip 有权换 transformers，通常不想要）。
> 注意 `arctic-inference==0.1.1` 在两台机器上**做法相反**：`.188`（gcc 8.3）编不了 → 用 `--arctic` 注释掉；`.190`（gcc 10.2）能编 → 用 §6 坑 5 预装。

**脚本本身的实测记录（2026-09-22，上游 main）**：
- 默认模式（pristine 文件）：`requirements.txt` 注释 5 行（torch / torch-npu / torchvision / torchaudio / triton-ascend），`pyproject.toml` 注释 4 行（torch-npu / torch / torchvision / triton-ascend），TOML 自校验通过（剩 26 项），`rc=0`；第二次运行幂等。
- `--arctic` 模式（2026-09-22 在 `.188` 实测）：`requirements.txt` 注释 **6** 行、`pyproject.toml` 注释 **5** 行，TOML 自校验通过（剩 **25** 项），`rc=0`，幂等；`arctic-inference` 的注释标记与 torch 家族不同（`needs C++20 <span>, not buildable with this gcc`）。
- 参数处理：`--help` → `rc=0`；未知 flag → `rc=2`；flag 放在仓根参数**前后均可**。

## 4. 装 vllm-ascend（编译 AscendC 算子）

```bash
cd $SRC/vllm-ascend
export COMPILE_CUSTOM_KERNELS=1
rm -rf csrc/build build
pip install -e . --no-build-isolation 2>&1 | tee build.log
```

- `COMPILE_CUSTOM_KERNELS=1` 才会编 AscendC 算子（`vllm_ascend_C` + aclnn），耗时长（十几分钟起）；不想编就设 0 或删掉这行，只装纯 python。
- `rm -rf csrc/build build` 清上次产物，避免半成品残留；换过 torch/CANN 版本后**必做**。
- `SOC_VERSION` 一般不用设（setup.py 用 `npu-smi … -c 0` 自动探测）；npu-smi 不可见时显式设：A2 `ascend910b1`、A3 `ascend910_9391`、300I DUO `ascend310p1`、950DT `ascend950dt_9582`。
- 构建中监控：`grep -c "error:" build.log`、`find csrc/build -name '*.o' | wc -l`。耐心轮询，别超时重试。

### 4.1 VLLM_BATCH_INVARIANT：默认不开

- 用户**没有**明确提批次不变性（batch invariance / 批次不变性 / 结果不随 batch 组成变化 / RL 场景一致性）→ **不要** export 这一行，命令里就不该出现。
- 用户明确要求 → 在 §4 的 `pip install -e .` **之前**加：

```bash
export VLLM_BATCH_INVARIANT=1     # 构建期生效
```

  作用：`csrc/build_aclnn.sh` 会额外下载并安装 batch_invariant 的 AscendC 算子包与 `batch_invariant_ops` wheel（联网 OBS 源），构建更慢。
- 这是**构建期**开关，不保留成运行时设置：起服务/离线推理时还要再 `export VLLM_BATCH_INVARIANT=1`，或 `--additional-config '{"enable_batch_invariant": true}'`。
- 预编译 wheel 不含 csrc，设了也不会重建（只在源码装时有效）。
- **（`.188` 实测坑）先修 `csrc/build_batch_invariant_ops.sh` 的超时再开这个开关**：该脚本用 `curl --max-time 5` 下载 batch_invariant 的 whl，实测这个 zip 要 2.4–4.7s，5s 上限会**随机超时 → whl 静默没装上 → 后面 import 不到 BI 算子**。把 whl 那一行改成 `--max-time 300`（`.188` 现成环境已改，原文件备份为 `.orig`）。下载 run 包那行的 `--max-time 120` 够用、不用动。
- **判 BI 到底编进去没有：别看脚本那行"成功"日志（假阳性）**。`csrc/build_batch_invariant_ops.sh` / `build_and_install.sh` 都**没有 `set -e`**，内层 ninja 明明失败仍会打印成功行。实测原文（失败却照样报成功）：
  ```
  build_and_install.sh: line 28: cd: .../dist: No such file or directory
  ERROR: Invalid wheel filename (wrong number of parts): '*'
  [install_batch_invariant] batch_invariant whl package installed successfully
  ```
  三条判据，**都过才算真装上**：
  1. `site-packages/batch_invariant_ops*/` 与 `batch_invariant_ops_lib*.so` 的 **mtime 是本次构建**；
  2. `python -c "import vllm_ascend.batch_invariant as b; print(b.HAS_ASCENDC_BATCH_INVARIANT)"` 输出 `True`；
  3. CANN 侧 `…/cann-<ver>/cann-9.1.0/opp/vendors/batch_invariant/` 目录存在且 mtime 是本次。
- **属性在哪个模块，别探错地方**：`HAS_ASCENDC_BATCH_INVARIANT` 定义在 **`vllm_ascend.batch_invariant`**（源码 `vllm_ascend/batch_invariant.py` 顶部），**不在** `batch_invariant_ops` 模块上——对它 `import batch_invariant_ops` 去探只会得到 `?`，会被误判成"BI 没编进去"。反面探针：`dir(torch.ops.batch_invariant_ops)` **数不出算子**（实测只返回 1 个属性），别拿它当判据；要看绑定关系就读 `vllm_ascend/batch_invariant.py` 里把 `aten::mm` / `aten::matmul` 绑到 `torch.ops.batch_invariant_ops.npu_*_batch_invariant` 的那几行（其后是 triton 回退分支）。

### 4.2 编 `vllm_ascend_C` 的编译器（torch 2.10 头文件要求 GCC ≥ 9）

`.188` 系统只有 gcc 8.3，编 C++ 扩展 `vllm_ascend_C` 会直接死——**`--arctic` 救不了它**（那只管 `arctic-inference`）。实测原文：

```
torch/include/c10/util/C++17.h:14:2: error: #error "You're trying to build PyTorch with a too old version of GCC. We need GCC 9 or later."
make: *** [Makefile:286: vllm_ascend_C] Error 2
subprocess.CalledProcessError: Command '['cmake', '--build', '.', '-j=64', '--target=vllm_ascend_C']' returned non-zero exit status 2
ERROR: Failed building editable for vllm_ascend
```

修法：**借机器上上一版构建时建的专用工具链 conda env，别去装/改系统 gcc**。`.188` 上的实例是 `/home/x00886548/vllm_build_0921/conda_envs/bi_0921`（`conda-forge gcc 10.4.0`，`bin/` 下有 `x86_64-conda-linux-gnu-gcc` / `g++` / `cc` / `c++` / `gcc-ar` / `gcc-nm` / `gcc-ranlib`）：

```bash
export BI_TC=<工具链 env 路径>
export CC=$BI_TC/bin/x86_64-conda-linux-gnu-gcc
export CXX=$BI_TC/bin/x86_64-conda-linux-gnu-g++
export C_COMPILER=$CC CXX_COMPILER=$CXX    # vllm-ascend 自己的 envs.py 会转成 -DCMAKE_CXX_COMPILER
```

- 只设 `CC`/`CXX`、或只设 `C_COMPILER`/`CXX_COMPILER`，两种都实测能过；**建议两者都设**（`CC`/`CXX` 是 torch `cpp_extension` 与 BI python wheel 源码编译读的）。
- ⚠️ **绝不把该 env 的 `bin` 前置进 `PATH`**：它是带自己 `python`/`pip` 的 conda env，前置后 `pip` 会解析到它的 pip，**把 vllm-ascend 装进错误的 conda env**（静默、后果严重）。只用 `CC`/`CXX` 的绝对路径指编译器。
- 换过 torch 或改过 pin 后**必须 `rm -rf csrc/build build`**（§4 已含），否则 cmake 沿用缓存里的旧编译器。
- **取证"这次用了哪个编译器"要看对地方**：`vllm_ascend_C` 的 cmake 跑在 setuptools 临时目录里，且 **pip 成功时不打印构建日志**；`csrc/build/CMakeCache.txt` 里的 `CMAKE_CXX_COMPILER=/usr/bin/c++` 属于 **aclnn/kernels 那套构建，不能用来判断 `vllm_ascend_C`**。可信取证：构建日志里 ninja 实际调用的 `g++` 路径，或新生成 `.so` 的 mtime（`ls -l --time-style=full-iso <env>/lib/python3.*/site-packages/vllm_ascend/*.so`）。

## 5. 验证（逐层来，别一上来就跑模型）

```bash
python3 -c "import torch, torch_npu; print(torch.npu.is_available(), torch.npu.device_count())"
python3 -c "
from vllm.platforms import current_platform as p; print(type(p).__name__, p.device_type)
import vllm_ascend, importlib.util as u, os, triton
print('ext:', bool(u.find_spec('vllm_ascend.vllm_ascend_C')))
print('ascend backend:', os.path.isdir(os.path.join(os.path.dirname(triton.__file__), 'backends', 'ascend')))"
python3 -c "import vllm; print('vllm', vllm.__version__)"
python3 -c "import importlib.metadata as m; print('vllm-ascend', m.version('vllm-ascend'))"   # 别用 vllm_ascend.__version__
python3 -m pip check        # 只剩上游固有冲突算正常（坑 4）
```

- **ascend backend 一定要从 `triton.__file__` 出发**：本流程用 `pip install -e .`（editable），`vllm_ascend.__file__` 指向**源码树**（`<src>/vllm-ascend/vllm_ascend/__init__.py`），所以 `dirname(vllm_ascend.__file__)+'/../triton/backends/ascend'` 恒为 `False`（2026-09-22 在 `.190` 实测：错误写法 False、正确写法 True）。
- **不要读 `vllm_ascend.__version__`**：`.188` 实测该属性不存在（`AttributeError`），取版本号用 `importlib.metadata.version('vllm-ascend')`。

端到端 NPU 冒烟与 `vllm serve` 起服务见 skill `ascend-vllm-serve`。

## 6. 高频坑

1. **pin 没注释** → `--no-build-isolation` 下报 build dependencies 不满足，或 pip 把已装 torch 换版本（torch 与 torch_npu 强绑定，换错就 import 崩）。
2. **顺序错**：vllm 侧 `use_existing_torch.py` 要在 `pip install -r requirements/common.txt` 前；vllm-ascend 侧注释要在 `pip install -e .` 前。
3. `import vllm` 报 `No module named 'triton.experimental'`：vllm main 需要、triton-ascend 3.2.2 不带，`vllm_ascend/__init__.py` 会打 stub，**装完 vllm-ascend 即消失**。别单独升级/重装 triton（会覆盖 triton-ascend 的文件）；破坏了就 `pip uninstall -y triton triton-ascend && pip install "triton-ascend==<pin>"`。
4. 上游版本互斥属固有：vllm main 要 `fastapi>=0.133`，vllm-ascend 要 `fastapi<0.124`，实测装成 0.123.10 也能起服务 —— 保留 pip 的解析结果，别手动"修"。`pip check` 里 numpy/opencv、以及 CANN `set_env.sh` 经 PYTHONPATH 注入的包（mindstudio-kpp 等）都忽略。
   **但 numpy 这条"互斥"不是噪声，它会被静默升级**（2026-09-28 在 `.188` 实测）：vllm 侧 `pip install -r requirements/common.txt` 会把已装的 `numpy 1.26.4` 升到 `numpy 2.3.5`，而 `triton-ascend 3.2.2` 硬 pin `numpy==1.26.4`。看元数据：`vllm -> ['numpy']`（无约束）、`triton-ascend -> ['numpy==1.26.4', 'numpy; extra == "tests"']` → **1.26.4 是唯一同时满足两侧的值**。修法（降级后三层自检与 BI 判据全过）：
   ```bash
   pip install --no-deps numpy==1.26.4
   ```
   `--no-deps` 不能省，否则 pip 会重算依赖图、顺手把别的包又换掉。
5. 缺 build 依赖：`arctic-inference==0.1.1` 在 `--no-build-isolation` 下需要 nanobind/cmake/ninja，先带隔离预装它（及 fastokens / memfabric_hybrid / memcache_hybrid），或先 `pip install "cmake>=3.26" ninja`。**仅限 gcc≥9 的机器（如 `.190`）**；`.188` 的 gcc 8.3 编不了它，见坑 8。
6. AscendC 构建报 `No module named 'regex'` 或 CMake 找到 base conda 的 python：`export CONDA_PREFIX=<目标 env>`（或 `Python3_ROOT_DIR=<目标 env>`）后再装。详见 `ascend-conda-env` 坑 5（**注意：该现象是 `.190` 的历史记录，2026-09-23 在 `.188` 实测未复现**——conda 26.7.1 下路径环境 activate 后 `CONDA_PREFIX` 正确）。
7. 磁盘：算子编译产物与 pip 缓存很大，`TMPDIR` / `PIP_CACHE_DIR` 指到大盘，别把 `/` 写满。
8. **（`.188` 专属）gcc 8.3 的两个连带问题**：
   - `arctic-inference` 编不了 → §3 必须加 `--arctic`（与坑 5 的预装法相反，别搞混）。
   - 系统 libstdc++ 无 `GLIBCXX_3.4.26`，而 tiling 库 `libcust_opmaster_rt2.0.so` 依赖它 → 运行时（不是构建期）报 `dtype or format of parameter` / `NnopbaseExecutorDoTiling`，**看着像算子 API 用错，其实是缺符号**。修法：把 conda 环境里的新版 libstdc++ 放进一个目录并前置到 `LD_LIBRARY_PATH`：
     ```bash
     mkdir -p $BI_ROOT/compat_lib
     cp -a $CONDA_PREFIX/lib/libstdc++.so.6.0.34 $BI_ROOT/compat_lib/
     ln -sf libstdc++.so.6.0.34 $BI_ROOT/compat_lib/libstdc++.so.6
     export LD_LIBRARY_PATH=$BI_ROOT/compat_lib:$LD_LIBRARY_PATH
     ```
     （`.188` 的 `xmz_0921` 自带 `libstdcxx 15.2.0`，提供 `libstdc++.so.6.0.34` = GLIBCXX_3.4.34，够用。注意只前置 `compat_lib` 这个只放 libstdc++ 的目录，**不要**把整个 `$CONDA_PREFIX/lib` 加进去——那会让 `git` 崩，见 `ascend-conda-env` 坑 5。）
   - 完整报错原文（2026-09-23 实测）：`Error detail: /lib/x86_64-linux-gnu/libstdc++.so.6: version 'GLIBCXX_3.4.26' not found (required by .../libcust_opmaster_rt2.0.so)` → `RuntimeError: Engine core initialization failed`。
9. **"有 constraints 文件"≠"约束生效"**（2026-09-28 在 `.188` 挖到的真根因）：机器上确实**存在**一份锁 torch 家族 + `numpy==1.26.4` 的约束文件（如 `/root/torch_stack_constraints.txt`），但 **`PIP_CONSTRAINT` 从未被设置、shell rc 里也没有 `export`** → 这份文件**完全没生效**，坑 4 的 numpy 静默升级就是这么发生的。纪律：约束文件必须先显式生效，且每个新 shell 都要重设：
   ```bash
   export PIP_CONSTRAINT=/root/torch_stack_constraints.txt
   python -c "import os; print(os.environ.get('PIP_CONSTRAINT'))"   # 装之前确认不是 None
   ```

## 7. 在 Windows 上驱动远端（与 `ascend-env` §5 同套规则）

- 内联 ssh 命令里禁用 `<`、`"`、`$()`；**脚本内禁用 heredoc**（经 ssh stdin 传入会永久挂起）。
- 模式：本地写 .sh/.py → 管道推到远端 → `ssh -n <host> "bash /remote/x.sh"`（`-n` 只用于执行**远端已存在的文件**）；长任务 `setsid nohup bash x.sh > x.log 2>&1 < /dev/null &` 后轮询日志。
- **`ssh -n` 与"脚本走 stdin"互斥**：要把本地脚本管道过去（`$body | ssh <host> "tr -d '\r' | bash -s"`）**绝不能加 `-n`**——stdin 被 `/dev/null` 占掉后脚本空跑且**不报错**，只看到输出为空。
- 读远端中文文件/脚本一律显式 UTF-8（`[System.IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)` 或 `Get-Content -Encoding UTF8`）；PowerShell 5.1 默认按 GBK 解码，会把 UTF-8 中文读成乱码。
- 默认主机用别名 `a3`（=`.188`）；`.190` 用 `a3b`。`.188` 的 `/root/.bashrc` 第 36 行 `. /usr/local/Ascend/ascend-toolkit/set_env.sh` 指向的是**真实断链**（`latest -> /usr/local/Ascend/cann-9.1.0/cann`，该目录不存在；2026-09-23 复验 `readlink -f` 返回空），所以每条 ssh 都会在 stderr 打一行 `No such file or directory`。**只要显式 source 生产 CANN（`/home/x00886548/env/cann/cann_9_1_0/...`）就不受影响**；别依赖 `/usr/local/Ascend/ascend-toolkit`。详见 `ascend-cann-env`。
- `scripts/strip_torch_pins.py` 就是为这种非交互场景准备的（单文件、参数简单，替代 vim）；推送示例：
  `(Get-Content -Raw .\strip_torch_pins.py) -replace "`r`n","`n" | ssh a3 "tr -d '\r' > /remote/strip_torch_pins.py"`

## 8. 版本事实（**2026-09-28 复核，以脚本当次输出为准**）

- vllm-ascend main 当日 pin（**与 2026-09-17 记录完全一致，未漂移**）：torch 2.10.0 / torchvision 0.25.0 / torchaudio 2.10.0 / torch-npu 2.10.0.post4 / triton-ascend 3.2.2 / transformers 5.14.1 / fastapi<0.124.0 / fastokens 0.2.0 / arctic-inference 0.1.1 / memfabric_hybrid 1.2.0 / memcache_hybrid 1.2.0。
- **`.github/vllm-main-verified.commit` = `84030bbe3d74d99bad477a3d2e37a973ccd8865c`（2026-09-22 复核仍是这个值）**——这个文件比 vllm-ascend main 本身稳定得多，所以配对用的 vllm 不必跟着每次 main 更新而重装。
- vllm-ascend main HEAD 已从 2026-09-17 的 `dc2b9b25` 走到 2026-09-22 的 `10d23bf5`（主线漂移）；`.190` 上现装的是中间的 `cb79183`（0.1.dev86），三层验证通过。
- 实测配对：
  - vllm `84030bbe` + vllm-ascend `dc2b9b25` → 端到端 NPU 出文本（`.190`，2026-09-17）
  - vllm `84030bbe` + vllm-ascend `cb79183` → 三层验证通过，未重跑端到端（`.190`，2026-09-22）
  - vllm `84030bbe` + vllm-ascend **`bf439330c`** → 端到端 NPU 出文本，且批次不变性验证通过（**`.188`，2026-09-21**；带 `VLLM_BATCH_INVARIANT=1` 编，47 个 A3 算子 / 1219 个 .o）
- **两台机器装出来的 vllm-ascend 版本串形态不同**（都正常，别当异常）：`.190` 报 `0.1.dev86+gcb79183b7`，`.188` 报 `0.19.1rc2.dev2317+gbf439330c`。
- **2026-09-28 实测配对（`.188`）**：vllm tag `v0.30.0` = commit `ced6857afa0ea7b2e3f0846a62e1394e90f15607`；vllm-ascend `9df651d` = `9df651d0ba8d92720275857199d38fc99a485f85`。该 checkout 的 `.github/vllm-main-verified.commit` **正好等于 `ced6857af…`** → 这两个版本就是上游自认证的配对。版本串形态：`vllm 0.1.dev1+gced6857af.d20260928` / `vllm-ascend 0.19.1rc2.dev2454+g9df651d0b.d20260928`。

## 9. 维护记录

- **2026-09-22 复核（DSH skill 巡检）**：上游 pin 与 `vllm-main-verified.commit` 均未变化，本流程判定**仍然有效**。本次改动：§1 补 catlass 子模块在 GitCode；§3 补"非 torch 但带版本约束的 build 依赖"清单（含 `transformers==5.14.1` 这个最易踩项）与脚本实测记录；§5 修正 triton ascend backend 校验（editable 安装下原写法恒为 `False`）；§8 更新到 2026-09-22 实测值。配套修复 `scripts/strip_torch_pins.py` 的 `re.split(..., maxsplit=1)` 弃用告警。
- **2026-09-22（默认机器切换为 `.188`）**：**默认机器由 `.190` 改为 `.188`**（别名 `a3`；`.190` 降为 `a3b`）。本次改动：
  1. 头部与 §0 补默认机器、别名、免密状态，以及**gcc 版本决定做法**的前置判断；
  2. §3 新增 `--arctic` 用法（`.188` 的 gcc 8.3 必须加）并说明与 §6 坑 5 预装法**相反**；补 `--arctic` 模式的实测记录（6+5 行、剩 25 项、幂等）；
  3. §4.1 补 `csrc/build_batch_invariant_ops.sh` 的 `--max-time 5` → 300 修复（`.188` 批次不变性构建必做）；
  4. §5 补"别读 `vllm_ascend.__version__`"（`.188` 无该属性）；
  5. §6 新增坑 8（`.188` gcc-8 的 arctic 编不了 + GLIBCXX_3.4.26 缺失 → compat_lib 兜底）；
  6. §7 更新主机别名为 `a3`，补 `ssh -n` 与 stdin 管道互斥、PowerShell UTF-8 解码、`.188` bashrc stderr 噪声；
  7. §8 补 `.188` 实测配对 `bf439330c` 与两机版本串形态差异。
  配套改动：`scripts/strip_torch_pins.py` 新增 `--arctic` 开关（默认关闭，`.190` 行为不变）、`--help`/未知参数处理、按包区分注释标记，并已在 `.188` 实测通过。
- **2026-09-23（skill 套件拆分后的交叉引用修正）**：原 `ascend-vllm-env` 已拆为 `ascend-env`（总纲）+ 7 个子 skill（含本文件），本文件所有指向它的引用已改为指向对应子 skill；§0 的 triton-ascend 源由 huaweicloud 改为**已实测可用的 osinfra**（`https://triton-ascend.osinfra.cn/pypi/simple`）；§6 坑 6 的 CONDA_PREFIX 现象补注「`.190` 历史记录，`.188` 未复现」；§6 坑 8 补 GLIBCXX 逐字报错原文；§7 的 `.188` bashrc 说明由「正常噪声」修正为「真实断链」。
- **2026-09-28（`.188` 实跑复核，共 5 处）**：
  1. §0 修正被证伪的断言「`.188` 加 `--arctic` 就够了」→ 补「gcc 8.3 编 `vllm_ascend_C` 必失败，要换 gcc 10 工具链」；
  2. 新增 §4.2：借 conda 工具链 env 的 `CC`/`CXX`/`C_COMPILER`/`CXX_COMPILER`、**禁止前置其 `bin` 到 `PATH`**、以及"取证用了哪个编译器要看哪"；
  3. §4.1 补批次不变性假阳性（无 `set -e`）与三条判据、`HAS_ASCENDC_BATCH_INVARIANT` 的真实模块位置与反面探针；
  4. §6 坑 4 补 numpy 静默升级（`1.26.4` 是两侧唯一交集），新增坑 9「`PIP_CONSTRAINT` 未 export = 约束没生效」；
  5. §1 补短 SHA 不能 fetch、本地镜像浅克隆可直接 fetch tag；§8 补 2026-09-28 配对（`v0.30.0` / `9df651d`，即 verified commit 自身）。
  与「跑得起来」相关的部分（TP≥2 多卡起服务、思考型模型 CoT）写在 `ascend-vllm-serve`，本文件不重复。
