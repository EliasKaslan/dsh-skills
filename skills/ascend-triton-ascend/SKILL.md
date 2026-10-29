---
name: ascend-triton-ascend
description: 昇腾 NPU（a3=.188 / a3b=.190）上 triton-ascend 的检测 / 安装 / 验证 / 排障——商发版 3.2.2 必须从 osinfra 专用源装（PyPI 上没有）；官方覆盖式共存，import triton 报 3.2.0 而非 3.2.2 属正常；被 pip install -U triton 覆盖后 `backends/ascend` 目录仍在但 `import triton` 直接崩。适用于"装 triton-ascend / triton 版本不对或被换掉 / import triton 报错 / No matching distribution found for triton-ascend / pip install -U triton 后 NPU kernel 挂了"。不适用：torch 与 torch_npu 本身的问题 → 用 `ascend-torch-npu`；vllm 与 vllm-ascend 装不上 → 用 `vllm-ascend-source-install`。
whenToUse: 要装 / 查 / 修昇腾上的 triton-ascend，怀疑 triton 被别的包换掉，或 import triton 与 backends/ascend 异常时用；torch 栈见 `ascend-torch-npu`。模型看不到本节。
---

# 昇腾 triton-ascend 检测 / 安装 / 验证 / 排障

- **机器**：默认 `root@192.168.13.188`（文档代称 **`a3`**），备用 `root@192.168.13.190`（`a3b`，**2026-10-22 整机不可达**），A5 `root@177.8.21.1`（`a5`，**需连 A5 VPN 后可达**，见 `univpn-vpn`）。**本机 ssh config 没有这几个别名，命令直连 IP**，见 `ascend-env` §1。
- **环境（写死）**：CANN 9.1.0 = `/mnt/share/x00886548/cann/cann_9_1_0`；conda 环境 `xmz_0921`，python = `/mnt/share/vllm/conda_envs/xmz_0921/bin/python`（Python 3.12.14）；site-packages = `/mnt/share/vllm/conda_envs/xmz_0921/lib/python3.12/site-packages`。
- **只碰 triton 栈**：从 Windows 驱动远端的硬规则见 `ascend-env` §5（不重复）；CANN 激活见 `ascend-cann-env`。下文命令均为**远端 bash**（已 `source` CANN `set_env.sh` + `conda activate xmz_0921`）。

## 何时调用

**加载本 skill 当：**

- 要装 / 重装 / 升级 triton-ascend，或问「该装哪个版本」；`import triton` 报错（**哪怕 `triton/backends/ascend` 目录还在**，见坑 3）。
- `pip install triton-ascend` 报 `No matching distribution found for triton-ascend`。
- 有人（或某个包）跑过 `pip install -U triton`，之后 NPU kernel 挂了。

**不要用本 skill（转交）：**
- torch / torch_npu 本身装不上、版本不匹配或 NPU 不可用 → 用 `ascend-torch-npu`。
- 问题在 CANN 检测 / 安装 / 环境变量 → 用 `ascend-cann-env`；`import vllm` 报 `No module named 'triton.experimental'` 是 vllm 侧 stub，不是 triton 坏 → 用 `vllm-ascend-source-install`。
- 装好后起服务 / 跑推理才报错 → 用 `ascend-vllm-serve`。
- 新建 conda 环境 / 激活 / 换 python 版本 → 用 `ascend-conda-env`。

**前置**：CANN 已 `source`，且 torch + torch_npu 已按车道装好（见「前置检查」最后一条）。 ／ **后继**：`vllm-ascend-source-install` → `ascend-vllm-serve`。

## 前置检查（先复制跑这四条）

```bash
python -V                                    # 期望 Python 3.12.14
pip list | grep -i triton                    # 期望同时看到 triton 3.2.0 与 triton-ascend 3.2.2
python -c "import triton, os; print(triton.__version__); print(os.path.isdir(os.path.join(os.path.dirname(triton.__file__),'backends','ascend')))"
# 期望：import 不报错 + 3.2.0 / True —— 硬判据是「import 成功 且 __version__ == 3.2.0」，目录 True 只是辅证（见坑 2 / 坑 3）
pip index versions triton-ascend --index-url https://triton-ascend.osinfra.cn/pypi/simple   # 期望 3.2.2
```
- **`.188` 的 pip 默认源是镜像**（`/root/.config/pip/pip.conf` → aliyun；`/root/.pip/pip.conf` → huaweicloud），所以**版本探测/安装都必须显式 `--index-url`**，否则拿到的可能是镜像缓存（实测 aliyun 与 pypi.org 的列表一致，不是镜像滞后）。
- torch / torch_npu 未就绪先停：本 skill 假设 `torch 2.10.0+cpu` + `torch_npu 2.10.0.post4` 已装（见 `ascend-torch-npu`）。

## 步骤

**⓪ 预下载并入并行 lane**（＝ `ascend-env` §3.1 的 **P3**）——triton-ascend 的两个 wheel（本包 279.9 MB + 社区 `triton==3.2.0` 约 250 MB）是整条流程最大的单项，**务必在并行段先下完**，别让它落在串行路径上：

```bash
WH=/home/vllm/x00886548/envbuild/wheelhouse; mkdir -p "$WH/log"
DL=/mnt/share/vllm/conda_envs/xmz_0921/bin/python     # 与目标 env 同为 py3.12 的任意解释器即可
# constraints.txt 由 `ascend-env` §3.1 落点块统一创建（唯一写者，车道 A/B 各写各的值）。
# 这里**只读不写**：本组若自带 echo 兜底，会与 torch 栈组构成同一文件的双写者，
# 且会把车道 B 的 pin 硬编码进去（车道 A 用它会写出错版本的约束）。
[ -s "$WH/constraints.txt" ] || { echo "缺少 $WH/constraints.txt：先按 ascend-env §3.1 落点块创建" >&2; exit 1; }
$DL -m pip download -d "$WH" -c "$WH/constraints.txt" "triton-ascend==3.2.2" \
  --index-url https://mirrors.aliyun.com/pypi/simple/ \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple \
  > "$WH/log/triton_ascend.log" 2>&1
```

判完成：`ls "$WH" | grep -E '^(triton|triton_ascend)-'` 里 `triton-3.2.0-*.whl` 与 `triton_ascend-3.2.2-*.whl` **都在**（社区 triton 是 triton-ascend 的依赖，会被一起拖下来）。**这一步不碰目标 env**，可与 CANN 三包下载 / conda 建环境 / 两仓 clone 同时跑。

- **这一组归本 skill 管**：`ascend-torch-npu` 步骤 3 只下 torch 三件套 + torch_npu，**不在那边重复下 triton-ascend**（同一个 `$WH`，两个 `pip` 并发写同名 wheel 会白费带宽甚至互相覆盖）。P3 因此是 **1+1 两组**。
- **未验证**：`triton-ascend==3.2.2` 到底依不依赖 torch 未确认。若依赖，本组会在约束下从 whl/cpu 再下一次 `torch-2.12.0+cpu`（192 MB 冗余，可接受，且**绝不会**是 CUDA 版——约束语义已在 `ascend-torch-npu` 步骤 3 实测：`==2.12.0+cpu` 不匹配 `2.12.0`、`==2.12.0` 匹配 `2.12.0+cpu`）；若不依赖，多给的 `-c` 与 extra-index 均无副作用。
- **未验证**：本组与 `ascend-torch-npu` 步骤 3 的 torch 栈组**并发写同一个 `$WH` 与同一个 pip 缓存**。实测只验过单组下载；若日志出现缓存争用告警，给本组单独设 `PIP_CACHE_DIR`，或把它挪到 torch 组的 `wait` 之后串行下（它不是墙钟瓶颈——**最大项 triton-ascend 279.9 MB 才是**）。

**① 安装 triton-ascend（最新商发版 = 3.2.2）**——属串行段 **S2 的第三步**（**必须在 torch 与 torch_npu 之后**）。用 ⓪ 下好的 wheelhouse 离线装：

```bash
WH=/home/vllm/x00886548/envbuild/wheelhouse
pip install --no-index --find-links "$WH" "triton-ascend==3.2.2"
```

wheelhouse 缺包时回退到在线装（**源不能少**，PyPI 上没有这个包）：

```bash
pip install "triton-ascend==3.2.2" --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple
```
> **未验证**：这里的离线装（`--no-index --find-links`）只有 `six` 这类纯 py wheel 的往返实测过（见 `ascend-torch-npu` 步骤 3），triton-ascend 全家未试；报缺包就用上面这条在线装回退，版本别改。
- 官方安装指南原文写法是 `pip install triton-ascend==3.2.1 --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple`（[installation_guide.md](https://github.com/Ascend/triton-ascend/blob/main/docs/zh/installation_guide.md)），把版本换成 `3.2.2` 即可；osinfra 上只有 `3.2.2` / `3.2.1`，**无 pre-release**。
- 验证：`pip list | grep -i triton` → `triton 3.2.0` 与 `triton-ascend 3.2.2` **同时出现**；`ls site-packages | grep -i triton` → `triton-3.2.0.dist-info` 与 `triton_ascend-3.2.2.dist-info` **共存是正常的**（见坑 2，别去"修"）。

**② 验证 import 层：`import triton` 必须成功且 `triton.__version__ == 3.2.0`**——**不能只看 `backends/ascend` 目录**：被 `pip install -U triton` 覆盖后该目录**仍为 `True`（孤儿残留）**，而 `import triton` 已经崩了 → 走坑 3。
```bash
python -c "import triton, os; d=os.path.join(os.path.dirname(triton.__file__),'backends','ascend'); print(d, os.path.isdir(d))"
# 期望：.../site-packages/triton/backends/ascend True（True 只是辅证，必须配合上面 import 成功）
```

> **反面写法（永久假阴性，2026-10-09 实测）**：不要用被 editable 安装的包（如 vllm-ascend 的源码树）的 `__file__` 去拼 `backends/ascend`——那会指向源码树，**恒为 `False`**。判 ascend backend 存不存在**只能从 `triton.__file__` 出发**（上面那条命令就是，实测返回 `True`）。

**③ 端到端验证：真编译一个 `@triton.jit` kernel 并在 NPU 上跑**——`import triton` 成功 **不等于** 可用，必须真编真跑（标准 vector-add，BLOCK=1024, n=1024）。
```bash
python /tmp/triton_ascend_check.py     # 脚本来源：D:\workspace\agent\skill\_recon\triton_ascend_check.py
```
验证（2026-09-23 在 `.188` 实测通过，原文输出）：
```
triton.__version__ = 3.2.0 / triton/backends/ascend exists = True / npu available/count/soc = True 16 253
TRITON_KERNEL_MAX_DIFF = 0.0
TRITON_ASCEND_CHECK_OK
=== EXIT=0 ===
```
- `max diff = 0.0` 是「triton-ascend 真能在 A3 NPU 上算出正确结果」的唯一硬证据。执行中那行 `Warning: The current CANN and HDK(driver) versions require processing for 32 padding size` 是正常告警。
- 本节的 kernel 实测在**两条车道**上各跑过一次并都通过：`xmz_0921`（torch 2.10.0+cpu，见 `_recon/torch_npu_triton_install.md` 第 288–289 行）与 `torch_latest`（torch 2.12.0+cpu，见 `_recon/torch_stack_verified.md` 第 350、551–554 行）。⚠️ **2026-10-22 复核：`torch_latest` 那个环境（`/home/vllm/x00886548/torch_test/envs/torch_latest`）已被删掉**——车道 B 要复跑得按 `ascend-torch-npu` 重建一个 py3.12 环境；车道 A 的 `xmz_0921` 仍在。

## 坑与修法

**坑 1｜`ERROR: No matching distribution found for triton-ascend`**——**triton-ascend 不在 PyPI**（实测默认源跑 `pip index versions triton-ascend` 就是这个报错）。修法：加 `--extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple`，查版本同样要带源。反向坑：`pip index versions torch-npu --index-url https://triton-ascend.osinfra.cn/pypi/simple` 会报 `ERROR: No matching distribution found for torch-npu`——**torch_npu 走 PyPI，两个源别搞反**。

**坑 2｜`import triton` 报 `3.2.0` 而不是 `3.2.2` → 这是正常的，不要"修"**
- 证据：`triton_ascend 3.2.2` 的 METADATA 里写着 `Requires-Dist: triton==3.2.0`；官方指南原文：「triton-ascend 3.2.1 及以上，Triton-Ascend 通过将 Triton 声明为安装依赖来缓解安装覆盖问题。安装 Triton-Ascend 时会**先安装社区 Triton，再由 Triton-Ascend 覆盖同名目录**」，且「**x86 依赖 triton==3.2.0，arm 依赖 triton==3.5.0**」。
- RECORD 级证据（2026-09-23 实测）：`triton-3.2.0.dist-info` RECORD **376 条**、`triton_ascend-3.2.2.dist-info` RECORD **249 条**、**重叠 73 条**；`triton` 的 RECORD 里 `triton/backends/ascend` 占 **0 条**，`triton_ascend` 占 **111 条**，且 triton_ascend **也覆盖 `triton/__init__.py`** —— 盘上真实生效的是覆盖后的 `triton/`。
- 结论：`import triton` 成功 + `triton.__version__ = 3.2.0` + `backends/ascend` 存在 + 两个 dist-info 共存 = **完全正确的状态**。`__version__` 报 3.2.0 **不是装错**，但它**是判据的一半**（另一半是 import 成功）；**目录存在不能单独作判据**（见坑 3）。

**坑 3｜单独 `pip install -U triton` 会把 triton-ascend 覆盖掉（社区 triton 已到 3.8.0；实测装 3.8.0 耗时 342s）**
- **真实症状（2026-09-23 实测——原「`backends/ascend` 变 `False`」的判据不准确）**：升级后 `triton_ascend 3.2.2` 的 dist-info **仍然在**、`triton/backends/ascend/` 目录**也仍然在（孤儿残留）**，pip 层面"看起来没坏"，但 `import triton` 直接崩：`ModuleNotFoundError: No module named 'triton._C.libtriton.ascend'; 'triton._C.libtriton' is not a package`（triton-ascend 的文件不在社区 triton 的 RECORD 里，pip 不删它）。→ 判据必须是 `import triton` 能否成功 + `triton.__version__ == 3.2.0`。
- 恢复（原文命令，实测 **5 秒**恢复；恢复后 `import triton` 正常、`backends/ascend=True`）：
```bash
pip uninstall -y triton triton-ascend && pip install triton-ascend==3.2.2 --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple
```
恢复后重跑 ②③ 验收。**永远不要为了"对齐版本"去单独升降 triton。**

**坑 4｜`pip check` 报 numpy 冲突 → 固有冲突，忽略，别手动"修"**
- 错误原文：`opencv-python-headless 5.0.0.93 has requirement numpy>=2, but you have numpy 1.26.4.`
- 原因：triton-ascend 3.2.2 的 METADATA 把 `numpy==1.26.4` 锁死（还有 `attrs==24.2.0`、`scipy==1.13.1`、`decorator==5.1.1`、`psutil==6.0.0` 等）。**手动把 numpy 升到 2.x 会破坏 triton-ascend**。同理忽略 `mindstudio-kpp` / `ms-service-profiler` / `affinity-sched` / `schedule-search` 缺包——那些是 CANN `set_env.sh` 经 `PYTHONPATH` 注入的包，不属于本环境。

**坑 5｜`import vllm` 报 `No module named 'triton.experimental'` → 别来动 triton**
- 错误原文：`ModuleNotFoundError: No module named 'triton.experimental'`
- 原因：vllm main 需要 `triton.experimental.gluon`，而 triton-ascend 3.2.2 基于社区 triton 3.2.0，3.2.0 wheel 里没有该模块。**这是 vllm 侧的 stub 问题**：`vllm_ascend/__init__.py` 在导入时把 `triton.experimental(.gluon)(.language)` stub 进 `sys.modules`。修法：**装完 vllm-ascend 即自动消失**，什么都别做；此时若去 `pip install -U triton` 会同时踩坑 3。详见 `vllm-ascend-source-install` / `ascend-vllm-serve`。

**坑 6｜Python 版本硬约束：py3.12 必须 ≥ 3.2.1**——官方表原文 `3.2.1 → py3.9 - py3.13`（py3.9 不支持 aarch64）、`3.2.0 → py3.9 - py3.11`。`xmz_0921` 是 **python 3.12.14**，装 `triton-ascend 3.2.0` 不可用 → 必须 `>=3.2.1`（本环境用 3.2.2）。

**坑 7｜triton-ascend 3.2.2 的 CANN 配套关系官方未列**——官方安装指南的 CANN 配套表**只到 `3.2.1 ↔ CANN 9.0.0`**（再往前 `3.2.0 ↔ CANN 8.5.0`、`3.2.0rc4 ↔ CANN 8.3.RC1/RC2`），**没有 3.2.2 那一行**；3.2.2 只出现在 osinfra 索引里。

> **[2026-10-29 复核，下面的"官方未列"已被新文档修正]** 官方版本说明（readthedocs `<版本说明> → 版本推荐配套`）现在给出了完整行，**且正式进了 CANN 9.2.0 一档**：
>
> | Triton-Ascend | PyTorch | TorchNPU 安装包 | CANN | Python |
> |---|---|---|---|---|
> | `3.6.0`（2026-10-15 发布，正式版） | 2.10.0 | `2.10.0.post7` | **9.2.0** | 3.10~3.13 |
> | `3.2.2.post2`（2026-10-15 补丁版） | 2.7.1 | `2.7.1.post11` | **9.2.0** | 3.9(x86)/3.10~3.13 |
> | `3.2.2` | 2.7.1 | `2.7.1.post8` | 9.1.0 | 同上 |
>
> - 表 2（与 CANN 兼容）里 **`3.6.0` 与 `3.2.2.post2` 对 CANN 9.2.0 都是 Y**（A2/A3 与 950 两个芯片列全 Y）。
> - **3.6.0 是本轮唯一 `CANN 9.2.0 + PyTorch 2.10.0 + torch_npu 2.10.0.post7` 的正式配套**；它的 Python 下限已抬到 **3.10**（3.2.x 曾有 py3.9）。
> - 索引侧：`repo.huaweicloud.com/ascend/repos/pypi/triton-ascend/` 与 `triton-ascend.osinfra.cn/pypi/simple` 现均有 `3.6.0` / `3.6.0.post2` / `3.2.2.post2` / `3.2.2` / `3.2.1`，**只有 cp310–cp313**（无 cp39 的 3.6.0、也无 cp314）。
> - **MindSpeed 26.2.0（分支 `26.2.0_core_r0.12.1`）的安装指南第 6 步就 pin `triton-ascend==3.6.0`**；triton-ascend 自己的镜像标签也是 `3.6.0-cann9.2.0-torch_npu2.10.0.post7-{a3,910b}-*`，与本条表格互相印证。
> - 所以"3.2.2 无官方配套"只对 **3.2.2 ↔ CANN 9.1.0** 那一段成立；**要用 CANN 9.2.0 就直接上 3.6.0**（或按 2.7.1 栈选 3.2.2.post2）。
- **未验证：** 3.2.2 ↔ CANN 9.1.0 是否属官方认证配套（`.188` 上「装得上、能 import、kernel max diff 0.0」不等于官方认证配套）。
- **官方未列（不是「未验证」）**：3.2.2 ↔ PyTorch 2.12 —— 官方 triton-ascend 配套表只到 `3.2.1 ↔ CANN 9.0.0`、System Requirements 只到 PyTorch 2.10，**没有 3.2.2 行、也没有 PyTorch 2.12 行**；但**本机已在 torch 2.10 与 torch 2.12 两条车道上实测 kernel 通过**（`MAX_DIFF = 0.0`）。→ 结论：**能用，但不属官方认证组合。**
- **未验证：** triton-ascend 自带 tutorial 全集与性能（③ 只测了单个 vector-add kernel）；全新 venv 里的真实 `pip install` 复现（结论来自版本存在性 + wheel METADATA + `.188` 现装环境实测）。
- **未验证：** triton-ascend **3.2.2 在 gitcode 上没有对应 tag/release**（最新 release 仍是 **3.2.1**），官方安装指南与 CANN 配套表也只写到 `3.2.1 ↔ CANN 9.0.0` → 「装得上 + kernel `MAX_DIFF=0.0`」**≠ 官方认证配套**。

**坑 8｜华为云 `mirrors.huaweicloud.com/ascend/repos/pypi` 是扁平文件目录、不是 PEP503 index**——当 `--index-url` 用会报 `ERROR: No matching distribution found`；要当 index 用请用 `https://mirrors.huaweicloud.com/repository/pypi/simple/`（实测 200，含 2.12.0）。**triton-ascend 一律以 `https://triton-ascend.osinfra.cn/pypi/simple` 为准**（该 URL 对具体包 301 → `https://repo.huaweicloud.com/ascend/repos/pypi/triton-ascend/`；2026-10-29 复核该索引已有 `3.6.0` / `3.6.0.post2` / `3.2.2.post2` / `3.2.2` / `3.2.1`，不再"只有 3.2.2 / 3.2.1"）。

> **2026-10-29 未判定**：MindSpeed 26.2.0 安装指南写的 `--extra-index-url=https://mirrors.huaweicloud.com/ascend/repos/pypi`（即上面那条扁平目录）**从本机 Windows 跑 `pip index versions` 解析不出**；但同批对照 `aliyun + torch-npu` 也一并失败 ⇒ 是该机 pip/网络侧的问题，**不能据此判该源可用或不可用**。在 `.188` 上真要装时优先 osinfra 那条。

**坑 9｜同版本换 base triton wheel 是「静默空操作」，且换不到功能差异（2026-10-09 实测，Python 3.12.15）**
- **症状**：已装 `triton-3.2.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`（env `/home/vllm/x00886548/xmz_1009_k3/envs/xmz_1009_k3`），再 `pip install` 同版本的 `triton-3.2.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` → pip 判 `already installed with the same version`，**没换成、也不报错**（静默空操作，最容易误判成"已换"）；事后 `triton-3.2.0.dist-info/WHEEL` 里的 `Tag:` 仍是 `cp312-cp312-manylinux_2_27_x86_64` + `cp312-cp312-manylinux_2_28_x86_64`。
  → 修法：同版本换 wheel **必须先 `pip uninstall -y triton`**（或 `pip install --force-reinstall <目标 wheel>`），装完**用 `WHEEL` 的 `Tag:` 行复核**，别信 pip 的 `Successfully installed`。
- **为什么换 base wheel 买不到功能**：`triton-ascend` 安装时会**覆盖 `triton/` 的核心**——`triton_ascend-3.2.2.dist-info/RECORD` 里有 **243 条落在 `triton/` 内**，含 `triton/_C/libtriton.so`、`triton/_C/libentryC.so`、`triton/__init__.py` 与 `triton/backends/ascend/**`（其内还自带 `bishengir/bin/bishengir-compile` 与 `-a5` / `-opt` / `-opt-a5`）。实测两个 base wheel 装完后**真正在跑的 `libtriton.so` 逐字节同尺寸 = 140,886,096 B**，只有 profiler 侧不同（`libproton.so`：`2_17` 版 18,195,880 B、`2_27` 版 11,262,096 B）与 `instrumentation/`。
- **结论**：换 base triton wheel **只买到 provenance / 可复现性，买不到功能差异**（功能来自 triton-ascend 的覆盖层）。若确为对账需要而换，按上面 `uninstall` 的做法做，且**两个 wheel 都留着**以便回滚。

## 不要做什么

- 不要单独 `pip install -U triton` / `pip install triton==<高版本>`（社区已到 3.8.0，会覆盖 triton-ascend）；也不要把 `triton.__version__ == 3.2.0` 当成装错而去"对齐"成 3.2.2。
- 不要为了消除 `pip check` 的 numpy 冲突而升 numpy；不要为了 `triton.experimental` 报错而动 triton（那是 vllm 侧 stub，见坑 5）。
- 不要用默认 pip 源做版本探测（`.188` 默认是 aliyun/huaweicloud 镜像），也不要给 `torch-npu` 加 osinfra 源。
- 不要往 `.188` 的 `/`、`/tmp`、`/root` 写大文件（同一块系统盘，多租户共用、长期紧张；**具体余量现场 `df -h` 取**），临时脚本用完即删。

## 验收标准

1. `pip list | grep -i triton` 同时出现 `triton 3.2.0` 与 `triton-ascend 3.2.2`（**两项都要在**）。
2. `python -c "import triton; print(triton.__version__)"` → `3.2.0` 且**不报错**（硬判据）；`os.path.isdir(.../triton/backends/ascend)` → `True`（辅证，**不能单独用**）。
3. 端到端 kernel：`TRITON_KERNEL_MAX_DIFF = 0.0` 且打印 `TRITON_ASCEND_CHECK_OK`（`EXIT=0`）。
4. `pip check` 里**只剩**坑 4 那类固有冲突与 CANN 注入包噪音，没有 triton 相关新报错；交叉引用：torch/torch_npu → `ascend-torch-npu`、CANN → `ascend-cann-env`、vllm 安装 → `vllm-ascend-source-install`、起服务/运行时 → `ascend-vllm-serve`、远端驱动 → `ascend-env` §5。

## 维护记录 → `references/maintenance-log.md`

逐轮改动与哪条旧结论被证伪。**用户不会问这个**，只在怀疑版本说法过时时才读。