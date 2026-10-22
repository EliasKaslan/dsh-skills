---
name: vllm-ascend-source-install
description: 从源码装 vllm + vllm-ascend 配对流程——main 按 `.github/vllm-main-verified.commit` 配 vllm（VLLM_TARGET_DEVICE=empty）；release tag 配同名 tag；VLLM_VERSION 在 v0.23.0 失效，改用 VLLM_VERSION_OVERRIDE；torch 家族 pin 先注释；VLLM_BATCH_INVARIANT 默认不导出。适用于"装或重装 vllm-ascend / 报 vllm_version_is 为 False / 报 ResolutionImpossible 或 numpy 冲突 / pip 卡在 llguidance / 复用已有 torch_npu / 报 build 依赖不满足（torch pin/nanobind）/ 报 metadata-generation-failed"。不适用：起服务排障 → 用 `ascend-vllm-serve`；torch 栈装不上 → 用 `ascend-torch-npu`。
whenToUse: 要决定「怎么把 vllm 与 vllm-ascend 从源码装进已有环境」时用：按 verified commit 配对两仓、复用已装 torch 栈、编译 AscendC 算子。模型看不到本节。
---

# vllm + vllm-ascend 源码安装（配对 commit + 复用已有 torch 栈）

范围：只做 vllm 与 vllm-ascend 两个 `pip install -e .`。**前置栈的从零搭建见总纲 skill `ascend-env`**（它按顺序指向 `ascend-server-layout` / `ascend-cann-env` / `ascend-conda-env` / `ascend-torch-npu` / `ascend-triton-ascend`）；跑起来见 `ascend-vllm-serve`。

**默认机器：`root@192.168.13.188`（文档代称 `a3`，可用）**；备用 `root@192.168.13.190`（代称 `a3b`，**2026-10-22 整机不可达**）；A5 `root@177.8.21.1`（代称 `a5`，**需连 A5 VPN 后可达**，见 `univpn-vpn`）。**本机 ssh config 没有这几个别名，命令直连 IP**，见 `ascend-env` §1。`.188` 已配公钥免密（2026-10-22 复核仍有效），密码 fallback 见 `ascend-env/credentials.txt`。**两机差异（尤其 gcc 版本）会直接改变本流程的做法**，见下——`.190` 恢复后先复核 gcc / python 再决定要不要套用。

## 何时调用

**加载本 skill 当：**
- 要把 vllm 与 vllm-ascend 用 `pip install -e .` 装进已有环境（或重装、换 commit），包括 `--no-build-isolation` 报 build dependencies 不满足。
- 要按 vllm-ascend 当次 checkout 的 `.github/vllm-main-verified.commit` 配对 vllm 版本。
- 不希望 pip 按 pin 换掉已装好的 torch / torch_npu / triton-ascend，或问要不要开 `VLLM_BATCH_INVARIANT`。
- 要**验收批次不变性**：判"BI 装进去了没有" → §4.1 / §4.3；判"算子结果真的不随批构成变" → **§5.5**（算子级验收配方）。

**不要用本 skill（转交）：**
- 服务起不来、离线推理 / 冒烟 / 权重校验 / 运行时排障 → 用 `ascend-vllm-serve`（本 skill 只管「装得上」，不管「跑得起来」）。
- **KDA 系模型（Kimi-K3 / GLM5next）运行时还需要 `fla_npu`，且它有 glibc ≥2.32 / 2.34 门槛** → 用 `ascend-vllm-serve`（正文归它，本文件只留这条指针）。
- torch 栈本身缺或装不上 → 用 `ascend-torch-npu`；triton-ascend 相关 → 用 `ascend-triton-ascend`；CANN → 用 `ascend-cann-env`。
- 判某模型在昇腾 / vllm-ascend 侧的适配程度与缺口 → 用 `ascend-model-adaptation-recon`。
- 上游仓库 docs 缺口审计（内部需求 vs docs 主线） → 用 `upstream-docs-refresh-audit`。
- 新增 / 移动 e2e 用例要进 CI、为什么报 MISSING → 用 `vllm-ascend-e2e-ci-wiring`。

**前置**：CANN 已装且每次操作前 `source` 过 toolkit 与 nnal/atb；环境里已有 torch / torch-npu / triton-ascend（见 §0）。 ／ **后继**：`ascend-vllm-serve`。

## 0. 前置（不满足先别往下走）

- Linux + 已装 CANN，且每次操作前 `source` 过 toolkit 与 nnal/atb 两段 `set_env.sh`；gcc/g++ ≥ 8（支持 C++17）**但编自带 C++ 扩展要 ≥ 9（见下一条与 §4.2）**；`MAX_JOBS` 按机器核数设，共享机别打满。
- **先确认 gcc 版本，它决定 §3 要不要加 `--arctic`、§4.2 要用哪个编译器、以及要不要做 GLIBCXX 兜底**：
  - `.188`（默认）：系统**只有 gcc/g++ 8.3**，且系统 libstdc++ **无 `GLIBCXX_3.4.26`** → §3 **用这套系统 gcc 编时**必须加 `--arctic`（`CC`/`CXX` 已指向 conda gcc 10.4.0 时不需要，见 §3 的范围限定）；**但 `--arctic` 只解决 `arctic-inference` 编不过的问题，编 C++ 扩展 `vllm_ascend_C` 时 gcc 8.3 会直接失败**（torch 头文件要求 GCC ≥ 9）→ 必须按 §4.2 换成 conda 工具链里的 gcc 10；运行时还要 compat_lib 兜底（见 §6 坑 8）。
  - `.190`（备用）：gcc/g++ 10.2，系统 libstdc++ 够用 → §3 不加 `--arctic`（反而要预装它，见 §6 坑 5），§4.2 也不用做。
- **硬条件：环境里已经有 torch / torch-npu / triton-ascend** —— 本流程会故意注释掉它们的 pin，不会去装它们。先确认：

```bash
python3 -c "import torch, torch_npu; print(torch.__version__, torch_npu.__version__)"
pip show triton-ascend | head -n 2
npu-smi info -t board -i 0 -c 0 | head -n 5     # -c 0 才有 Chip Name，setup.py 靠它探 SOC
```

- 缺 torch 栈：先按 vllm-ascend **改动前** `requirements.txt` 里的 pin 预装（§3 的脚本会把原 pin 打印出来），装完再进 §3：

```bash
pip install torch==2.12.0+cpu torchvision==0.27.0+cpu torchaudio==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
pip install torch-npu==2.12.0
pip install "triton-ascend==3.2.2" --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple
# 上面是车道 B 的实测值；车道 A 换成 2.10.0+cpu / 2.10.0.post4 / 0.25.0 / 2.10.0（就照这些数字填，别留 `<x>` 尖括号——bash 会当重定向）
# triton-ascend 不在 PyPI 上，必须带这个 --extra-index-url（2026-09-23 实测 osinfra 上只有 3.2.2/3.2.1）；细节见 skill `ascend-triton-ascend`
```

### 0.1 版本纪律（2026-10-08 用户定，**优先于本文其它版本说法**）

- **版本只参考 `vllm-ascend` 的 `requirements.txt`**。它的 torch 家族 pin 被本流程注释掉之后，**原文就留在注释里**（实测 `.188` 现成 checkout：`# torch==2.10.0  # pin removed -> reuse the torch stack installed in this env`，同款还有 torch-npu 2.10.0.post4 / torchvision 0.25.0 / torchaudio 2.10.0 / triton-ascend 3.2.2）——读注释即得版本。
- **`vllm` 仓的 `requirements.txt` 不用参考**：`pip install -r requirements/common.txt` 只是为了补齐 vllm 的运行期依赖，**不要拿它的输出反推或"对齐"版本**。
- **依赖冲突不用管**：坑 4 那类 numpy / fastapi / starlette 互斥、`pip check` 噪音、CANN `PYTHONPATH` 注入包，**一律不算失败**。唯一硬判据是 §5 的分层验证 + `ascend-env` §4 三层验收。
- 因此**不要为了"版本对齐"来回重装**：装得上、`import` 得动、NPU 可用即通过。

## 1. 取版本对（＝ `ascend-env` §3.1 的 lane P4；两仓**并行** clone）

配对规则不变：vllm 必须用 vllm-ascend 当次 checkout 里的 `.github/vllm-main-verified.commit`。**但这个 commit 不必先 clone 才能拿到**——raw 上直接读，于是两个 clone 能**真并行**（2026-10-08 在 `.188` 实测该 URL 返回 200 且内容为 `ced6857afa0ea7b2e3f0846a62e1394e90f15607`）：

```bash
SRC=/home/vllm/x00886548/envbuild/src; mkdir -p "$SRC/log"; cd "$SRC"

# ① 免 clone 拿配对 commit（要用 release 就把 URL 里的 main 换成目标 tag/分支）
VLLM_COMMIT=$(curl -sL -m 60 \
  https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/.github/vllm-main-verified.commit)

# ② 两仓同时 clone（各写各的日志；子模块留在 vllm-ascend 那条里）
( git clone --depth 1 https://github.com/vllm-project/vllm-ascend.git \
    > "$SRC/log/clone_ascend.log" 2>&1
  cd "$SRC/vllm-ascend" \
    && git submodule update --init --recursive >> "$SRC/log/clone_ascend.log" 2>&1 ) &

( git init -q vllm && cd vllm \
    && git remote add origin https://github.com/vllm-project/vllm.git \
    && git fetch --depth 1 origin "$VLLM_COMMIT" \
    && git checkout -q FETCH_HEAD ) > "$SRC/log/clone_vllm.log" 2>&1 &

wait
git -C "$SRC/vllm-ascend" log --oneline -1
git -C "$SRC/vllm"        log --oneline -1
cat "$SRC/vllm-ascend/.github/vllm-main-verified.commit"
```

- **判完成**：两仓 `log --oneline -1` 都有输出，且 vllm 的 HEAD == 文件里那个 commit（**看产物，不看进程**）。
- 子模块 `csrc/third_party/catlass` 在 **gitcode.com/cann/catlass.git**（不是 GitHub），源码装必做，所以它挂在 vllm-ascend 那条 lane 里（`git ls-remote` 实测 gitcode 可达）。
- 这条 lane **不 source CANN、不装任何包**，可与 CANN 三包下载（P1）/ conda 建环境（P2）/ torch 栈 whl 预下载（P3）同时跑。全程编排见 `ascend-env` §3.1。
- `SRC` 必须落 `/home/vllm`（源码 + 后面 csrc 构建产物都很大）。
- 两仓是**配对**的：vllm 必须用 vllm-ascend 当次 checkout 里的 `.github/vllm-main-verified.commit`，不要用 vllm 自己的 tag 或最新 main。
  > **例外：按 release tag 装时反过来** —— 该文件记的是 `vLLM main` 的 CI 验证 commit（`v0.23.0` 上是 `ee0da84…`），tag 装要改用 vllm 的**同名 release tag**，见 §1.1。
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

### 1.1 从 release tag 装时的配对规则（2026-10-08 实测：「双 `v0.23.0`」端到端跑通）

**纪律**：从 release tag 安装时，配对用 **vllm 的同名 release tag**；**不要照抄 tag 里的 `.github/vllm-main-verified.commit`** —— 该文件记的是 **`vLLM main`** 的 CI 验证 commit（`v0.23.0` 上是 `ee0da84…`，与 vllm `v0.23.0` tag 的 `0fc695f` 不同）。**只有 main 分支安装才用那个文件。**

逐字证据（vllm-ascend `v0.23.0` 的 release commit `5cb98ca`，标题 `[v0.23.0][Doc][Misc] Prepare for v0.23.0 official release`，提交信息尾部直接写明配对目标）：

```text
- vLLM version: v0.23.0
- vLLM main:
https://github.com/vllm-project/vllm/commit/ee0da84ab9e04ac7610e28580af62c365e898389
```

- 即 release 的配对目标是 vLLM **`v0.23.0`（同名 tag）**；`ee0da84ab9e04ac7610e28580af62c365e898389` 是「**vLLM main**」取向的 CI 验证 commit（日期 2026-06-28，形态是 `[KV-Offloading] … (cherry picked from commit 798185d…)`），**不是** tag 配对目标。
- 实测该组合端到端离线推理出文本（Qwen2.5-0.5B，`rc=0`）。
- 取值一句话（`--tags` 列表里按版本号精确匹配，别用分支名）：
  ```bash
  git ls-remote --tags https://github.com/vllm-project/<repo>.git | grep -E "refs/tags/v?<版本>$"
  ```
- `VLLM_VERSION` 逃生口见 §5.1，算子产物落点判据见 §5.2。

## 2. 装 vllm（不编 C++）

```bash
cd $SRC/vllm
export VLLM_TARGET_DEVICE=empty
# ① 先看 use_existing_torch.py 在不在：在 → 必须先跑（删 requirements/* 与 pyproject 里 torch 家族的行）
[ -f use_existing_torch.py ] && python3 use_existing_torch.py
# ② 再查 pyproject 的 [build-system].requires 有没有钉 torch（今日 main 有，见坑 17）
grep -n '"torch\|"torch-npu' pyproject.toml
pip install -r requirements/common.txt
pip install setuptools_rust setuptools_scm
pip install -e . --no-build-isolation          # 必须在已 source CANN 的 shell 里（坑 18）
```

- **`use_existing_torch.py` 不是永久的（2026-10-22 实测 `a98247ab` 上 404，文件已被上游删除）**：今日 main 的 `requirements/common.txt` 也**已不含任何 torch pin**，所以这一步对今日主线是**空操作，直接跳过**。判据只认现场 `ls`，不要照抄"必须先跑"。
- 它在老版本上仍必须在 `pip install -r` **之前**，否则 pip 会按 pin 换掉已装 torch。
- `pip install -r requirements/common.txt` 只是**补 vllm 的运行期依赖**；`requirements/*` 与 `pyproject.toml` 里 torch 家族那几行已被上一步删掉。**它的输出去反推/对齐版本是禁止的**（见 §0.1）；它把某个非 torch 包装成别的版本也**不用管**。
- `VLLM_TARGET_DEVICE=empty` 使 `ext_modules=[]`，vllm 不编 C++，gcc 版本低也无所谓；rust 扩展是 optional。
- 此时 `import vllm` 可能报 `No module named 'triton.experimental'`，属预期，装完 vllm-ascend 自动消失（坑 3）。
- **这一步属串行段 S3 的第一半**，必须在 4 条 lane 的 barrier 之后做（它要求 CANN 已 source、环境里已有 torch 栈、源码已 clone 好）。

## 3. 注释掉 vllm-ascend 里 torch 家族的版本 pin（等价 vllm 的 use_existing_torch.py）

vllm-ascend 仓没有 `use_existing_torch.py`，用本 skill 自带脚本代替（幂等、自动备份 `<file>.pinbak`、TOML 自校验并失败回滚）：

```bash
cd $SRC/vllm-ascend
python3 "$SKILL/scripts/strip_torch_pins.py" .                 # .190 等 gcc>=9 的机器
python3 "$SKILL/scripts/strip_torch_pins.py" --arctic .        # 仅当编译器不支持 C++20（如 .188 系统 gcc 8.3）才需要；CC/CXX 是 conda gcc 10.4.0 时不需要（见下）
# 先 export SKILL=<本 skill 目录>（如 ~/.dsh/skills/vllm-ascend-source-install），别把尖括号路径直接粘进 shell
git diff -- requirements.txt pyproject.toml                # 确认只动了目标行
```

**`--arctic` 是干什么的**：额外把 `arctic-inference==0.1.1` 也注释掉。它的 C++ 扩展需要 C++20 `<span>`，**gcc 8.3 编不过**；该包只被 vllm 的可选 suffix-decoding 路径使用，vllm-ascend 源码不引用它，所以注释掉是安全的。默认不加这个 flag，`.190` 上的行为与以前完全一致（那里 gcc 10.2 能编，应改用 §6 坑 5 的预装法）。

> **2026-10-09 实测补的范围限定（`--arctic` 不是无条件必做）**：判据是**编译器支不支持 C++20**，不是"哪台机器"。`CC`/`CXX` 指向 conda-forge gcc/g++ **10.4.0**（§4.2 那套 `bi_0921` 的 `x86_64-conda-linux-gnu-gcc` / `-g++`）时，`pip install -r requirements.txt` 实测 **`RC=0`**，`arctic-inference-0.1.1` 由 pip 直接装上、`import arctic_inference` **成功**；该环境全程**没跑过 strip**（`git -C src/vllm-ascend status --porcelain` = **0 行**，§3 一行都没改，安装照样成功）。⇒ 有 conda gcc 10.4.0 这类 C++20 编译器时 `--arctic` **不必要**；只有系统 gcc 8 这类不支持 C++20 的编译器才必须加。
> 范围仅限于 `arctic-inference` 这一项：**torch 家族注释（第 3 条）与 §6 坑 1 的理由不变**（本轮那个环境另有 `PIP_CONSTRAINT` 兜底，见 §6 坑 9）。

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

**`--arctic` 跑完后 `requirements.txt` 长什么样（2026-10-08 实测，全文 39 行）** —— 用来核对"注释到底生效没有"：
- **活跃行（25 个包名）**：`cmake>=3.26` / `decorator` / `einops` / `numpy` / `packaging` / `pip` / `pybind11` / `pyyaml` / `regex` / `scipy` / `pandas` / `psutil` / `setuptools>=64` / `setuptools-scm>=8` / `wheel` / `xgrammar>=0.1.30` / `pandas-stubs` / `compressed_tensors>=0.11.0` / `msgpack` / `quart` / `numba` / `memfabric_hybrid` / `memcache_hybrid` / `transformers==5.5.4` / `fastapi<0.124.0`。
- **被注释掉的 6 行** = 5 个 torch 家族 pin（`torch==2.10.0`、`torch-npu==2.10.0.post4`、`torchvision==0.25.0`、`torchaudio==2.10.0`、`triton-ascend==3.2.2`）+ `arctic-inference==0.1.1`。
- 关于 install_requires：`setup.py:539` 是 `install_requires=get_requirements()`，**不做任何过滤** ⇒ 上面活跃行的版本约束会原样进入安装期解析（这也是坑 4 把 numpy 摘出去再放回的前提）。
- 两个容易以为装不上的包：`memfabric_hybrid 1.2.1` / `memcache_hybrid 1.2.1` **PyPI 上有**（NJU 镜像实测能装到）。

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
- 构建中监控：`grep -c "error:" build.log`。**别拿 `find csrc/build -name '*.o' | wc -l` 当进度**（2026-10-09 实测）：`.o` 计数实测 **1421**，但被 `build/binary/ascend910_93/gen/kernel_meta_<Op>_<hash>/` 的**实例**淹没（每个算子实例各一份），**非线性** ⇒ 数它得不到"编到几成"。通用教训见 `orchestrating-subagents` §9.12。
- **确定性进度判据（2026-10-09 实测，判"编完没有"只认这两条）**：① 下面那条**打包产物** `cann-ops-transformer-custom_linux-x86_64.run` **存在** ⇒ `--target package` 阶段**确已完成**；② 配套看 `_cann_ops_custom` 的**文件数量级**（本轮 **1162 文件 / 50,988,328 B**）。**别把 `binary` 目录个数写死成判据**：§5.2 那次记的是 `208` 个，本轮是 **0**（布局不同）⇒ 判「`.run` 存在 + 文件数量级」，不判 `binary` 目录数。
- **编译器退出判据（别去等 `ccec` / `cc1plus`）**：AscendC 真正的编译器是 **`bisheng`** 与 CANN 的 **`opc.py`** ⇒ `pgrep -c -f bisheng` = **0** 且 `pgrep -c -f opc.py` = **0** 才算编译进程收摊。
- **`-soc_version=Ascend910_9391` / 构建目录 `ascend910_93` 与 `torch.npu.get_device_name(0)` = `Ascend910_9382` 不是不匹配**（同族；`get_soc_version()` = `253`）⇒ **不要据此判定编译目标错**、也别去改 `SOC_VERSION`。
- **判"编到哪一步了"要看真目录**（2026-10-08 实测）：真正的构建目录是 **`src/vllm-ascend/csrc/build`**，**不是** `src/vllm-ascend/build`；AscendC 产物落在 `src/vllm-ascend/vllm_ascend/_cann_ops_custom/vendors/custom_transformer`（本轮实测 **87 MB / 1013 个文件**，与 §5.2 一致）。
- 另有一个**打包产物**：`csrc/build/cann-ops-transformer-custom_linux-x86_64.run`（由 `cpack` + `makeself.sh --gzip` 打出）——有它说明 `--target package` 那一步真跑完了（2026-10-09 实测 **16,268,894 B**）。
- **耗时实测**：这一装（`cmake --build . --target package -j32` + ninja + cpack 打包）在 **load≈287** 的机器上约 **20 分钟**。别按空载经验设超时。
- **`--no-build-isolation` 需要先预装 `cmake ninja wheel`**：vllm 的 `[build-system].requires` 要 `cmake>=3.26.1` / `ninja`，而 `requirements/common.txt` **不带**这两个 ⇒ 走这条路前先 `pip install cmake ninja wheel`；另需 `setuptools_rust setuptools_scm`（§2 已含）。

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
  > **构建期日志侧的独立判据**（run 包与 whl 包**各自的** `installed successfully` + `SOC_ARG=ascend910_93` + `ascend_install_rc=0`；必须看**成功那份**日志，且 SOC 行要 `-vv` 才拿得到）见 §4.3。
- **属性在哪个模块，别探错地方**：`HAS_ASCENDC_BATCH_INVARIANT` 定义在 **`vllm_ascend.batch_invariant`**（源码 `vllm_ascend/batch_invariant.py` 顶部），**不在** `batch_invariant_ops` 模块上——对它 `import batch_invariant_ops` 去探只会得到 `?`，会被误判成"BI 没编进去"。反面探针：`dir(torch.ops.batch_invariant_ops)` **数不出算子**（实测只返回 1 个属性），别拿它当判据；要看绑定关系就读 `vllm_ascend/batch_invariant.py` 里把 `aten::mm` / `aten::matmul` 绑到 `torch.ops.batch_invariant_ops.npu_*_batch_invariant` 的那几行（其后是 triton 回退分支）。
- **算子数：模块侧导出 11 个，被 vllm-ascend 注册的只有 4 个（2026-10-10 实测）**。`import batch_invariant_ops` 后 `dir(batch_invariant_ops)` 实测列出 **11** 个（**比源码里被注册的多**）：
  `npu_mm_batch_invariant` / `npu_matmul_batch_invariant` / `npu_reduce_sum_batch_invariant` /
  `npu_fused_infer_attention_score_batch_invariant`（含 `_out` / `_v2`）/ `npu_reduce_mean_batch_invariant` /
  `npu_softmax_batch_invariant` / `npu_log_softmax_batch_invariant` / `npu_add_rms_norm_batch_invariant` /
  `npu_fused_linear_online_max_sum_batch_invariant`；
  而 `vllm_ascend/batch_invariant.py:142-148`（`:96` 是另一处注册点）实际注册的只有 **`mm` / `matmul` / `fused_infer_attention_score` / `reduce_sum` 四个**。
  ⇒ **别拿"导出数 = 生效数"当判据**：多出来的算子只是被绑定出来，未必被 vllm-ascend 接进 `aten::` 分派。判生效读 `batch_invariant.py` 的注册行，不数 `dir()`（注意：`dir(batch_invariant_ops)` 是**模块侧**，与上一行那个"数不出算子的 `dir(torch.ops.batch_invariant_ops)`"不是同一个对象，别混）。

### 4.2 编 `vllm_ascend_C` 的编译器（torch 2.10 头文件要求 GCC ≥ 9）

`.188` 系统只有 gcc 8.3，编 C++ 扩展 `vllm_ascend_C` 会直接死——**`--arctic` 救不了它**（那只管 `arctic-inference`）。实测原文：

```
torch/include/c10/util/C++17.h:14:2: error: #error "You're trying to build PyTorch with a too old version of GCC. We need GCC 9 or later."
make: *** [Makefile:286: vllm_ascend_C] Error 2
subprocess.CalledProcessError: Command '['cmake', '--build', '.', '-j=64', '--target=vllm_ascend_C']' returned non-zero exit status 2
ERROR: Failed building editable for vllm_ascend
```

修法：**借机器上上一版构建时建的专用工具链 conda env，别去装/改系统 gcc**。`.188` 上的实例是 `/home/vllm/x00886548/vllm_build_0921/conda_envs/bi_0921`（`conda-forge gcc 10.4.0`，`bin/` 下有 `x86_64-conda-linux-gnu-gcc` / `g++` / `cc` / `c++` / `gcc-ar` / `gcc-nm` / `gcc-ranlib`）：

```bash
export BI_TC=/home/vllm/x00886548/vllm_build_0921/conda_envs/bi_0921   # ← 换成你的工具链 env（别写 <...> 尖括号，bash 会当重定向）
export CC=$BI_TC/bin/x86_64-conda-linux-gnu-gcc
export CXX=$BI_TC/bin/x86_64-conda-linux-gnu-g++
export C_COMPILER=$CC CXX_COMPILER=$CXX    # vllm-ascend 自己的 envs.py 会转成 -DCMAKE_CXX_COMPILER
```

- **实测可用的整条调用**（2026-10-09，`.188`；本机系统 gcc/g++ = **8.3.0**（Debian 10）、conda = **10.4.0**）：`COMPILE_CUSTOM_KERNELS=1 MAX_JOBS=8 CC=$BI_TC/bin/x86_64-conda-linux-gnu-gcc CXX=$BI_TC/bin/x86_64-conda-linux-gnu-g++ C_COMPILER=$BI_TC/bin/x86_64-conda-linux-gnu-gcc CXX_COMPILER=$BI_TC/bin/x86_64-conda-linux-gnu-g++ PIP_CONSTRAINT=$CONSTR pip install -e . --no-build-isolation`
- 只设 `CC`/`CXX`、或只设 `C_COMPILER`/`CXX_COMPILER`，两种都实测能过；**建议两者都设**（`CC`/`CXX` 是 torch `cpp_extension` 与 BI python wheel 源码编译读的）。
- ⚠️ **绝不把该 env 的 `bin` 前置进 `PATH`**：它是带自己 `python`/`pip` 的 conda env，前置后 `pip` 会解析到它的 pip，**把 vllm-ascend 装进错误的 conda env**（静默、后果严重）。只用 `CC`/`CXX` 的绝对路径指编译器。
- 换过 torch 或改过 pin 后**必须 `rm -rf csrc/build build`**（§4 已含），否则 cmake 沿用缓存里的旧编译器。
- **取证"这次用了哪个编译器"要看对地方**：`vllm_ascend_C` 的 cmake 跑在 setuptools 临时目录里，且 **pip 成功时不打印构建日志**；`csrc/build/CMakeCache.txt` 里的 `CMAKE_CXX_COMPILER=/usr/bin/c++` 属于 **aclnn/kernels 那套构建，不能用来判断 `vllm_ascend_C`**。可信取证：构建日志里 ninja 实际调用的 `g++` 路径，或新生成 `.so` 的 mtime（`ls -l --time-style=full-iso <env>/lib/python3.*/site-packages/vllm_ascend/*.so`）。

### 4.3 ★ 重发 BI 构建前的硬门控（**能省一次 24 分钟编译**）

AscendC 自定义算子的编译是**整条链路的最后一步**才失败（§4.1 / 坑 5 / 坑 15 那类 python 与依赖问题会一路拖到 cmake 的 `ops prepare build failed`）⇒ **在重新发起 `COMPILE_CUSTOM_KERNELS=1 VLLM_BATCH_INVARIANT=1` 之前，先跑这一条，`rc` 必须为 0**：

```bash
$ENVP/bin/python -c "import regex, torch, torch_npu, vllm"; echo "rc=$?"
```

- **为什么这四项必须都点名**：`regex` 是 `csrc/cmake/scripts/util/ascendc_impl_build.py:21` 的模块级 import（坑 6 的"cmake 选错 python"与坑 15 的"依赖没装齐"都以它现形）；`torch` / `torch_npu` 认的是编译期那一套；`vllm` 不在时报得更晚（`ops prepare build failed`）。**rc=0 才发编译；rc≠0 一律先修依赖**，否则整轮白跑（一次约 24 分钟）。
- **取证要 `-vv`，`-v` 不够**：`[build_aclnn] resolved SOC_ARG=…` 这类行受 pip 的 verbose 级别控制，`used_level = VERBOSE(15)`（依据 `pip/_internal/utils/subprocess.py`）⇒ `-v` 打不出这类行，**要用 `-vv`**。
- **失败尝试与成功那次写在不同的日志里**：判「BI 到底装上了没有」必须看**成功那一份**日志——本轮两份日志并存，只看失败那份会得出"没装上"的错结论。
- **BI 成功的判据（三条都来自同一份成功日志）**：run 包与 whl 包**各自的** `[install_batch_invariant] ... installed successfully` + `SOC_ARG=ascend910_93` + `ascend_install_rc=0`。这三条都是**多词模式**，`grep` 时必须把模式写进 `.sh` 再推远端——为省引号裸写会**静默降级**（见 `ascend-env` §5）。

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
python3 -m pip check        # 仅供了解；**不是验收判据**（可用环境固有 2 条违规，见坑 1b）
```

- **ascend backend 一定要从 `triton.__file__` 出发**：本流程用 `pip install -e .`（editable），`vllm_ascend.__file__` 指向**源码树**（`<src>/vllm-ascend/vllm_ascend/__init__.py`），所以 `dirname(vllm_ascend.__file__)+'/../triton/backends/ascend'` 恒为 `False`（2026-09-22 在 `.190` 实测：错误写法 False、正确写法 True）。
- **不要读 `vllm_ascend.__version__`**：`.188` 实测该属性不存在（`AttributeError`），取版本号用 `importlib.metadata.version('vllm-ascend')`。

端到端 NPU 冒烟与 `vllm serve` 起服务见 skill `ascend-vllm-serve`。

### 5.1 版本分支判据是**版本线**不是等值；`VLLM_VERSION` 在 vllm `v0.23.0` 上**已不生效**（2026-10-08 修正）

> **本节原断言「按 release tag 装完必须 `export VLLM_VERSION=<tag版本>`，否则 `vllm_version_is("<tag>")` 为 `False`」已被本轮实测证伪**，不要再无条件照抄；真正改 vllm 自报版本串的开关是 `VLLM_VERSION_OVERRIDE`。

- **`VLLM_VERSION` 在 vllm `v0.23.0` 上不再被 setup.py 读取**：`grep -n VLLM_VERSION setup.py` 逐字只有两行 ——
  ```
  946:    if env_version := os.getenv("VLLM_VERSION_OVERRIDE"):
  947:        print(f"Overriding VLLM version with {env_version} from VLLM_VERSION_OVERRIDE")
  ```
  ⇒ 要覆盖版本串就用 **`VLLM_VERSION_OVERRIDE`**；`export VLLM_VERSION=…` 只会换来运行时那一行噪声 `WARNING [envs.py:2088] Unknown vLLM environment variable detected: VLLM_VERSION`（无害，别为消它改代码）。
- **`vllm_version_is(...)` 是版本线/区间判定**，这正是不必为它导任何变量的原因。装成 `vllm.__version__ = '0.23.1.dev0+g0fc695fc6.d20261008'` 时实测三向：
  ```bash
  python -c 'from vllm_ascend.utils import vllm_version_is as v
  print(v("0.23.0"), v("0.23.1"), v("0.23.1.dev0+g0fc695fc6.d20261008"))'
  # 逐字输出 True False False  —— 判的是"当前 vllm 是否落在 v0.23.x 这条线上"
  ```
  ⇒ **不需要**为了让它为 `True` 而导出 `VLLM_VERSION`；它判 `False` 才说明配错了版本（如坑 10 照抄 `vllm-main-verified.commit`）。判据仍然只有这一条命令，但期望值按版本线读。
- 只有**在别的 vllm 版本上现场核实过**该版本的开关名与 `vllm_version_is` 语义，才照那个版本的实际行为处理。

### 5.2 AscendC 算子编出来没有 / 是哪套 CANN 编的（**别看 `$ASCEND_OPP_PATH/vendors/`**）

`COMPILE_CUSTOM_KERNELS=1` 的产物落在**包内**，不在 CANN 的 opp/vendors 下：

- 落点：`<site-packages 或源码树>/vllm_ascend/_cann_ops_custom/vendors/custom_transformer/`，含 `bin/`、`op_api/lib/libcust_opapi.so`、`op_impl/{ai_core,cpu}`、`op_proto/`、`scripts/`、`version.info`。实测 **1013 个文件 / 87M / 208 个 `binary` 目录**（**`binary` 目录数不是判据**：2026-10-09 另一次实测是 **1162 文件 / ~51 MB / `binary` 目录 = 0**，布局随构建方式不同 ⇒ 只判「`.run` 产物存在 + 文件数量级」，见 §4）；而 `$ASCEND_OPP_PATH/vendors/` 下**只有** `batch_invariant`。
- → 「opp/vendors 里没有 vllm_ascend 就以为算子没编」是**假阴性**，别据此重编。
- 判「这批算子按哪个 CANN 编的」：
  ```bash
  cat <pkg>/vllm_ascend/_cann_ops_custom/vendors/custom_transformer/version.info   # 实测 custom_opp_compiler_version=9.1.0
  cat <pkg>/vllm_ascend/_build_info.py                                            # 实测 __device_type__ = 'A3'
  ```
- 判「扩展运行时真加载了哪套 CANN 库」：import `vllm_ascend.vllm_ascend_C` 后正则扫 `/proc/self/maps` 里的 `cann*` 路径 → 实测**全部命中 `cann_9_1_0`**。
- `vllm_ascend_C` 的 `dir()` 公开符号**只有** `['init_module','python_create_and_map','python_unmap_and_release']` 三个 —— **别拿公开符号个数判断编译是否失败**。

### 5.3 平台层失败的第一诊断点：`VLLM_TARGET_DEVICE=cpu`（2026-10-09 从源码读到）

§5 里那条 `current_platform` 检查退化成 `UnspecifiedPlatform` 时，**第一步先看这个变量**：

```bash
echo $VLLM_TARGET_DEVICE        # 期望为空；为 cpu 就是病根
unset VLLM_TARGET_DEVICE        # 若为 cpu，在本 shell 清掉后重跑 §5 的 current_platform 检查
```

- **机理（逐字）**：`vllm/vllm/platforms/__init__.py:237` 是 `if envs.VLLM_TARGET_DEVICE == "cpu": return cpu_platform_plugin()` —— 这一句**在咨询任何平台插件之前就 return** ⇒ 只要该变量是 `cpu`，**所有插件都被绕过**，平台层必然退化成 `UnspecifiedPlatform`。更难看的是插件抛错被 `except Exception:` **吞掉、只记在 `debug` 级** ⇒ 正常日志里一点线索都没有。
- **纪律：一键激活脚本（§7.1）里绝对不要 `export VLLM_TARGET_DEVICE`**。它是**运行时**读取的（`vllm/vllm/envs.py:89` 定义、`:604` 读 `os.getenv`）；§2 里构建期那个 `VLLM_TARGET_DEVICE=empty`（让 `ext_modules=[]`）与运行时**无关**，别把两者混起来用。

### 5.4 拿已知 good 的参考环境当 oracle（**只读**：绝不写入、绝不 kill 它的进程）

参考环境 `REF=/mnt/share/vllm/conda_envs/xmz_0921`（2026-10-09 实测）。**上面还跑着别的团队的 Kimi-K3 作业**，只读。

- **佐证 commit 选择**：`ls -d $REF/lib/python3.*/site-packages/vllm-*.dist-info` → 实测 `vllm-0.1.dev1+gced6857af.d20260928.empty.dist-info` ⇒ 同一个 vllm commit `ced6857af`，是对我们配对 commit 的**独立佐证**。
- **只能当"打包形态"oracle，不能照抄它的 commit**：它的 `vllm_ascend-0.19.1rc2.dev2454+g9df651d0b.d20260928.dist-info` 是**从本地 clone `9df651d0` 构建的、不是 upstream main**。
- **判自己的 entry_points 正常吗**：`grep -A2 'vllm.platform_plugins' $REF/lib/python3.*/site-packages/vllm_ascend-*.dist-info/entry_points.txt` → 实测 `ascend = vllm_ascend:register`，与本仓 `setup.py:507` **逐字相同**。
- **判 `pip check` 的抱怨是不是噪声**：两边都有**逐字同一句** `opencv-python-headless 5.0.0.93 has requirement numpy>=2, but you have numpy 1.26.4` ⇒ 参考环境也有 = **既定噪声**（实测 `import cv2` 正常、版本 `5.0.0`）⇒ **不要动 opencv / numpy**，并再次确认 `pip check` **不是验收判据**（§6 坑 1b）。

### 5.5 算子级批次不变性验收（"BI 装上了" ≠ "结果真的不随批构成变"；**本节是 BI 的验收配方**）

§4.1 / §4.3 只证「BI 装进去了」。要证「同一个逻辑行在不同批构成下**逐位相同**」，跑这一层：

- **自发现算子名，不编造**：算子名从 `dir(batch_invariant_ops)` 现取，拿不到就判 **SKIP**；**不要手写一个猜来的算子名当用例**。
- **判据是 `torch.equal` 逐位相同，绝不用 `allclose`**：`allclose` 有容差，恰好会放过"差一点"的批次相关误差。
- **必须先断言张量真在 NPU 上**：不在就判 **`SKIP(not-on-npu)`**，不要判 PASS——CPU 上跑出的"全 PASS"什么也证明不了。
- **★ 唯一根因（旧写法全错在这条）：参考必须是"同一个逻辑行"**。旧写法把 `A[0]` 的输出当成第 r 行的参考 ⇒ 比的是**两个不同输入** ⇒ 全元素失配（实测 `max_abs_diff` **60~87**），并呈现**极具误导性**的形态：「**第 0 行恒 PASS、其它行恒 FAIL**」。正解是目标行单独成批算参考，**再把它置于批首**：
  ```python
  target = a_dev[r:r+1]                                        # 同一个逻辑行，单独一批 = 参考
  rows = torch.cat([target, a_dev[0:r], a_dev[r+1:]], dim=0)   # 目标行置于批首
  assert torch.equal(rows[0:1], target)                        # ★ 位级自检：先证明切片没写坏
  ```
  **位级自检 `torch.equal(rows[0:1], target)` 不能省**：它把"切片写坏"与"算子真的批次不变"分开；没有它，后面的 FAIL 无法归因。
- **空张量比对必须判 FAIL**：`shape=(0,1)` 时两边"相等"会给出**假 PASS**（真原因通常是切片写坏）⇒ 检测到 `numel()==0` 直接判 **FAIL** 并标 `EMPTY`。
- **负控（没有它整个测试等于空转）**：拿一个**故意做成批次非不变**的 CPU stub 跑同一套断言，必须报出 **FAIL**；**只报全 PASS 的测试不构成证据**。
- **覆盖面，以及不许读作证据的东西**：`npu_fused_infer_attention_score_batch_invariant` **默认 SKIP**——它的张量布局在本地源码里查不到，凭猜调用 = 编造；即使加 `--allow-attn` 也**仍然 SKIP**，并报 **`EZ1008 ... When layout is TND, actualSequenceLengthQ is required`** ⇒ **这条不得读作"注意力算子批次不变"的证据**。

## 6. 高频坑

1. **pin 没注释** → `--no-build-isolation` 下报 build dependencies 不满足，或 pip 把已装 torch 换版本（torch 与 torch_npu 强绑定，换错就 import 崩）。
2. **顺序错**：vllm 侧 `use_existing_torch.py` 要在 `pip install -r requirements/common.txt` 前；vllm-ascend 侧注释要在 `pip install -e .` 前。
3. `import vllm` 报 `No module named 'triton.experimental'`：vllm main 需要、triton-ascend 3.2.2 不带，`vllm_ascend/__init__.py` 会打 stub，**装完 vllm-ascend 即消失**。别单独升级/重装 triton（会覆盖 triton-ascend 的文件）；破坏了就 `pip uninstall -y triton triton-ascend && pip install "triton-ascend==<pin>"`。
4. 上游版本互斥属固有：vllm main 要 `fastapi>=0.133`，vllm-ascend 要 `fastapi<0.124`，实测装成 0.123.10 也能起服务 —— 保留 pip 的解析结果，别手动"修"。`pip check` 里 numpy/opencv、以及 CANN `set_env.sh` 经 PYTHONPATH 注入的包（mindstudio-kpp 等）都忽略。
   > **2026-10-08 起本条降级为"备用"**（见 §0.1）：**冲突不用管**，不要为了消冲突去动 numpy。只有当后面真出现 `import triton` 崩、或 triton 侧报 numpy 相关错误时，才执行下面这一条回退一次，然后继续往下走，不要反复试版本。
   **但 numpy 这条"互斥"不是噪声，它会被静默升级**（2026-09-28 在 `.188` 实测）：vllm 侧 `pip install -r requirements/common.txt` 会把已装的 `numpy 1.26.4` 升到 `numpy 2.3.5`，而 `triton-ascend 3.2.2` 硬 pin `numpy==1.26.4`。看元数据：`vllm -> ['numpy']`（无约束）、`triton-ascend -> ['numpy==1.26.4', 'numpy; extra == "tests"']` → **1.26.4 是唯一同时满足两侧的值**。真需要回退时（降级后三层自检与 BI 判据全过）：
   ```bash
   pip install --no-deps numpy==1.26.4
   ```
   `--no-deps` 不能省，否则 pip 会重算依赖图、顺手把别的包又换掉。
   > **2026-10-08 补充（新失败模式：不是"静默升级"，而是直接解析失败）**：vllm `v0.23.0` 的 `requirements/common.txt:36` 是 `opencv-python-headless >= 4.13.0`，而 `opencv-python-headless 5.0.0.93` 的 METADATA 声明 `numpy>=2; python_version >= "3.9"`；`triton-ascend==3.2.2` 的 METADATA 又声明 `numpy==1.26.4` ⇒ **同一次 pip 解析必然无解**，逐字两行：
   > ```
   > ERROR: Cannot install -r requirements/common.txt (line 36) and numpy because these package versions have conflicting dependencies.
   > ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
   > ```
   > **修法（本轮实测通过）——把 numpy 从这次解析里摘出去，装完再放回**：
   > 1. 准备两份约束文件：`constraints_nonumpy.txt`（**不含** numpy）与 `constraints.txt`（含 `numpy==1.26.4`）。
   > 2. `pip install -r requirements/common.txt --only-binary=llguidance` —— 用**不含 numpy** 的那份约束（`--only-binary=llguidance` 见坑 15）。
   > 3. 紧接 `pip install --no-deps --no-index --find-links $WH numpy==1.26.4` 把 pin 放回去。
   > 4. vllm 的 `pip install -e . --no-build-isolation` **必须再加 `--no-deps`**：否则它重新解析 `install_requires`，会把 opencv 拉回依赖图、再次 `ResolutionImpossible`。
   > 5. 之后的步骤换回含 numpy 的那份约束。
   > 佐证：本机两个**已跑通**的环境里 `numpy 1.26.4` 与 `opencv-python-headless 5.0.0.93` 共存，`import cv2` 得 `cv2 5.0.0`、`numpy.__version__` 为 `1.26.4`。
1b. **`pip check` 不是验收判据，可用环境固有 2 条违规**（2026-10-08 实测，**明知故犯**）：
   - `opencv-python-headless 5.0.0.93 has requirement numpy>=2; python_version >= "3.9", but you have numpy 1.26.4.`（上面坑 4 的必然结果）
   - `prometheus-fastapi-instrumentator 8.1.0 has requirement starlette<2.0.0,>=1.0.0, but you have starlette 0.50.0.`
   ⇒ 判环境成功用**三层 import/NPU 检查 + 离线冒烟**（§5 + `ascend-env` §4），**不要**拿 `pip check` 干净与否下结论。
5. 缺 build 依赖：`arctic-inference==0.1.1` 在 `--no-build-isolation` 下需要 nanobind/cmake/ninja，先带隔离预装它（及 fastokens / memfabric_hybrid / memcache_hybrid），或先 `pip install "cmake>=3.26" ninja`。**仅限 gcc≥9 的机器（如 `.190`）**；`.188` 的 gcc 8.3 编不了它，见坑 8。
   > **2026-10-10 实测：`nanobind` 缺失时逐字报的是 `CMake Error at CMakeLists.txt:36 (find_package)`**（缺的正是 `nanobind` 的 CMake 配置包）→ 逐字补 **`pip install nanobind`** 即过。**别把它判成"C++20 不支持、得上 `--arctic`"**——本轮实测 `arctic-inference` 的拦路虎是 **`nanobind`，不是 C++20**，补上 nanobind 后**不需要 `--arctic`**（`--arctic` 只在系统 gcc 8.3 那条路上才需要，见坑 8 与 §3；两条不是一回事，别混）。
6. AscendC 构建报 `No module named 'regex'` 或 CMake 找到 base conda 的 python：`export CONDA_PREFIX=<目标 env>`（或 `Python3_ROOT_DIR=<目标 env>`）后再装。**只做这一项还不够**——要按 §7.1 把共享 base 剔出 `PATH`、并显式 `rm -rf csrc/build`。
   > **2026-10-08 修正：原注「该现象是 `.190` 历史记录，2026-09-23 在 `.188` 实测未复现」是错的**（当时只是 shell 恰好不在 conda base）。真触发条件是**登录 shell 落在 conda base**，不是机器型号：`.188` 的共享 miniconda3 一进来就在 base（`CONDA_PREFIX=/mnt/share/x00886548/miniconda3`，python 3.14.7，**没有 `regex`**），而 CMake 的 `Modules/FindPython/Support.cmake` 会把 **`ENV CONDA_PREFIX`** 当 virtualenv 优先搜（原文 `PATHS ENV VIRTUAL_ENV ENV CONDA_PREFIX`），`find_package(Python3)` 又默认按 **VERSION 策略取最高版本** → **即使把 base 从 `PATH` 里剔干净，cmake 仍会选中 base 的 python3.14**，`csrc/cmake/scripts/util/ascendc_impl_build.py:21` 的 `import regex as re` 直接 `ModuleNotFoundError`。
   > 另：`csrc/build_aclnn.sh` 只删 `csrc/output` 与 `csrc/build_out`、**保留 `csrc/build`**（自己会打 `preserving csrc/build and cleaning output dirs`），而 `HI_PYTHON` 是 `CACHE STRING` → 选错的解释器会**跨轮存活**。所以清缓存要写 `rm -rf csrc/build csrc/output csrc/build_out build`（带了 aclnn 那套时 `csrc/build` 也要删），别只删 `build`。
7. 磁盘：算子编译产物与 pip 缓存很大，`TMPDIR` / `PIP_CACHE_DIR` 指到大盘，别把 `/` 写满。
8. **（`.188` 专属）gcc 8.3 的两个连带问题**：
   - `arctic-inference` 用**系统 gcc 8.3** 编不了 → §3 必须加 `--arctic`（与坑 5 的预装法相反，别搞混）；`CC`/`CXX` 指向 conda gcc 10.4.0 时它编得过、`--arctic` **不需要**（2026-10-09 实测，见 §3）。
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
   > **`PIP_CONSTRAINT` 里 torch 那几行要按 METADATA 的写法写**（2026-10-08 实测）：`torch-npu 2.10.0.post4` 的 METADATA 里写的是 **`torch==2.10.0+cpu`**（**带 `+cpu` 后缀**）。写成 `torch==2.10.0` 与它不等值，约束会和依赖声明对不上——照 METADATA 逐字写。

10. **按 release tag 装却照抄了 tag 里的 `.github/vllm-main-verified.commit`** → 装错 vllm 版本。该文件记的是 `vLLM main` 的 CI 验证 commit（`v0.23.0` 上是 `ee0da84…`），tag 配对目标是 vllm 的**同名 tag**（见 §1.1）。**这条不会自曝**：import 得动、编得过，只是 `vllm_version_is("<你的tag>")` 读出 `False`、版本分支走错边。修法：回 §1.1 取同名 tag 重装（`VLLM_VERSION` 不是修法，见 §5.1 修正）。
11. **拿 `VLLM_VERSION` 当版本分支的开关**（2026-10-08 修正，原写"不设输出 False、设了输出 True"**已证伪**）→ 判据仍只有这一条命令：`python -c 'from vllm_ascend.utils import vllm_version_is; print(vllm_version_is("<tag版本>"))'`，但它判的是**版本线**；vllm `v0.23.0` 上 `VLLM_VERSION` 已不被读取（真开关 `VLLM_VERSION_OVERRIDE`），且不导任何变量时 `vllm_version_is("0.23.0")` 本来就 `True`。完整三向实测见 §5.1。
12. **找不到 AscendC 算子产物就以为没编** → 落点在**包内** `vllm_ascend/_cann_ops_custom/vendors/custom_transformer/`，**不在** `$ASCEND_OPP_PATH/vendors/`（那里只有 `batch_invariant`）——这是假阴性，见 §5.2。同理别用 `dir(vllm_ascend_C)` 的符号个数（只有 3 个）判编译成败；也别用 `csrc/build/CMakeCache.txt` 的编译器判 `vllm_ascend_C`（§4.2）。
13. **env 交付脚本（一键激活）缺项** → 5 项缺一即坏，且都以"别处的报错"形式炸出来，见 §7.1。
14. **系统 `cmake` 太旧，AscendC 直接编不了**（`.188` 系统只有 **3.13.4**）。逐字原文：`CMake Error at CMakeLists.txt:11 (cmake_minimum_required): CMake 3.16 or higher is required. You are running version 3.13.4`。修法：**前置目标 env 的 `bin`**——conda 装的 `cmake 4.4.4` + `ninja` 就在那里，且该 `bin` 里**没有编译器**，不会 shadow 系统 `gcc`/`ld`：
    ```bash
    export PATH=$ENVP/bin:$PATH
    cmake --version        # 必须 ≥3.16
    ```
    > 这与 §4.2「**绝不**把工具链 env 的 `bin` 前置进 `PATH`」**不冲突**：那里说的 `bi_0921` 是带自己 `pip` 的**编译器 env**，这里前置的是**目标 python env**，两者是不同目录、不同用途。
15. **`llguidance` 会挂成"零进展"，修法是 pip 命令加 `--only-binary=llguidance`**（2026-10-08 在 `.188` 实测）：
    - 现象：`pip install` 长时间停在 `Preparing metadata (pyproject.toml)`，十几分钟不动。
    - **根因（原解释正确，别改）**：PyPI 上 `llguidance 1.7.6` 的 x86_64 wheel 就是 **`llguidance-1.7.6-cp39-abi3-manylinux_2_31_x86_64.whl`**（同批还有 `manylinux_2_31_aarch64` / `manylinux_2_34_i686` / `manylinux_2_39_riscv64`，以及一批 **cp314 自由线程**版——cp312 用不上）⇒ 它要求 **glibc ≥2.31**。而 `.188` 实测 `ldd --version` = `ldd (Debian GLIBC 2.28-10+deb10u4) 2.28`，且 `pip debug --verbose` 显示本机首选标签上限是 **`cp312-cp312-manylinux_2_28_x86_64`（最高 manylinux_2_28）** ⇒ **manylinux_2_31 的 wheel 被平台标签拒绝**。所以**本机确实没有任何可用 wheel**，pip 只能回退 **sdist 源码编译**。1.7.x 每个版本都是 **15 个 wheel**（1.6.1 / 1.7.0 / 1.7.2 / 1.7.3 / 1.7.5 / 1.7.6 逐个确认）。
    - **⚠️ 方法论教训（比结论本身更值钱）：判"某包有没有 wheel"必须直接读索引/PyPI 的文件名，不能只用 `--only-binary=:all:` 的成败。** 它报 `No matching distribution` **无法区分「根本没有 wheel」与「有 wheel 但本机 glibc / 平台标签不兼容」**——本轮就曾据此误判成"索引上只有 sdist"（**错的**，实际是**有 wheel 但 manylinux_2_31 装不上**）。正确做法：`curl -s https://pypi.org/pypi/<pkg>/<ver>/json` 读 `urls[].filename`。
    - 后果链：源码构建需要 Rust ⇒ 该 sdist 的 PEP-517 助手 **`puccinialin`** 去 `static.rust-lang.org`（Fastly）下 **`rustup-init`**，实测 ~11 kB/s ⇒ 卡数小时。
    - **修法（实测，秒级通过）**：
      ```bash
      pip install -r requirements/common.txt --only-binary=llguidance
      ```
      **正确机理**：该包在本机没有任何可用 wheel ⇒ **pip 的索引候选集为空** ⇒ 转而采用**已安装的 1.7.6**（它满足 `>=1.7.0,<1.8.0`）。实测把 30 分钟挂死变成秒级通过。
      > **⚠️ 2026-10-10 修正：这条修法只在 `llguidance` 已经装好时成立，不许当通用修法用。** 它**没装**时，`--only-binary=llguidance` 反而把候选集**掏空**（本机该包没有任何可用 wheel）⇒ 报 `ERROR: Could not find a version that satisfies the requirement llguidance<1.8.0,>=1.7.0` / `No matching distribution found for llguidance<1.8.0,>=1.7.0`。**正确判据：先 `pip show llguidance` 看它在不在**——在 → 加该开关（利用已装版本）；**不在 → 走下面的离线补轮子**。
      > **`llguidance` 缺失的正确修法 = 离线补自建轮子**（2026-10-10 实测通过）：直接把本机自建并缓存的 **`llguidance-1.7.6-cp39-abi3-linux_x86_64.whl`** 装上。**注意文件名是 `linux_x86_64`、没有 manylinux 标签**——这正是"本机自建"的标志（PyPI 上只有 `manylinux_2_31`，本机 glibc 2.28 装不了，机理见上）：
      > ```bash
      > pip install --no-index --find-links <wheelhouse> llguidance==1.7.6
      > ```
      > **⚠️ 症状会伪装成 CANN / SOC / 批不变性问题（本轮最大的误判陷阱）**：`llguidance` 缺失会让 `pip install -r requirements/common.txt` **整条 abort**，可真正爆出来的却是 C++ 侧这两行：
      > ```
      > ModuleNotFoundError: No module named 'regex'
      > CMake Error at cmake/config.cmake:268 (message): Error: ops prepare build failed.
      > ```
      > ⇒ 看着像 CANN 版本 / `SOC_VERSION` / 批不变性脚本的问题，**真因只是 python 依赖没装齐**。而且这个 `No module named 'regex'` **有两个真因、必须先分开**：① cmake 的 `FindPython` 选中了共享 base conda 的 python3.14（坑 6）；② python 依赖没装齐（本条）。**判据是先跑 §4.3 的硬门控**，import 过不了就先修依赖，别去动 CANN。
    - **重要反例**：**仅仅"预先装好 llguidance"不足以绕过** —— 不加该开关时，pip 仍会为索引里的 sdist 候选准备元数据，从而**重新触发 Rust 构建**。
    - **判"是不是卡在这上面"的可复制证据（父 pip 进程 pid）**：`awk '{print $14+$15}' /proc/<pid>/stat` 隔 12s 取两次 **delta=0**；`grep State /proc/<pid>/status` = `S (sleeping)`；`cat /proc/<pid>/stack` = **`pipe_read`**；`ss -tnp | grep pid=<pip>` 出现 **`CLOSE-WAIT …:443`**；`ls -l /proc/<子进程>/cwd` 指向 **`pip-install-*/llguidance_*`**（元凶一眼看出）；进程树里能看到 **`rustup-init -y --no-modify-path --profile minimal --default-host x86_64-unknown-linux-gnu`**。
    - 旁证：本机自建并留下缓存的 wheel 文件名是 `llguidance-1.7.6-cp39-abi3-linux_x86_64.whl`（**`linux_x86_64`、无 manylinux 前缀**）——这正是"本机自建"的标志，也是它能被 pip 接受的原因（`linux_x86_64` 在兼容标签里，优先级低但可用）。
    - （历史记录，仍可能有用）sdist 自带 `rust-toolchain.toml` 要求 `channel = "1.95.0"` + `components = ["clippy","rustfmt"]`；真要走源码构建时，`export PATH=/root/.cargo/bin:$PATH` + `export RUSTUP_TOOLCHAIN=stable-x86_64-unknown-linux-gnu`（完整三元组名，且该 toolchain 已在 `rustup toolchain list` 里）可绕开。**首选仍是 `--only-binary=llguidance`，别把 Rust 装法写进通用流程。**

16. **版本串形态「正常劣化」不要修**（2026-10-09 实测）：
    - `pip install -e .` 会用 setuptools_scm 往**源码树**写 `vllm_ascend/_version.py`（`setup.py:416` 的 `get_version(write_to=…)`）——源码树里多出这个文件属正常，别当脏改动清掉。
    - **`--depth 1` 且 clone 里没有 tag ⇒ 拼不出 `.devNNNN+gSHA` 后缀**：实测得到 `0.29.0rc1`（§8 记的正常形态是 `0.19.1rc2.dev2317+gbf439330c`）⇒ **形态差异、无功能影响**，不要为它重 clone 或补打 tag。
    - `vllm.__version__` 实测 `0.30.1.dev0+gced6857af.d20261009`（合成 tag 不在真实 HEAD 可达路径 + dirty tree 导致 scm 降级）——**不要设 `VLLM_VERSION_OVERRIDE` 去"修"这个串**：它只是显示值，§5.1 的 `vllm_version_is` 判的是**版本线**。

17. **vllm 自己的 `[build-system].requires` 会钉死 torch（2026-10-22 实测，新坑）**：
    - 现象：`pip install -e . --no-build-isolation`（vllm 侧）直接失败在 build 依赖校验，报 `build dependencies ... missing` 一类，与"torch 已装 2.10.0"完全无关。
    - 原因：`a98247ab` 的 `pyproject.toml` `[build-system].requires` 里逐字是 **`"torch == 2.13.0",`**（vllm main 已切 2.13 线），而 vllm-ascend 侧钉的是 2.10.0 —— 两边不同线。`--no-build-isolation` 会逐个校验 `build-system.requires` 是否已满足，pin 不一致就过不去。
    - 修法（本地旁路，不 commit）：`sed -i 's/"torch == 2.13.0",/"torch >= 2.10.0",/' pyproject.toml`，先 `cp -a pyproject.toml pyproject.toml.pinbak` 留底。放宽下界即可让 2.10.0 满足，不必改别的行。
    - **这不是"注释掉就行"**：`build-system.requires` 里必须留一个可满足的 torch 约束，整行删掉会让 setuptools 在用 `--no-build-isolation` 时缺 build 依赖判定；放松下界是最小改动。
    - 与坑 1/§3 的分工：§3 的 `strip_torch_pins.py` 只处理 **vllm-ascend** 仓，**vllm 仓这一行它不碰**，必须手工改。

18. **`setup.py` 顶部 `import torch` ⇒ 任何 `pip install -e .` 都必须在已 source CANN 的 shell 里跑（2026-10-22 实测，花掉约 15 分钟才定位）**：
    - 现象：`pip install -e . --no-build-isolation` 在 **metadata generation** 阶段炸，报
      ```
      File "<string>", line 17, in <module>
      File ".../torch/__init__.py", line 2980, in <module>
          _import_device_backends()
      RuntimeError: Failed to load the backend extension: torch_npu.
      You can disable extension auto-loading with TORCH_DEVICE_BACKEND_AUTOLOAD=0.
      ...
      error: metadata-generation-failed
      ```
    - 原因：torch >= 2.10 在 `import torch` 时会**自动加载已注册的设备后端**，`torch_npu` 被拉起后要 `aclInit`，而该 shell 没有 `ASCEND_HOME_PATH` / `LD_LIBRARY_PATH` ⇒ 加载失败。**这与 vllm / vllm-ascend 的代码无关，纯粹是 shell 环境没激活。**
    - 修法：`source <本环境激活脚本>` 之后再 `pip install -e .`。注意报错会被 pip 包成 `metadata-generation-failed`，**看起来像打包配置错误，实际是环境没 source**——别去改 `setup.py`/`pyproject.toml`。
    - 反例（不要用）：`TORCH_DEVICE_BACKEND_AUTOLOAD=0` 能绕过加载，但那样装出来的环境仍缺 CANN，验收一定失败；`VLLM_TARGET_DEVICE=empty` 只关 C++ 扩展，**不解决**这个问题。

## 7. 在 Windows 上驱动远端（与 `ascend-env` §5 同套规则）
- 内联 ssh 命令里禁用 `<`、`"`、`$()`；**脚本内禁用 heredoc**（经 ssh stdin 传入会永久挂起）。
- 模式：本地写 .sh/.py → **base64 通道**推到远端 → `ssh -n <host> "bash /remote/x.sh"`（`-n` 只用于执行**远端已存在的文件**）；长任务 `setsid nohup bash x.sh > x.log 2>&1 < /dev/null &` 后轮询日志。
  > **2026-10-08 改**：**不要再用 `(Get-Content -Raw …) | ssh … "tr -d '\r' [| tail -c +4] > /remote/x.sh"` 直推脚本正文**——实测本机管道**不注入 BOM**（`$OutputEncoding.GetPreamble().Length` = 0），`tail -c +4` 会吃掉脚本前 3 字符；而且**多行含中文脚本直推会静默损坏**（丢行 + 中文变私用区字符）。改用 base64，完整写法与判据见 `ascend-env` §5。
- **`ssh -n` 与"脚本走 stdin"互斥**：要把本地脚本管道过去（`$body | ssh <host> "… bash -s"`）**绝不能加 `-n`**——stdin 被 `/dev/null` 占掉后脚本空跑且**不报错**，只看到输出为空。
- 读远端中文文件/脚本一律显式 UTF-8（`[System.IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)` 或 `Get-Content -Encoding UTF8`）；PowerShell 5.1 默认按 GBK 解码，会把 UTF-8 中文读成乱码。
- **主机一律直连 IP**：`root@192.168.13.188`（默认可用）/ `root@192.168.13.190`（备用，**2026-10-22 整机不可达**）/ `root@177.8.21.1`（A5，**需连 A5 VPN 后可达**，见 `univpn-vpn`）。文档代称 `a3` / `a3b` / `a5` 只是叫法，**本机 `~/.ssh/config` 里没有这几个别名**（2026-10-08 与 2026-10-22 两次复核，见 `ascend-env` §1）。`.188` 的 `/root/.bashrc` 第 36 行 `. /usr/local/Ascend/ascend-toolkit/set_env.sh` 指向的是**真实断链**（`/usr/local/Ascend/ascend-toolkit` 现在是**空目录**，既无 `set_env.sh` 也无 `latest` 软链，2026-10-22 复核），所以每条 ssh 都会在 stderr 打一行 `No such file or directory`。**只要显式 source 生产 CANN（`/mnt/share/x00886548/cann/cann_9_1_0/...`）就不受影响**；别依赖 `/usr/local/Ascend/ascend-toolkit`。详见 `ascend-cann-env`。
- `scripts/strip_torch_pins.py` 就是为这种非交互场景准备的（单文件、参数简单，替代 vim）；推送示例（base64，实测逐字无损）：

  ```powershell
  $f = "<本 skill 目录>\scripts\strip_torch_pins.py"
  # 该文件含中文 docstring：必须读**原始字节**；Get-Content -Raw 会按 GBK 解码把文件改坏（见下）
  $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($f))
  ssh root@192.168.13.188 "printf '%s' '$b64' | base64 -d > /tmp/strip_torch_pins.py"
  ssh -n root@192.168.13.188 "md5sum /tmp/strip_torch_pins.py"   # 必须等于本机 (Get-FileHash -Algorithm MD5 $f).Hash
  ```

  > **2026-10-08 实测：这个示例自己就是坑**。老写法 `(Get-Content -Raw $f)` 在 PS 5.1 会按 **GBK 解码**再 `UTF8.GetBytes` 重编码 → 该脚本推过去**字节数从 7343 变成 7819**，远端 `python` 报 `SyntaxError: invalid non-printable character U+E15E`（`"""pyproject.toml 閲屽舰濡?…` 这类乱码）。改 `ReadAllBytes` 后 md5 与本地逐字一致（`44f8663c108105dfc1854b256f65af5e`）。**判推送成功只看 md5**；别用内联 `python -c` 做语法自检（引号会被 PowerShell 吃掉），把检查命令也写成 .sh 推过去。

### 7.1 远端 env 交付脚本（一键激活）必备 5 项，**缺一即坏**

可参考实例：`/home/vllm/x00886548/cann91_v0230/env_cann910_v0230.sh`（`.188`）。缺任一项都不会在当场报错，而是在构建期以别处的报错形式炸出来：

1. **把共享 conda base 从 `PATH` 里剔掉、并前置目标 env 的 `bin`**：base 是 `/mnt/share/x00886548/miniconda3`（见 `ascend-conda-env`）。不清掉它，cmake 的 FindPython 会抓到 base 的 python3.14，编算子报 `No module named 'regex'`（§6 坑 6）。
2. `export CONDA_PREFIX=<目标 env 绝对路径>` —— 同上的确定答案，别依赖 activate 自己推。
3. `LD_LIBRARY_PATH` 前置**只放 libstdc++ 的** `compat_lib` 目录（Debian 10 缺 `GLIBCXX_3.4.26`，见 §6 坑 8）；**不要**直接把整个 `$CONDA_PREFIX/lib` 加进去（会让 `git` 崩）。
4. 用 `set +u` 包住，**再** `source $CANN/cann/set_env.sh` 与 `$CANN/nnal/atb/set_env.sh`（CANN 脚本在 `set -u` 下会因未定义变量直接退出）。
5. **版本相关变量先核实再写**（§5.1 已修正）：vllm `v0.23.0` 上 `VLLM_VERSION` **已不被读取**（真开关 `VLLM_VERSION_OVERRIDE`），而 `vllm_version_is("<tag>")` 是版本线判定——**不导任何变量时本来就为 `True`**，所以 env 脚本里**不要**再无条件写 `export VLLM_VERSION=<tag版本>`；要写就按现场核实过的开关写。

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
- **2026-10-08 实测（`.188`，只读）**：`git ls-remote` → vllm-ascend `refs/heads/main` = **`0bb59db162f6c98b207db14de0cae67246419e66`**（对比 2026-09-28 的 `9df651d…`，**主线已漂移**）；vllm `refs/tags/v0.30.0` = `ced6857afa0ea7b2e3f0846a62e1394e90f15607`；`raw.githubusercontent.com/vllm-project/vllm-ascend/main/.github/vllm-main-verified.commit` 实测仍返回 **`ced6857af…`** → **verified commit 依旧是 vllm `v0.30.0`**。该文件比 main 本身稳定得多——**这正是 §1「免 clone 读 commit、两仓真并行」成立的前提**。现成 checkout `/mnt/share/x00886548/workspace/batch_inv_qwen35/`：vllm HEAD `ced6857`、vllm-ascend HEAD `9df651d0b`，两仓都带本地构建旁路改动（torch 家族 pin 已注释、`csrc/build_batch_invariant_ops.sh` 的 `--max-time` 已改）。

- **2026-10-08 实测：release tag `v0.23.0`（双仓同名）= 端到端可跑通的 tag 组合**：
  - vllm-ascend tag `v0.23.0` = `5cb98ca`（`[v0.23.0][Doc][Misc] Prepare for v0.23.0 official release`）；vllm tag `v0.23.0` = `0fc695f`。该组合端到端离线推理出文本（Qwen2.5-0.5B，`rc=0`）。
  - vllm-ascend `v0.23.0` tag 的 `requirements.txt` 里 pin **是活的（未被注释）**，逐字为：`torch==2.10.0` / `torch-npu==2.10.0.post4` / `torchvision==0.25.0` / `torchaudio==2.10.0` / `triton-ascend==3.2.2` / `transformers==5.5.4` / `fastapi<0.124.0` / `arctic-inference==0.1.1`。（对照：main 上这些行会被本流程注释掉、原 pin 留在注释里，见 §0.1。）
  - tag 里的 `.github/vllm-main-verified.commit` = `ee0da84ab9e04ac7610e28580af62c365e898389`（2026-06-28，`[KV-Offloading] … (cherry picked from 798185d…)`），**与 vllm `v0.23.0` 的 `0fc695f` 不一致** —— 它是 `vLLM main` 取向的 CI 验证 commit，见 §1.1。
  - 同一 release commit 给出的**官方版本矩阵**（release note 与 `docs/source/community/versioning_policy.md` 同步）：

    ```text
    | vLLM Ascend v0.23.0 | vLLM v0.23.0 | Python >=3.10,<3.13 | Stable CANN 9.0.1 | PyTorch/torch_npu 2.10.0 / 2.10.0.post2 | Triton Ascend 3.2.1 |
    ```

    **矩阵与 tag `requirements.txt` 不一致，实装以 `requirements.txt` 为准**：矩阵写 `torch_npu 2.10.0.post2` / `Triton Ascend 3.2.1`，而 `requirements.txt` 是 `2.10.0.post4` / `3.2.2` —— 本环境按 **post4 / 3.2.2** 装并跑通（呼应 §0.1「版本只参考 vllm-ascend 的 `requirements.txt`」）。

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
