---
name: ascend-cann-env
description: CANN 检测/安装/换版/卸载：install.info 定位、三件套序列。适用于"装 CANN / import acl 报错 / ASCEND_HOME_PATH 为空 / Permission denied / 该用哪个包"。
whenToUse: 要在 192.168.13.188/.190 上查 CANN 装在哪、什么版本，装或重装 CANN 9.1.0，切版本、修 CANN 环境变量，或判断该用合一包还是独立 toolkit 包时使用。
---

# 昇腾 CANN 检测 / 安装 / 激活 / 换版本 / 卸载（9.1.0 真机实测）

环境写死：`a3`=`root@192.168.13.188`（默认）/ `a3b`=`.190`（备用）；生产 CANN 9.1.0 在 `/home/x00886548/env/cann/cann_9_1_0`（`cann-9.1.0/` 9.2G + `nnal/` 1.1G；旧路径 `/mnt/share/x00886548/cann` 是兼容软链，勿删）；driver 25.5.1；芯片 `Ascend910_9382`。远端执行硬规则（禁内联引号/heredoc、`ssh -n` 互斥）见 **`ascend-env` §5**，磁盘红线见 `ascend-server-layout`。

## 何时调用

**加载本 skill 当：**
- 要查「CANN 装在哪 / 什么版本 / 机器上有几份」，或 `import acl`、`atc`、算子编译报找不到 CANN。
- 要装 / 重装 / 换路径 / 换版本 / 卸载 CANN 9.1.0（toolkit、ops、nnal 三件套）。
- `source set_env.sh` 之后 `ASCEND_HOME_PATH` 为空，或指向已不存在的目录。

**不要用本 skill（转交）：**
- 问题在 conda 环境或 python 版本 → 用 `ascend-conda-env`。
- 只是不知道该往哪写文件 / 磁盘满了 / 找模型在哪 → 用 `ascend-server-layout`。
- 已装好 CANN，卡在 torch_npu 装不上 → 用 `ascend-torch-npu`。
- triton-ascend 装不上 / 被 pip install -U triton 覆盖 → 用 `ascend-triton-ascend`。
- 起服务 / 离线推理冒烟 / 显存释放与运行时排障 → 用 `ascend-vllm-serve`。
- 从源码装 / 重装 vllm 与 vllm-ascend（按 verified commit 配对） → 用 `vllm-ascend-source-install`。

**前置**：能 ssh 进 `a3`（免密已配）。 ／ **后继**：`ascend-conda-env` → `ascend-torch-npu`。

## 前置检查

```bash
P=$(awk -F= '/^Install_Path=/{print $2}' /etc/Ascend/ascend_cann_install.info); echo "P=$P"
readlink -f "$P/cann"                                                    # 实体版本目录 <P>/cann-<ver>
ls "$P"/cann-*/x86_64-linux/*install.info               # 有 all_cann=合一包装的；有 toolkit=独立包装的
cat /usr/local/Ascend/driver/version.info | head -2                      # Version=25.5.1
npu-smi info | head -6 ; df -h "$P" ; python3 -V ; ls -d /home/vllm
```

- `P` 是权威来源（`/etc/Ascend/ascend_cann_install.info` 由 toolkit 安装器写，2 行：`Install_Path` + `Toolkit_InstallPath`）；**`/etc/ascend_install.info` 是 driver 写的，别混**（toolkit 的 `set_env.sh` 靠它的 `Driver_Install_Path_Param` 找 `libascend_hal.so`）。
- 判据：有 `ascend_all_cann_install.info` = 合一包装的（`package_name=Ascend-cann`，`innerversion=V100R001C25B114`）；只有 `ascend_toolkit_install.info` = 独立包（`package_name=Ascend-cann-toolkit`，`innerversion=V100R001C11SPC001B243`）。两者**布局完全一致**。
- 驱动基线（装 CANN 前后必须不变）：`e0ae42a0d046fa6a0ec8f26e9693eef8  /etc/ascend_install.info`、`4019d58ec411a20a27e1b3415123a78a  /usr/local/Ascend/driver/version.info`。
- 磁盘：官方要求 toolkit 安装目录可用空间 **>10GB**；`.188` 只有 `/home/vllm`（6.9T，剩 3.5T）能写，`/mnt/share`、`/tmp`、`/root` 全与 `/` 同盘（剩 392G）。
- Python 官方支持 **3.7.x–3.14.x**；`.188` 的 conda base 3.14.7 与 `/usr/bin/python3`（3.7.3）实测都通过 `import acl`。conda 见 `ascend-conda-env`。

## 步骤

**0. 备份全局登记文件（换路径/重装前必做）**

```bash
BK=/home/vllm/x00886548/cann_test/etc_Ascend_backup; mkdir -p "$BK"
cp -a /etc/Ascend/ascend_cann_install.info "$BK"/ascend_cann_install.info.orig
md5sum "$BK"/ascend_cann_install.info.orig    # 期望 a2d38ce7fe341e70acfc9f30a10e21bc；收尾时 cp -a 还原并复验
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
# 换版本：新路径重装（步骤 0→6），再 source 新 <p>/cann/set_env.sh；旧路径可保留共存
# 卸载（未验证：只读了卸载脚本原文，未执行过）；顺序 ops > toolkit
cd <p>/cann-<ver>/x86_64-linux/script && ./uninstall.sh        # toolkit（会连带卸 ops）
cd <p>/cann-<ver>/x86_64-linux/script && ./ops_uninstall.sh    # 单独卸 ops
cd <p>/nnal && ./nnal_uninstall.sh                             # nnal
```
- 也可 `./xxx.run --uninstall --install-path=<p>`：它读 `Install_Path`，**归档目录里的旧 info 不会被读**；`cann_uninstall.sh` 必须不带任何参数运行（带参报 `parameter is not supported.`）。
- 合一包**不支持 `--upgrade`**（`--help` 无该项）；独立 toolkit 包与 ops/nnal 支持。要升级合一包装的 CANN：卸载后重装。

## 坑与修法

1. **`set -u` 与 CANN set_env.sh 冲突**：`ZSH_VERSION: unbound variable` → 脚本引用未定义变量。修法：env 脚本里先 `set +u`，需要严格模式在 source 之后自己开。（**从旧 `ascend-vllm-env` 搬来**）
2. **不先 source toolkit 就装 nnal**（真报错，exit code **4**）：
   `[cann-atb] [ERROR] Check owner failed, please check env ASCEND_TOOLKIT_HOME or ASCEND_NNAE_HOME is set.` → 先 `source <同版本 toolkit>/cann/set_env.sh`；否则 atb 装不上，只剩空 `<p>/nnal`。
3. **只装 toolkit 未装 ops**：`ImportError: libacl_dvpp.so: cannot open shared object file: No such file or directory` → `libacl_dvpp.so` 由 ops 的 `cann-dvpp_9.1.0` 子包提供。**这不是安装失败**，装完 ops 再跑 `import acl` 即通过（conda py3.14 与 /usr/bin/py3.7 都通过，输出 `Ascend910_9382`）。
4. **`atc --version` 不存在**：`ERROR: unknown command line flag 'version'` → 用 `atc --help` / `which atc` / 读 `opp/version.info`。同类无害噪声：`cp: cannot stat './script/TOOLKIT_uninstall.sh': No such file or directory`（`cann_uninstall.sh` 已正常生成）、`[ops_A3] [WARNING] delete operation, the directory <root>/cann-9.1.0 is not empty.` → 都忽略。
5. **重跑时通配符双匹配（本次新发现，最有价值的增量）**：首次安装 `./*toolkit*` / `./*nnal*` 各只命中 `.run`；**装过一次后安装根里多了 `ascend-toolkit/`、`nnal/` 目录，glob 展开成两个词**，shell 把目录当命令执行 → `Permission denied` / `Is a directory`，脚本挂。`./*cann_9*` 因下划线不会误匹配 `-A3-ops_9` / `-nnal_9` / `-toolkit_9`，**仍安全**；`./*cann*` 会全中，**不可用**。修法：`.run` 放独立 `pkgs/` 子目录（本 skill 步骤 1 就是这么做的），或写精确文件名。
6. **`source X | head` 后变量全空**：source 跑在管道子 shell 里 → 写 `source X >/dev/null 2>&1`。
7. **整体搬移安装树后 set_env.sh 失效**：`version_dirpath` 被**硬编码在 `<p>/cann-<ver>/set_env.sh` 第 63 行**（例 `version_dirpath="/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0"`）→ 必须重装或手改这一行。（`nnal/atb/set_env.sh` 由 `BASH_SOURCE` 推导，可移植。）
8. **每条 ssh 都打印** `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory` → 是**真实断链**（`latest -> /usr/local/Ascend/cann-9.1.0/cann`，该目录不存在；`readlink -f` 返回空），不是偶发噪声。修法：**别依赖 `/usr/local/Ascend/ascend-toolkit`**，显式 source `/mnt/share/x00886548/cann/cann_9_1_0/cann/set_env.sh`。
9. **`.188` gcc-8 缺 `GLIBCXX_3.4.26` → CANN tiling 报"参数错误"**（从旧 `ascend-vllm-env` 坑 8 搬来，属 CANN 侧依赖）：系统 `libstdc++.so.6` 里 `GLIBCXX_3.4.26` 出现 0 次，而 CANN tiling 库 `libcust_opmaster_rt2.0.so` 依赖它，症状是 `dtype or format of parameter` / `NnopbaseExecutorDoTiling`，**看起来像算子用法错误**。修法：把 conda 环境的 `libstdc++.so.6.0.34` 复制到 `compat_lib/` 并 `export LD_LIBRARY_PATH=<compat_lib>:$LD_LIBRARY_PATH`（细节见 `ascend-torch-npu`）。
10. **`usergroup=root not right!`**（官方附录 C）：非 root 登录后 `su` 到 root 安装时 `USER` 仍是原用户 → `export USER=root` 后再装。
11. **公开下载源**：唯一可直连源 = `https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%20<版本>/`（匿名只读）。**最高版本 = 9.1.0**（9.2.0 / 9.2.0-beta.1/2 / 9.1.RC1 / 9.0.RC1 全 403，已用对照对象证伪）；`mirrors.huaweicloud.com/ascend/` 只托管 yum/apt 包，**不托管 run 包**。**合一包 `Ascend-cann_9.1.0_linux-x86_64.run` 不在公开桶**（403）→ 只用公开源时走「独立 toolkit 包」那支。

   ```bash
   mkdir -p /home/vllm/x00886548/cann_test/pkgs && cd /home/vllm/x00886548/cann_test/pkgs
   B="https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%209.1.0"
   curl -L -k -C - -O "$B/Ascend-cann-toolkit_9.1.0_linux-x86_64.run"   # 1298337341 B, md5 bc4f2b6a09fe94f7891f946590c52c2c
   curl -L -k -C - -O "$B/Ascend-cann-nnal_9.1.0_linux-x86_64.run"      #  572750476 B, md5 f8918a5b8fcec5809df45c1b87469449
   curl -L -k -C - -O "$B/Ascend-cann-A3-ops_9.1.0_linux-x86_64.run"    # 2363708646 B
   ```
   - **该桶缺对象返回 403 而不是 404**，列桶也 403 → 探版本时必须同批混入一个**已知存在**的对照对象（否则会把「无权限」当「不存在」）。

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
