---
name: ascend-cann-env
description: 昇腾 CANN 的检测/安装/激活/换版本/卸载（默认 a3=192.168.13.188，备用 a3b=.190）——权威定位看 /etc/Ascend/ascend_cann_install.info，toolkit+ops+nnal 三件套安装序列与耗时，合一包不覆盖驱动，公开源最新非 beta = 9.1.1，beta/T 构建桶内目录名 ≠ 版本号（如 CANN 9.2.T3）。适用于"装/换/查 CANN / import acl 或 atc 报找不到 CANN / source set_env.sh 后 ASCEND_HOME_PATH 为空 / install.info 里还记着旧路径 / 重跑安装脚本报 Permission denied / 该用合一包还是独立 toolkit 包 / 某个 CANN 版本公开源有没有 / OBS 探版本全是 403"。不适用：conda 与 python 版本 → 用 `ascend-conda-env`；目录与磁盘红线 → 用 `ascend-server-layout`。
whenToUse: 要在 .188/.190/A5 上查 CANN 装在哪、什么版本，装或重装、切版本、修 set_env.sh，判该用合一包还是独立 toolkit 包，或确认某版本在公开源有没有时用。模型看不到本节。
---

# 昇腾 CANN 检测 / 安装 / 激活 / 换版本 / 卸载（9.1.0 与 9.2.0-beta.2 真机实测）

环境写死：`a3`=`root@192.168.13.188`（默认，可用）/ `a3b`=`.190`（备用，**2026-10-22 整机不可达**）/ `a5`=`root@177.8.21.1`（**需连 A5 VPN 后可达**，CANN 规格仍未采，见 `univpn-vpn`）——三台准入状态见 `ascend-env` §1；生产 CANN 9.1.0 在 `/mnt/share/x00886548/cann/cann_9_1_0`（`cann-9.1.0/` 9.2G + `nnal/` 1.1G）；driver 25.5.1（`/usr/local/Ascend/driver/version.info` 的 `Version=25.5.1`，`npu-smi` 同版本）；芯片 `Ascend910_9382`。该安装根顶层同时躺着三个 `.run` 与四个展开目录（`Ascend-cann_9.1.0_linux-x86_64.run` / `Ascend-cann-A3-ops_9.1.0_linux-x86_64.run` / `Ascend-cann-nnal_9.1.0_linux-x86_64.run`＋`ascend-toolkit / cann / cann-9.1.0 / nnal`），**现场佐证**下面"toolkit+ops+nnal 三件套"。**2026-10-22 复核**：`/etc/Ascend/ascend_cann_install.info` 仍指 `/home/vllm/x00886548/zero_v0230/cann_9_1_0`（mtime `Oct 9 11:01`），而 `env_batch_inv.sh` 实际 source 的是 `/mnt/share/.../cann_9_1_0` —— **两者不一致是常态，别按 install.info 判"当前在用哪套"**（见坑 1 第 39 行那段的判据）。远端执行硬规则（禁内联引号/heredoc、`ssh -n` 互斥）见 **`ascend-env` §5**，磁盘红线见 `ascend-server-layout`。

## 何时调用

**加载本 skill 当：**
- 要查「CANN 装在哪 / 什么版本 / 机器上有几份」，或 `import acl`、`atc`、算子编译报找不到 CANN。
- 要装 / 重装 / 换路径 / 换版本 / 卸载 CANN（9.1.0 或 9.2.0-beta.2；toolkit、ops、nnal 三件套）。
- 要确认某个 CANN 版本在公开 OBS 上到底有没有（**桶内目录名 ≠ 版本号，但这条只对 beta/T 构建成立**——正式版目录名就是版本号，见坑 11）。
- `source set_env.sh` 之后 `ASCEND_HOME_PATH` 为空，或指向已不存在的目录。

**不要用本 skill（转交）：**
- 问题在 conda 环境或 python 版本 → 用 `ascend-conda-env`。
- 只是不知道该往哪写文件 / 磁盘满了 / 找模型在哪 → 用 `ascend-server-layout`。
- 已装好 CANN，卡在 torch_npu 装不上 → 用 `ascend-torch-npu`。
- triton-ascend 装不上 / 被 pip install -U triton 覆盖 → 用 `ascend-triton-ascend`。
- 起服务 / 离线推理冒烟 / 显存释放与运行时排障 → 用 `ascend-vllm-serve`。
- 从源码装 / 重装 vllm 与 vllm-ascend（按 verified commit 配对） → 用 `vllm-ascend-source-install`。

**前置**：能免密 ssh 进 `root@192.168.13.188`（本机无 `a3` 别名，见 `ascend-env` §1）。 ／ **后继**：`ascend-conda-env` → `ascend-torch-npu`。

## 前置检查

```bash
P=$(awk -F= '/^Install_Path=/{print $2}' /etc/Ascend/ascend_cann_install.info); echo "P=$P"
readlink -f "$P/cann"                                                    # 实体版本目录 <P>/cann-<ver>
ls "$P"/cann-*/x86_64-linux/*install.info               # 有 all_cann=合一包装的；有 toolkit=独立包装的
cat /usr/local/Ascend/driver/version.info | head -2                      # Version=25.5.1
npu-smi info | head -6 ; df -h "$P" ; python3 -V ; ls -d /home/vllm
```

- `P` 是**查「最近一次安装落在哪」的权威入口**（`/etc/Ascend/ascend_cann_install.info` 由 toolkit 安装器写，2 行：`Install_Path` + `Toolkit_InstallPath`）；**但它≠「当前环境正在用哪套 CANN」**（2026-10-09 `.188` 实测）。同一台机**多套 9.1.0 并存**：`find -maxdepth 3 -name 'cann-9.1.0' -type d` 命中 **≥5 处** —— `/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0`、`/home/vllm/x00886548/cann/cann_9_1_0_img/cann-9.1.0`、`/home/vllm/x00886548/cann/cann_9_1_0/cann-9.1.0`、`/home/vllm/x00886548/zero_v0230/cann_9_1_0/cann-9.1.0`、`/home/vllm/x00886548/sv0230/cann/cann-9.1.0`，另有**驱动侧一套 9.0.0**（`/usr/local/Ascend/cann -> /usr/local/Ascend/cann-9.0.0`）；`/etc/Ascend/` 下除当前 info（130 B，mtime `Oct 9 11:01`）还有 **6 个带时间戳的历史快照**（`20250829_153104` / `20260716_140303` / `20260921_150726` / `20261008_160642` / `20261008_194804` / `20261009_105734`），**每个都含自己的 `ascend_cann_install.info`**（与坑 12「注册表在运行时不被查询」一致）。本轮实测该 info 指向 `/home/vllm/x00886548/zero_v0230/cann_9_1_0`，**它不是坏的、也不是过期残留**：其下 `cann-9.1.0/set_env.sh`、`cann-9.1.0/bin/ccec` 都在，`ASCEND_HOME_PATH=[/home/vllm/x00886548/zero_v0230/cann_9_1_0/cann-9.1.0]`，`command -v ccec` 亦落在它 —— **只是一套真实可用、但当前没在用的 CANN**。判「当前在用哪套」只有两个判据：① 激活脚本 source 的**绝对路径** ② `echo $ASCEND_HOME_PATH` 的**实际值**（本仓激活脚本正是自定位写法：`export ASCEND_CANN_ROOT=/mnt/share/x00886548/cann/cann_9_1_0` 然后 source 它，**不读 install.info**，所以它才对）。**`/etc/ascend_install.info` 是 driver 写的，别混**（toolkit 的 `set_env.sh` 靠它的 `Driver_Install_Path_Param` 找 `libascend_hal.so`）。
- 判据：有 `ascend_all_cann_install.info` = 合一包装的（`package_name=Ascend-cann`，`innerversion=V100R001C25B114`）；只有 `ascend_toolkit_install.info` = 独立包（`package_name=Ascend-cann-toolkit`，`innerversion=V100R001C11SPC001B243`）。两者**布局完全一致**。
- **`ccec` / `bishengir-compile` 在哪**（2026-10-09 `.188` 实测）：在 **`$CANN_HOME/bin/`（即 `<CANN>/cann-9.1.0/bin/`）** —— `ccec -> ../../tools/bisheng_compiler/bin/ccec`、`bishengir-compile -> ../../tools/bishengir/bin/bishengir-compile`、`bishengir-opt -> ../../tools/bishengir/bin/bishengir-opt`、`hivmc -> ../../tools/bishengir/bin/hivmc`（另有 `-a5` 变体）；**实体副本**在 `$CANN_HOME/x86_64-linux/bin/{ccec,bishengir-compile}`。**`$CANN/bin/`（`cann_9_1_0/bin/`）不存在，`compiler/ccec_compiler/bin/` 也报 `No such file or directory`** —— 别去这两处找。`$ASCEND_HOME_PATH` 就是 `$CANN_HOME`，故 `command -v ccec` 应落在 `$CANN_HOME/bin/ccec`。
- 驱动基线（装 CANN 前后必须不变）：`e0ae42a0d046fa6a0ec8f26e9693eef8  /etc/ascend_install.info`、`4019d58ec411a20a27e1b3415123a78a  /usr/local/Ascend/driver/version.info`。
- 磁盘：安装器要求 toolkit 安装目录可用空间 **>10GB**（这是官方硬要求，不是本机现状）；`.188` 只有 `/home/vllm`（独立大容量盘）适合写，`/mnt/share`、`/tmp`、`/root` 全与 `/` 同盘（系统盘，长期紧张）。**装之前自己 `df -h` 现场确认余量**，别照抄历史数字。
- Python 官方支持 **3.7.x–3.14.x**；`.188` 的 conda base 3.14.7 与 `/usr/bin/python3`（3.7.3）实测都通过 `import acl`。conda 见 `ascend-conda-env`。

## 步骤

> **下载与安装分属两个阶段**（2026-10-08 起）：下面步骤 2~5 是**安装**，属 4 条并行 lane 之后的串行段 **S1**；三个 `.run` 的**下载**属并行 lane **P1**（见坑 11 的并行写法），应当**最先发出去**，然后去干别的 lane，等 barrier 再回来装。编排见 `ascend-env` §3。

**0. 备份全局登记文件（换路径/重装前必做）**

```bash
BK=/home/vllm/x00886548/cann_test/etc_Ascend_backup; mkdir -p "$BK"
cp -a /etc/Ascend/ascend_cann_install.info "$BK"/ascend_cann_install.info.orig
md5sum "$BK"/ascend_cann_install.info.orig    # **现场取并把结果存档，不要照抄任何硬编码 md5**；收尾时 cp -a 还原并复验同一个值
```

**1. 准备安装根 + 独立 `pkgs/` 目录**

```bash
ROOT=/home/vllm/x00886548/cann_test/cann_9.1.0; PKGS=/home/vllm/x00886548/cann_test/pkgs
mkdir -p "$ROOT" "$PKGS"; cd "$PKGS" && chmod +x ./*.run     # 官方只要 chmod +x，不要 -R 777
ln -f "$PKGS"/*.run "$ROOT"/                                  # 同盘硬链接，零额外占用
ls -d "$ROOT"/./*toolkit* "$ROOT"/./*nnal*                    # 首次应各只命中 1 个 .run
```
- 验证：三个 glob 各展开成**一个词**。**`.run` 必须留在 `pkgs/`，安装根只放解出来的目录**（原因见坑 5）。

**2. 装 toolkit**（合一包 74s / 独立包 68s，实测 rc=0）

```bash
cd "$ROOT"
./Ascend-cann_9.1.0_linux-x86_64.run        --install --install-path=$(pwd) -q   # 合一包（含驱动子包）
# 或： ./Ascend-cann-toolkit_9.1.0_linux-x86_64.run --install --install-path=$(pwd) -q   # 公开源只能拿这支
```
- 落盘：toolkit → `<p>/cann-9.1.0`，并建 `<p>/cann -> <p>/cann-9.1.0` 与 `<p>/ascend-toolkit/{latest,set_env.sh}` 两条兼容软链。
- 验证：Summary 出现 `CANN: Ascend-cann_9.1.0_linux-x86_64 install success, installed in <p>.`；`-q` 原文 `Quiet install, accept EULA by default`（**自动接受 EULA，全程无交互**）。
- 合一包会不会碰驱动：本机 driver 25.5.1 已装时日志为 `skip install Ascend-hdk-driver_26.0.rc1_linux-x86-64.run` + `Check version matched! driver version 25.5.1 satisfies >=25.5.0`，驱动 md5 前后一致。Summary 里的 `Driver: Installed in /usr/local/Ascend/driver.` **只是状态汇报，不是本次装了驱动**。要绝对保险加 `--whitelist=toolkit`（未验证：该参数本次未实测）。

**3. 激活（官方路径 `<p>/cann/set_env.sh`）**

```bash
set +u                                   # 坑 1：与 set -u 冲突
source "$ROOT/cann/set_env.sh"
echo "$ASCEND_HOME_PATH | $ASCEND_OPP_PATH | $ASCEND_TOOLKIT_HOME | $ASCEND_AICPU_PATH"
```
- 验证：`ASCEND_HOME_PATH=$ROOT/cann-9.1.0`、`ASCEND_OPP_PATH=$ROOT/cann-9.1.0/opp`。`<p>/ascend-toolkit/set_env.sh` 是向后兼容软链，实测两路四个变量**完全一致**，但推荐官方那条（少一跳，不易断）。换版本/多版本共存：开**新 shell** 再 source 新版本；同一 shell 里 A→B 会叠加（`set_env.sh` 只清自己 `install_dirpath` 前缀的条目）。

**4. nnal**（12s，rc=0；**必须先 source 同版本 toolkit**）

```bash
cd "$ROOT"; ./Ascend-cann-nnal_9.1.0_linux-x86_64.run --install --install-path=$(pwd) -q
source "$ROOT/nnal/atb/set_env.sh"
```
- `--install-path` 对 nnal 生效：装到 **`<p>/nnal`**，`/usr/local/Ascend/nnal` 零改动（mtime 前后不变）。
- 验证：`ATB_HOME_PATH=$ROOT/nnal/atb/latest/atb/cxx_abi_1` 且该目录存在。`cxx_abi` 由 `set_env.sh` 探测 `torch.compiled_with_cxx11_abi()` 决定，无 torch 时默认 `1`——所以**先 source torch 环境再 source 它**，torch/torch_npu 见 `ascend-torch-npu`（未验证：`cxx_abi_0` 分支本次未实测）。
- **`nnal/asdsip/set_env.sh` 绝对不要 source**：它会把自己插到 `LD_LIBRARY_PATH` 最前，shadow 掉本行 atb 的 `libtbe_adapter.so`、并挤掉 `compat_lib`（静默废掉坑 9 的 `GLIBCXX_3.4.26` 修复）→ 只 source **toolkit + `nnal/atb` 两段**，见坑 15。

**5. ops**（91s，rc=0；必须与 toolkit 同路径）

```bash
cd "$ROOT"; ./Ascend-cann-A3-ops_9.1.0_linux-x86_64.run --install --install-path=$(pwd) -q
```
- 落盘：**`<p>/cann-9.1.0/opp/`**，**不会**产生 `<p>/ops`。ops 无需再 source（`ASCEND_OPP_PATH` 已由 toolkit 的 set_env.sh 导出）。
- 验证：`ls -d "$ROOT/cann-9.1.0/opp"`；10 个子包（opbase/hixl/hccl/dvpp/ops_math/ops_nn/ops_cv/ops_transformer/ops_ras/legacy）日志各一行 `install success`。

**6. 验收**（三件套合计耗时 ≈3 min：合一包链路 74+12+91s）

```bash
python3 -c "import acl;print(acl.get_soc_name())"          # 期望 Ascend910_9382
atc --help >/dev/null && echo "atc OK"                     # 不要用 atc --version，见坑 4
grep -n 'version_dirpath=' "$ROOT"/cann-*/set_env.sh       # 应等于 $ROOT/cann-9.1.0
npu-smi info | head -6
```

**7. 换版本 / 卸载**

```bash
# 换版本：新路径重装（步骤 0→6），再 source 新 $P/cann/set_env.sh；旧路径可保留共存
# 卸载（未验证：只读了卸载脚本原文，未执行过）；顺序 ops > toolkit
P=/mnt/share/x00886548/cann/cann_9_1_0      # ← 换成你的 CANN 安装根（别写 <p> 这类尖括号，bash 会当重定向）
cd $P/x86_64-linux/script && ./uninstall.sh        # toolkit（会连带卸 ops）
cd $P/x86_64-linux/script && ./ops_uninstall.sh    # 单独卸 ops
cd ${P%/cann_9_1_0}/nnal && ./nnal_uninstall.sh    # nnal（nnal 与 toolkit 同级，不在 toolkit 里）
```
- 也可 `./xxx.run --uninstall --install-path=$P`：它读 `Install_Path`，**归档目录里的旧 info 不会被读**；`cann_uninstall.sh` 必须不带任何参数运行（带参报 `parameter is not supported.`）。
- 合一包**不支持 `--upgrade`**（`--help` 无该项）；独立 toolkit 包与 ops/nnal 支持。要升级合一包装的 CANN：卸载后重装。

## 坑与修法

1. **`set -u` 与 CANN set_env.sh 冲突：未绑定变量有**两个**，不是一个**（2026-10-09 在 `.188` 对 `/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0/set_env.sh` 实测，`( set -u; source …/cann-9.1.0/set_env.sh )` 逐字报两条）：`…/cann-9.1.0/set_env.sh: line 31: CMAKE_PREFIX_PATH: unbound variable` 与 `…/cann-9.1.0/set_env.sh: line 48: PYTHONPATH: unbound variable`（旧记录只写 `ZSH_VERSION: unbound variable`，那是另一个 shell 侧的观测，**不完整**）→ 脚本引用未定义变量。修法：env 脚本里先 `set +u` **包住整段 source**，需要严格模式在 source 之后自己开——加 `set +u` 后同一条命令即得 `ASCEND_HOME_PATH=[/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0]`。（**从旧 `ascend-vllm-env` 搬来**）
2. **不先 source toolkit 就装 nnal**（真报错，exit code **4**）：
   `[cann-atb] [ERROR] Check owner failed, please check env ASCEND_TOOLKIT_HOME or ASCEND_NNAE_HOME is set.` → 先 `source <同版本 toolkit>/cann/set_env.sh`；否则 atb 装不上，只剩空 `<p>/nnal`。
3. **只装 toolkit 未装 ops**：`ImportError: libacl_dvpp.so: cannot open shared object file: No such file or directory` → `libacl_dvpp.so` 由 ops 的 `cann-dvpp_9.1.0` 子包提供。**这不是安装失败**，装完 ops 再跑 `import acl` 即通过（conda py3.14 与 /usr/bin/py3.7 都通过，输出 `Ascend910_9382`）。
4. **`atc --version` 不存在**：`ERROR: unknown command line flag 'version'` → 用 `atc --help` / `which atc` / 读 `opp/version.info`。同类无害噪声：`cp: cannot stat './script/TOOLKIT_uninstall.sh': No such file or directory`（`cann_uninstall.sh` 已正常生成）、`[ops_A3] [WARNING] delete operation, the directory <root>/cann-9.1.0 is not empty.` → 都忽略。
5. **重跑时通配符双匹配（本次新发现，最有价值的增量）**：首次安装 `./*toolkit*` / `./*nnal*` 各只命中 `.run`；**装过一次后安装根里多了 `ascend-toolkit/`、`nnal/` 目录，glob 展开成两个词**，shell 把目录当命令执行 → `Permission denied` / `Is a directory`，脚本挂。`./*cann_9*` 因下划线不会误匹配 `-A3-ops_9` / `-nnal_9` / `-toolkit_9`，**仍安全**；`./*cann*` 会全中，**不可用**。修法：`.run` 放独立 `pkgs/` 子目录（本 skill 步骤 1 就是这么做的），或写精确文件名。
6. **`source X | head` 后变量全空**：source 跑在管道子 shell 里 → 写 `source X >/dev/null 2>&1`。
7. **整体搬移安装树后 set_env.sh 失效**：`version_dirpath` 被**硬编码在 `<p>/cann-<ver>/set_env.sh` 第 63 行**（例 `version_dirpath="/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0"`）→ 必须重装或手改这一行。（`nnal/atb/set_env.sh` 由 `BASH_SOURCE` 推导，可移植。）
8. **每条 ssh 都打印** `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory` → 是**真实断链**（`latest -> /usr/local/Ascend/cann-9.1.0/cann`，该目录不存在；`readlink -f` 返回空），不是偶发噪声。修法：**别依赖 `/usr/local/Ascend/ascend-toolkit`**，显式 source `/mnt/share/x00886548/cann/cann_9_1_0/cann/set_env.sh`。**同一根因**（`/root/.bashrc: line 36` 这行 source 指向不存在的文件）也是 `.188` 上 **`ssh` 退出码恒为 1** 的原因——登录 shell 每次都报这一行。
9. **`.188` gcc-8 缺 `GLIBCXX_3.4.26` → CANN tiling 报"参数错误"**（从旧 `ascend-vllm-env` 坑 8 搬来，属 CANN 侧依赖）：系统 `libstdc++.so.6` 里 `GLIBCXX_3.4.26` 出现 0 次，而 CANN tiling 库 `libcust_opmaster_rt2.0.so` 依赖它，症状是 `dtype or format of parameter` / `NnopbaseExecutorDoTiling`，**看起来像算子用法错误**。修法：把 conda 环境的 `libstdc++.so.6.0.34` 复制到 `compat_lib/` 并 `export LD_LIBRARY_PATH=<compat_lib>:$LD_LIBRARY_PATH`（细节见 `ascend-torch-npu`）。
10. **`usergroup=root not right!`**（官方附录 C）：非 root 登录后 `su` 到 root 安装时 `USER` 仍是原用户 → `export USER=root` 后再装。
11. **公开下载源**：唯一可直连源 = `https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/<桶内目录名>/`（匿名只读；`-H "Referer: https://www.hiascend.com/"` **非必需**，2026-10-08 实测带/不带都 200）；`mirrors.huaweicloud.com/ascend/` 只托管 yum/apt 包，**不托管 run 包**。**合一包 `Ascend-cann_9.1.0_linux-x86_64.run` 不在公开桶**（403）→ 只用公开源时走「独立 toolkit 包」那支。

    **⚠️ 桶内目录名 ≠ 版本号 —— 这条只对 beta/T 构建成立，正式版目录名就是版本号**（2026-10-08 首测，2026-10-10 收窄复测）：9.2.0-beta.2 的目录是 **`CANN 9.2.T3`**，**不是** `CANN 9.2.0-beta.2`；而**正式版 9.1.0 的目录就叫 `CANN 9.1.0`**（`CANN%209.1.0/...` 直接命中 **200**）⇒ **只有 beta/T 构建需要按 T 号换名，正式版按版本号猜目录是"对的"**。但**别把"按版本号猜目录必 403"还在正式版上照搬**：旧记录「最高版本 = 9.1.0，9.2.0-beta.1/2 全 403」正是拿版本号当目录名去探 beta 得到的，**已被证伪**。

    | 探针（同批必须混入一个**已知存在**的对照对象，否则 403 分不清"无权限/目录错/不存在"） | 结果 |
    |---|---|
    | `CANN 9.2.T3/Ascend-cann-toolkit_9.2.0-beta.2_linux-x86_64.run` | **200**，Content-Length `1398240001`，ETag `6b5a5dc6d3cf9e9fcf680bf4684906cf` |
    | `CANN 9.2.0-beta.2/Ascend-cann-toolkit_9.2.0-beta.2_linux-x86_64.run`（目录名错） | 403 |
    | `CANN 9.2.T3/Ascend-cann-toolkit_9.2.0_linux-x86_64.run`（商发名，无 `-beta`） | 403 |
    | `CANN 9.2.0/Ascend-cann-toolkit_9.2.0_linux-x86_64.run` | 403 |

    → **公开源版本号最高 = 9.2.0-beta.2（社区版 / 预发布）**；**9.2.0 商发（无 `-beta`）公网确实不存在**（同一目录下 403，对照 beta.2 = 200），内网/商发渠道包才可能有。用户点名"9.2.0 商发"时要**先说明这一点**再决定用 beta.2。
    → **另：9.1.0 不是最新**（2026-10-10 实测）——公开源更新的**非 beta** 版是 **9.1.1**（目录名就是 `CANN 9.1.1`，OBS 实测 **200** / `1301221019 B` / 2026-09-01 构建）⇒ 要「最新的稳定版」选 **9.1.1**，要「最高版本号」才是 9.2.0-beta.2。**"最高 beta" ≠ "最新"**，用户说"最新"时先问清是哪一种。

    **9.2.0-beta.2 三包实测（2026-10-08，`CANN 9.2.T3/`；安装序列、参数、`-q` 行为与 9.1.0 完全一致，直接套用步骤 0~7）**：toolkit `1398240001 B` md5 `6b5a5dc6d3cf9e9fcf680bf4684906cf`；A3-ops `2533705704 B` md5 `d58d77bed571aa7561c547a454ffbbfe`；nnal `440760339 B` md5 `5e4eb1a4749490a20f8c0808b20855f2`。落盘形态同 9.1.0：`cann-9.2.0-beta.2/`（`opp/` 在它下面）+ `cann` / `ascend-toolkit` 兼容软链 + `nnal/`；`ASCEND_HOME_PATH=<p>/cann-9.2.0-beta.2`；`<p>/ops` 同样**不会**产生。**toolkit 的 OBS ETag 就等于 md5** → 判「下完没」可先读 `curl -I` 的 ETag，不必等下完再 `md5sum`。

    **下面那段并行下载脚本只需把 `B` 的目录名换掉**（`-C -` 续传、三条并发、`&`+`wait` 全部不变），例如 9.2.0-beta.2 用
    `B="https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%209.2.T3"`。

   **并行下载（＝ `ascend-env` §3.1 的 lane P1；三个包同时下，无任何前置依赖）**：

   ```bash
   PKGS=/home/vllm/x00886548/cann_test/pkgs; mkdir -p "$PKGS/log"; cd "$PKGS"
   B="https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%209.1.0"
   for f in Ascend-cann-toolkit_9.1.0_linux-x86_64.run \
            Ascend-cann-nnal_9.1.0_linux-x86_64.run \
            Ascend-cann-A3-ops_9.1.0_linux-x86_64.run ; do
     ( curl -L -k -C - -o "$PKGS/$f" "$B/$f" > "$PKGS/log/$f.log" 2>&1 ) &
   done
   wait
   ls -l "$PKGS"/*.run
   ```
   - 体积 / md5 / sha256（判"下完没"只看这个，**不看进程**）：toolkit `1298337341 B` md5 `bc4f2b6a09fe94f7891f946590c52c2c` / sha256 `69e52e49a5ac1dde756a0d72077e36df7382b37cd3e1d78005d9cdbf699aeafc`；nnal `572750476 B` md5 `f8918a5b8fcec5809df45c1b87469449` / sha256 `1a743a0957a77a0624c2ecfdf689b5c5937a9097fda1e3b3e8e0191a7d11c694`；A3-ops `2363708646 B`（无 md5 记录）/ sha256 `7449e7151c7c3a1c23f2eed6978699b3bb3602ca2662e653cec51da2ab0f61ee`（三个 sha256 均 2026-10-10 实测，可作为"下完没"的第二判据）。
   - **并行只能 `&` + `wait`，别指望下载器**（2026-10-08 实测）：`.188` 上 `aria2c` / `axel` **不存在**，`curl` 是 **7.64**，该版本的 `--parallel` 与 `-Z` **都不支持**（`curl --parallel UNSUPPORTED` / `curl -Z UNSUPPORTED`）；`wget` 有，但要并行同样得自己 `&`。实测三条并发 HEAD 同时返回 200。
   - `-C -` 断点续传：重跑同一条命令即续传，不从头再来（4.2G 量级值得留着）。
   - **这条 lane 与 CANN 安装完全解耦**：下载完可以先搁着，安装（上面步骤 2~5）等 4 条 lane 的 barrier 之后再统一做；它也可与 conda 建环境 / torch 栈 whl 预下载 / 两仓 clone 同时跑。全程编排见 `ascend-env` §3.1。
   - **文件名大小写敏感**（2026-10-10 实测）：9.1.0 的 A3 算子包是**大写 `Ascend-cann-A3-ops_9.1.0_linux-x86_64.run`** —— 小写 `a3-ops` = **403**，`Ascend-cann-kernels-910b_` = **403**；名字对不上时 403 与"不存在"长得一模一样。合一包 `Ascend-cann_9.1.0_linux-x86_64.run` = **403**（不在公开桶，见坑 11 首段）。
   - **该桶缺对象返回 403 而不是 404**（响应头 `x-obs-error-code: AccessDenied`），**列桶也全 403**（桶根、`?prefix=`、`?list-type=2` 都是 AccessDenied）⇒ 探版本时**同批必须同时混入正/负两种对照**（一个**已知存在**、一个**已知不存在**），否则分不清「无权限 / 目录名错 / 真不存在」，单靠一个 200 对照只能证"桶可达"，证不了"这个键不存在"。
   - **想"列目录"就别用 OBS**（2026-10-10 实测）：`https://ascend.devcloud.huaweicloud.com/cann/run/software/` 是**可列的 Artifactory 索引**（真的 `Index of` 页面，与 OBS 同一批产物——A3-ops 长度两边都是 `2363708646`），找/核文件名用它比逐个探 OBS 快。
   - **hiascend 文档站是 SPA，但 `/doc_center/source/zh/...` 直出静态原文**（如 `.../CANNCommunityEdition/910/softwareinst/instg/instg_0008.html`）——**同目录并非同规则**（实测 0003 / 0005 / 0008 = 200，0001 / 0002 / 0004 / 0006 / 0007 / 0009 = 403）⇒ 文档页只能**逐个探**，别按"同目录应该都能取"推断。

12. **安装器的既有副作用 + 「注册表在运行时不被查询」**（2026-10-08 实测）：安装器会创建 `/etc/Ascend/<日期时间>` 备份目录（本轮实测 `/etc/Ascend/20261008_194804`）并改写全局注册表 `/etc/Ascend/ascend_cann_install.info`。把注册表恢复成**原值**（本轮恢复到指向**别人**的 `…/vllm_0230/cann/cann_9_2_0/cann-9.2.0-beta.2`）之后，这套新装的 CANN **依然完全正常**（`import acl` 得 `ACL_SOC Ascend910_9382`、真实推理成功）⇒ **注册表在运行时不被查询**，别把它当"跑不起来的原因"。`/root/.bashrc` **未被改动**（改动前后 md5 一致，本轮同为 `2a9409ac2cbfff2e64b05c3d866f711b`）。纪律：注册表 md5 **现场取 + 存档**（步骤 0），**不要硬编码**——历史正文里那种写死的期望值会随别人重装而失效。
13. **CANN 的 `set_env.sh` 会污染 `PYTHONPATH`，把 `pip list` / `pip check` 搞花**（2026-10-08 实测）：它把 `.../cann-9.1.0/python/site-packages` 与 `.../cann-9.1.0/opp/built-in/op_impl/ai_core/tbe` 前置 ⇒ pip 会看到 CANN 自带的一堆发行包。本轮实测多出 **5 条噪声**（逐字）：
    ```
    schedule-search 0.0.1 requires absl-py, which is not installed.
    mindstudio-kpp 26.1.0 requires plotly, which is not installed.
    ms-service-profiler 26.0.0 requires matplotlib/msguard/openpyxl/tzdata, which is not installed.
    affinity-sched 26.1.0 requires argparse, which is not installed.
    ms-service-profiler 26.0.0 has requirement pandas~=2.2, but you have pandas 3.0.6.
    ```
    ⇒ **判环境要用 `pip list --local` 或直接看 site-packages**，不要被这 5 条误导成"环境装坏了"。
14. **判「实际加载了哪套 CANN」不要看环境变量，看进程真实映射**：在 python 里读 `/proc/self/maps` 再正则抓 CANN 路径即可（本轮 85 条路径**全部**指向 `$ROOT/cann/cann-9.1.0`，判定 has sv0230/cann: True）。可复制命令与完整判据 → `vllm-ascend-source-install` §5.2，本文件不重复。
15. **绝对不要 source `nnal/asdsip/set_env.sh`**（2026-10-09 在 `.188` 用 `env -i` 全新 shell 实测）：它**把自己插到 `LD_LIBRARY_PATH` 最前面**——source 之前头部 = `/home/vllm/x00886548/xmz_1009_k3/compat_lib`，source 之后头部 = `/mnt/share/x00886548/cann/cann_9_1_0/nnal/asdsip/latest//lib`（**路径里那个双斜杠是原文**）；紧接着 `import torch, torch_npu` 崩：
    ```
    File ".../torch_npu/npu/__init__.py", line 273, in _lazy_init
        torch_npu._C._npu_init()
    RuntimeError: /mnt/share/x00886548/cann/cann_9_1_0/nnal/atb/latest/atb/cxx_abi_1/lib/libtbe_adapter.so: undefined symbol: _ZN3Mki15PlatformManager8InstanceEv
    [ERROR] 2026-10-09-17:38:46 (PID:209868, Device:-1, RankID:-1) ERR99999 UNKNOWN applicaiton exception
    ```
    → 原因（**两重危害，第二重更隐蔽**）：① asdsip 的 lib 目录抢先被搜到，**shadow 掉 `nnal/atb` 的 `libtbe_adapter.so`**（报错里那个 `.so` 路径正是 atb 的，符号 `_ZN3Mki15PlatformManager8InstanceEv` 找不到）；② 它**把 `compat_lib` 从 `LD_LIBRARY_PATH` 首位挤掉**，于是坑 9 的 `GLIBCXX_3.4.26` 修复**被静默废掉**（该修复正是靠把 conda 的 `libstdc++.so.6.0.34` 前置）。
    → 修法：**只需 source 两段——toolkit（步骤 3）+ `nnal/atb`（步骤 4）**；`nnal/asdsip/set_env.sh` **一行都不要 source**。对照实验：把这一行 source 去掉即恢复正常。注意 `nnal/` 与 `cann-9.1.0/` **同级**：`/mnt/share/x00886548/cann/cann_9_1_0/nnal/atb/set_env.sh` 存在，而 `/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0/nnal/atb/set_env.sh` **不存在**。

## 不要做什么

- **不要 `rm -rf /etc/Ascend/ascend_cann_install.info`**：用户原脚本的第一处前提**已被本次实测推翻** —— 不删直接装 **exit 0**，安装器自动把旧 info 归档到 `/etc/Ascend/<YYYYmmdd_HHMMSS>/`；删与不删唯一差异 = **少一个归档目录（可追溯性变差）**。只在换路径重装前**备份**它（步骤 0）。
- **不要 `chmod -R 777 .`**：用户原脚本的第二处前提**已被本次实测推翻** —— 官方只要求 `chmod +x ./*.run`，实测即成功；而且**重跑时 `-R` 会递归改 9G 的安装树**，安全风险大，且与官方「root 755 / 非 root 750」基线冲突。
- 不要在安装根里用 `./*toolkit*` / `./*nnal*` / `./*cann*`（重跑双匹配，见坑 5）；不要用 `atc --version`；不要用合一包的 `--upgrade`（不支持，要升级只能卸载后重装）。
- 不要依赖 `/usr/local/Ascend/ascend-toolkit`（`.188` 上是断链）。
- 不要把 CANN 装到共享盘再挂载使用（官方：文件锁依赖可能导致任务拉起失败）。**例外**：本机 `/mnt/share` 经 `findmnt -T` 实测是本地盘 `nvme0n1p2 ext4`，只是目录名叫 share，**不受此限**——但换机器要重新确认。
- 未验证，别当结论用：`--check` / `--full` / `--force` / `--install-for-all` / `--torch_atb` / `--feature` / `--type` / `--whitelist=toolkit`、非 root 安装、卸载流程、nnal 的 `cxx_abi_0` 分支、`/usr/local/Ascend` 默认路径安装——**本次只读了 help 原文，未实测**。

## 验收标准

1. `python3 -c "import acl;print(acl.get_soc_name())"` → **`Ascend910_9382`**（官方验收命令，必须在 ops 装完后跑）。
2. `echo $ASCEND_HOME_PATH` → `<p>/cann-9.1.0`；`echo $ASCEND_OPP_PATH` → `<p>/cann-9.1.0/opp`；`echo $ATB_HOME_PATH` → `<p>/nnal/atb/latest/atb/cxx_abi_1` 且目录存在。
3. `atc --help` rc=0；`npu-smi info` 头部 `Version: 25.5.1`，16 个 Ascend910。
4. `ls -d <p>/cann-9.1.0 <p>/cann <p>/ascend-toolkit <p>/nnal` 全存在；`ls <p>/ops` 应**报不存在**（正常）。
5. `grep -n 'version_dirpath=' <p>/cann-<ver>/set_env.sh` 第 63 行等于 `<p>/cann-<ver>`；驱动未被改动：`md5sum /etc/ascend_install.info` = `e0ae42a0d046fa6a0ec8f26e9693eef8`。
