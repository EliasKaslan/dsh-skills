# vllm-ascend-source-install 维护记录（原 §9 原样拆出）

> 从 `vllm-ascend-source-install/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

## 9. 维护记录

- **2026-10-09（融合 `.188` 源码安装实测：1 处证伪断言修正 + 1 处进度判据修正 + 3 处新增）**：
  1. **修正 §0 / §3 / §6 坑 8 —— `--arctic` 由「`.188` 必加」改为按编译器限定**：只在编译器不支持 C++20（系统 gcc 8.3）时才需要；`CC`/`CXX` 指向 conda gcc 10.4.0 时 `arctic-inference 0.1.1` 由 pip 直接装上、`import arctic_inference` 成功，且该环境全程未跑 strip（`git status --porcelain` 0 行）。限定范围仅限 `arctic-inference` 这一项，torch 家族注释的理由不变。
  2. **修正 §4 构建进度判据**：删掉「`find csrc/build -name '*.o' | wc -l` 当进度」（1421 个 `.o` 被 `kernel_meta_<Op>_<hash>/` 实例淹没、非线性）；改为**确定性产物**：`.run` 存在（实测 16,268,894 B）+ `_cann_ops_custom` 文件数量级（1162 文件 / 50,988,328 B）；写明 `binary` 目录数（208 vs 0）不能当判据、编译器退出看 `bisheng` / `opc.py` 归零、`Ascend910_9382` 与 `ascend910_93` 不是不匹配。
  3. **新增 §5.3**：平台层失败的第一诊断点 `VLLM_TARGET_DEVICE=cpu` —— `vllm/vllm/platforms/__init__.py:237` 在任何插件之前就 return cpu 平台，插件异常被 `except Exception:` 吞成 `debug` 级；纪律：激活脚本绝不 export，排查第一步 `echo $VLLM_TARGET_DEVICE`。
  4. **新增 §5.4**：拿已知 good 的参考环境 `REF=/mnt/share/vllm/conda_envs/xmz_0921`（**只读、别 kill 它的进程**）当 oracle 的四种比对法（commit 佐证 / 打包形态 / `entry_points.txt` 逐字比对 / `pip check` 既定噪声）。
  5. **新增 §6 坑 16**：版本串形态「正常劣化」不要修（`--depth 1` 无 tag ⇒ `0.29.0rc1`；`vllm.__version__` 的 `.d20261009` 合成串），也别为此设 `VLLM_VERSION_OVERRIDE`。
  6. §4.2 补一条**实测可用的整条调用**（含 `MAX_JOBS=8`、`PIP_CONSTRAINT` 与四个编译器变量）。
- **2026-10-08（第三批：1 处勘误 + 1 处补全 + 6 处新增，全部为 `.188` 实测）**：
  1. **勘误 §5.1**：原「按 release tag 装完**必须** `export VLLM_VERSION=<tag>`，否则 `vllm_version_is` 为 `False`」**被证伪**——vllm `v0.23.0` 的 `setup.py` 只认 `VLLM_VERSION_OVERRIDE`（逐字 `946`/`947` 两行），且不导任何变量时 `vllm_version_is("0.23.0")` 本来就 `True`；该函数是**版本线**判定（`0.23.1.dev0+g0fc695fc6…` 实测 `True / False / False`）。§6 坑 10/11、§7.1 第 5 项已同步改掉，**description 里的「须 export VLLM_VERSION」也一并修正**。
  2. **§6 坑 15 补全（原结论「`manylinux_2_31` wheel + glibc 2.28 装不上 → 回退 sdist」成立，不要改）**：实测 `.188` glibc `2.28`、`pip debug --verbose` 平台标签上限 `manylinux_2_28`，而 PyPI 上 `llguidance 1.7.6` 的 x86_64 wheel 就是 `llguidance-1.7.6-cp39-abi3-manylinux_2_31_x86_64.whl`（1.7.x 每版 15 个 wheel）⇒ 本机**有 wheel 但装不上**。**新增方法论教训**：`pip download --only-binary=:all:` 的成败**不能**用来判「某包有没有 wheel」——它分不清「没有 wheel」与「有 wheel 但平台标签不兼容」，必须 `curl -s https://pypi.org/pypi/<pkg>/<ver>/json` 读 `urls[].filename`。修法 `--only-binary=llguidance` 的机理补全为「本机无可用 wheel ⇒ pip 索引候选集为空 ⇒ 采用已安装的 1.7.6」，并保留「预先装好 llguidance 不足以绕过」的反例与六条取证判据。
  3. **新增 §6 坑 1b**：`pip check` 不是验收判据（可用环境固有 2 条：opencv→numpy>=2 与 prometheus-fastapi-instrumentator→starlette）。
  4. **新增 §6 坑 4 的第二种失败模式**：不是"静默升级"而是 **`ResolutionImpossible`**（`requirements/common.txt:36` 的 `opencv-python-headless>=4.13.0` × `opencv 5.0.0.93` 要 `numpy>=2` × `triton-ascend 3.2.2` 锁 `numpy==1.26.4`），附逐字两行报错与五步修法（两份约束文件 + `--only-binary=llguidance` + `--no-deps --no-index --find-links` 放回 numpy + `pip install -e . --no-build-isolation --no-deps`）。
  5. **新增 §3 实测清单**：`strip_torch_pins.py --arctic` 跑完后 `requirements.txt` 全文 39 行（25 个活跃包名 / 6 行注释 = 5 个 torch 家族 pin + `arctic-inference`）、`setup.py:539 install_requires=get_requirements()` 不过滤、`memfabric_hybrid`/`memcache_hybrid` 1.2.1 在 PyPI 上有。
  6. **新增 §4 两条**：真构建目录 `csrc/build` 与 `csrc/build/cann-ops-transformer-custom_linux-x86_64.run` 打包产物、load≈287 下约 20 分钟；以及 `--no-build-isolation` 需预装 `cmake ninja wheel`。
  7. **新增 §6 坑 9 注**：`PIP_CONSTRAINT` 里写 `torch==2.10.0+cpu`（按 `torch-npu 2.10.0.post4` 的 METADATA 逐字）。
- **2026-10-08（同轮第二批，共 4 处：2 修正 + 2 新坑）**：
  1. **§7 的 base64 推送示例自己就是坑**：`(Get-Content -Raw $f)` 在 PS 5.1 按 **GBK** 解码 → `strip_torch_pins.py`（含中文 docstring）推过去**字节数 7343 → 7819**，远端 `python` 报 `SyntaxError: invalid non-printable character U+E15E`。已改为 `[IO.File]::ReadAllBytes($f)`，并把「**`md5sum` 与本地 `Get-FileHash -Algorithm MD5` 一致才算推送成功**」写成硬判据——这一条能同时兜住 GBK 改坏 / CRLF / 截断。
  2. **§6 坑 6 的「`.188` 未复现」被证伪**：真触发条件是**登录 shell 落在 conda base**，与机器型号无关。机理：`Modules/FindPython/Support.cmake` 把 `ENV CONDA_PREFIX` 当 virtualenv 优先搜，且 `find_package(Python3)` 默认按 VERSION 取最高版本 → **把 base 剔出 `PATH` 也拦不住**，仍会选中 base 的 python3.14 报 `ModuleNotFoundError: No module named 'regex'`。另补：`csrc/build_aclnn.sh` **保留 `csrc/build`**（`HI_PYTHON` 是 `CACHE STRING` → 选错的解释器跨轮存活），清缓存必须带 `csrc/build`。
  3. **新增坑 14**：系统 `cmake 3.13.4 < 3.16` → `CMake 3.16 or higher is required. You are running version 3.13.4`；修法是前置**目标 python env** 的 `bin`（含 cmake 4.4.4 + ninja、无编译器），并写明它与 §4.2「绝不前置**工具链 env** 的 `bin`」是**两个不同 env**、不冲突。
  4. **新增坑 15**：`llguidance` 在本机只能源码编（唯一 x86_64 wheel 是 `manylinux_2_31`，`.188` 是 glibc 2.28），而 sdist 的 `rust-toolchain.toml` 逼 rustup 去下 `1.95.0`/clippy/rustfmt → 卡在 `Preparing metadata` 十几分钟；`PATH=/root/.cargo/bin:$PATH` + `RUSTUP_TOOLCHAIN=stable-x86_64-unknown-linux-gnu` 后 **40 秒**编完。
- **2026-10-08（release tag 安装实测：双 `v0.23.0` 端到端跑通，共 5 处）**：
  1. **新增 §1.1「从 release tag 装时的配对规则」**：`.github/vllm-main-verified.commit` 只在 `main` 上可信——`v0.23.0` 里它是 `ee0da84…`（`vLLM main` 取向的 CI 验证 commit），而 release commit `5cb98ca` 的提交信息逐字写着 `- vLLM version: v0.23.0`，即 tag 配对目标是 vllm 的**同名 tag**（实测端到端出文本）；§1 配对条加例外指针。
  2. **新增 §5.1 `VLLM_VERSION` 逃生口（release tag 安装必需品）**：tag 装时 setuptools_scm 报 `0.23.1.dev0+g0fc695fc6.d20261008`，而 `v0.23.0` 有约 20 处 `vllm_version_is("0.23.0")` 分支 → 必须 `export VLLM_VERSION=0.23.0`；给两向可复制判据（不设 `False` → 设了 `True`）与 `Unknown vLLM environment variable detected: VLLM_VERSION` 无害噪声。
  3. **新增 §5.2 AscendC 算子产物判据**：产物在**包内** `vllm_ascend/_cann_ops_custom/vendors/custom_transformer/`（实测 1013 文件 / 87M / 208 个 `binary` 目录），**不在** `$ASCEND_OPP_PATH/vendors/`（那里只有 `batch_invariant`）→「opp/vendors 里没有就是没编」是**假阴性**；补 `version.info`（`custom_opp_compiler_version=9.1.0`）、`_build_info.py`（`__device_type__ = 'A3'`）、扫 `/proc/self/maps` 判 CANN 归属三条取证，以及「`vllm_ascend_C` 公开符号只有 3 个、别拿符号个数判编译成败」。
  4. **§6 新增坑 10 / 11 / 12 / 13**（tag 照抄 verified.commit 装错版本、`VLLM_VERSION` 未设、算子产物假阴性、env 脚本缺项）；**新增 §7.1「远端 env 交付脚本必备 5 项」**（剔 base 的 `PATH` / `CONDA_PREFIX` / 只放 libstdc++ 的 `compat_lib` / `set +u` 包住 source / `VLLM_VERSION`）。
  5. **§8 补 `v0.23.0` tag 事实与官方版本矩阵**，并记下矩阵（`torch_npu 2.10.0.post2` / `Triton Ascend 3.2.1`）与 tag `requirements.txt`（`2.10.0.post4` / `3.2.2`）**不一致、实装以 `requirements.txt` 为准**。
- **2026-10-08（并行化 + 版本不纠结，用户要求"大刀阔斧"）**：
  1. **§1 改成两仓真并行 clone**（＝ `ascend-env` §3.1 的 lane P4）：配对 commit 用 `raw.githubusercontent.com/…/vllm-main-verified.commit` **免 clone** 取（实测返回 200），于是 vllm 的 `git fetch --depth 1 origin <sha>` 与 vllm-ascend 的 clone + submodule 可**同时发**；`wait` 后用两仓 `log --oneline -1` 判完成（**不看进程**）。新增「这条 lane 不 source CANN、不装任何包」的边界说明。**修正**：vllm 那条子 shell 的重定向原先只罩住最后一条 `git checkout`（`init`/`fetch` 的输出会丢），已改为罩整个子 shell（`( … ) > "$SRC/log/clone_vllm.log" 2>&1 &`）。
  2. **新增 §0.1 版本纪律**（用户 2026-10-08 定）：版本**只参考 vllm-ascend 的 `requirements.txt`**（pin 注释里保留原文，读注释即得）、**vllm 的 `requirements/*` 只用来补运行期依赖、禁止拿它对齐版本**、**依赖冲突一律不管**；唯一硬判据是 §5 + `ascend-env` §4。§2 与坑 4 已同步降级（坑 4 由"必修"改为"只在真报错时回退一次"）。
  3. §8 补 2026-10-08 实测：vllm-ascend main `0bb59db16…`（相对 09-28 已漂移）、vllm `v0.30.0` = `ced6857af…`、raw 上的 verified commit 仍是 `ced6857af…`。
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

