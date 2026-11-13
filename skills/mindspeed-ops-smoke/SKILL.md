---
name: mindspeed-ops-smoke
description: MindSpeed-Ops 冒烟：按版本矩阵建环境、UT + ATK 精度双读判绿。适用于"跑 26.2.0 冒烟 / ATK 精度怎么判 / 冒烟全绿了吗 / CI 镜像配套对不对"。
---

# MindSpeed-Ops 商发配套冒烟（UT + ATK）

**本 skill 只讲「怎么把 26.2.0 商发配套的冒烟跑起来并判读」。** 环境铺设（CANN / conda / torch 栈）细节一律在 `ascend-*` 子 skill；本文件只写这一套冒烟实测跑通的路径、坑与判据。

## 何时调用

**加载本 skill 当：**
- 用户说"跑一遍 26.2.0 的商发配套冒烟""看看 MindSpeed-Ops 最新代码有没有问题""冒烟是不是全绿"。
- **要跑 26.2.0 商发冒烟：不要重建环境，直接用现成镜像**——`mindspeed-ops-smoke:2620-950` 已做好并验证（§12.11 给了位置、校验和、load/run 命令；判读基线见 §12.9）。
- 需要知道某分支的**配套版本矩阵**（CANN / PyTorch / TorchNPU / Triton-Ascend）从仓库哪个文件读。
- ATK 报 `Invalid exchange name: '127.0.0.1:9090@...'`、`Address already in use`（端口 8881）、`acc_pass_result: Failed` 但 `failed: 0`。
- UT 或 ATK 在共享机上出现随机 NaN/Inf、`NPU out of memory`，怀疑被别人抢卡。

**不要用本 skill（转交）：**
- 装 / 换 / 查 CANN → `ascend-cann-env`；conda 与 python → `ascend-conda-env`；torch 与 torch_npu → `ascend-torch-npu`；triton-ascend → `ascend-triton-ascend`。
- 机器目录与磁盘选址 → `ascend-server-layout`；从 Windows 驱动远端 → `ascend-env` §5。
- 冒烟跑完要提 PR / 判门禁 → `gitcode-pr-flow`。

**前置**：目标机能与 CANN 配套的 NPU 可用（`npu-smi info` 正常）；已确认要测的分支 commit。
**后继**：结果写报告；失败算子按本 skill §6 复跑复核，再决定是否算代码问题。

## 1. 先定「配套」，别自己猜版本

配套矩阵只认仓库这两处（同一分支内自洽）：

```bash
sed -n '1,40p' docker/OVERVIEW.zh.md        # Tag 组成规则 + 各组件版本示例
git show --stat <最近一次"更新 Docker 配套版本"的提交>   # 实际改动的版本号
cat pyproject.toml                          # build-system 里 pin 的 triton-ascend
cat requirements.txt
```

26.2.0 的配套（2026-11-09 实测，提交 `70c1479` 的说明逐字）：

| 组件 | 版本 |
|---|---|
| CANN | 9.2.0 |
| PyTorch | 2.10.0（cpu 版 `2.10.0+cpu`） |
| TorchNPU（PTA） | 2.10.0.post7 |
| Triton-Ascend（TA） | 3.6.0（连带 `triton==3.6.0`、`numpy==1.26.4`） |

> `pyproject.toml` 里 `triton-ascend==3.6.0` 是权威 pin；装错版本会在算子层出精度或编译问题，且错误信息不指向版本。
>
> **TorchNPU 有两个口径，别混**：产品口径（`docs/zh/release_notes_ops.md` 兼容表、install_guide 正文）写 `26.2.0`；**包口径/pip 版本是 `2.10.0.post7`**。PyPI 与华为镜像上 `torch-npu` 共 67 个版本、2.10 线最高 `2.10.0.post7`，**没有 `26.2.0`**（实测 `pip download torch-npu==26.2.0` → `ERROR: No matching distribution found`）。凡是要填 `--torch-npu-version` / `pip install torch-npu==` 的地方一律用 `2.10.0.post7`。

## 2. 环境搭建（一机一套，可复用）

```bash
WD=/home/x00886548/smoke2620        # 放 /home（大文件盘），别放 / 或 /tmp
ENVP=$WD/envs/py310
export TMPDIR=$WD/tmp PIP_CACHE_DIR=$WD/pipcache
/mnt/share/miniconda3/bin/conda create -p $ENVP python=3.10 -y --override-channels \
  -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c https://mirrors.nju.edu.cn/anaconda/pkgs/r
PY=$ENVP/bin/python; PIP="$PY -m pip"

# 顺序不能换：torch -> torch_npu -> triton-ascend（后者会把 numpy 拉回 1.26.4）
$PIP install "torch==2.10.0+cpu" --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple/
$PIP install "torch-npu==2.10.0.post7" --index-url https://mirrors.aliyun.com/pypi/simple/
$PIP install "triton-ascend==3.6.0" \
  --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple \
  --index-url https://mirrors.aliyun.com/pypi/simple/
$PIP install pytest pyyaml pybind11 regex --index-url https://mirrors.aliyun.com/pypi/simple/
```

- **osinfra 下 triton-ascend 极慢**（321MB 实测卡住 15 分钟以上）。已知有装好的机器时**直接搬 wheel**：
  ```bash
  # 188 -> 190 免密直传（两机 root 公钥互通，别走 Windows 中转）
  ssh root@192.168.13.188 "ls /home/x00886548/ms2620/wheelhouse/*.whl"
  scp -o BatchMode=yes root@192.168.13.188:/home/x00886548/ms2620/wheelhouse/triton-3.6.0-*.whl \
      root@192.168.13.190:/home/x00886548/smoke2620/wheels/
  $PIP install --find-links=$WD/wheels "triton-ascend==3.6.0" \
      --index-url https://mirrors.aliyun.com/pypi/simple/      # 小依赖走镜像，大 wheel 走本地
  ```
  `--no-index` 会因 `attrs==24.2.0 / scipy==1.13.1 / psutil==6.0.0` 等 pin 不在本地而失败，加 `--find-links` + 镜像即可。
- **ATK 工具**：仓库 `tests/atk_tests/triton/README.md` 指向 GitCode 的 ATK release。已有装好机器时直接搬同 cp 版本的 wheel（实测 `atk-26.9.24-cp310-cp310-linux_x86_64.whl`，12MB），`$PIP install <whl>` 会连带装 celery/kombu 等。
- **激活脚本**（所有执行脚本都 source 它）：
  ```bash
  cat > $WD/activate.sh <<'EOF'
  export WD=/home/x00886548/smoke2620 REPO=$WD/ops2620 ENVP=$WD/envs/py310
  export TMPDIR=$WD/tmp PIP_CACHE_DIR=$WD/pipcache
  set +u                                   # ← 必须，见坑 1
  . /mnt/share/cann/cann-9.2.0/cann-9.2.0/set_env.sh >/dev/null 2>&1
  . /mnt/share/cann/cann-9.2.0/nnal/atb/set_env.sh >/dev/null 2>&1
  export PATH=$ENVP/bin:$PATH PYTHONPATH=$REPO:${PYTHONPATH:-} PYTHONDONTWRITEBYTECODE=1
  EOF
  ```
- 验收（唯一硬判据）：`python -c "import torch,torch_npu;print(torch.__version__,torch_npu.__version__,torch.npu.is_available(),torch.npu.device_count(),torch.npu.get_soc_version())"` → A3 上期望 `2.10.0+cpu 2.10.0.post7 True 16 253`。
- 仓库用 `git clone -b <branch>` + `reset --hard origin/<branch>` 取最新；**跑 UT/ATK 不需要 `pip install -e .`**（`PYTHONPATH=$REPO` 即可）。未编译扩展时 `import mindspeed_ops` 只会打一行 `mindspeed_ops_C{*.so,*.pyd} not found ... Rebuild ... pip install -e .`，属于预期。

## 3. 选卡（共享机必须做）

```bash
npu-smi info -t proc-mem -i 0..7     # 看哪些 npu 有别人的进程
npu-smi info | grep -E '^\| [0-9]+ +Ascend910'   # AICore%/HBM 用量
```

- 判据：**AICore 0、HBM 只有基线（~3GB）、`No process in device`** 才算空闲。
- 一个 npu = 2 个 die；`ASCEND_RT_VISIBLE_DEVICES=<die>` 选 die，ATK 的 `--devices` 始终写 0（重映射后）。
- **别在别人占用的 die 上跑**：会出现随机 NaN/Inf 与大 shape OOM，把环境问题误判成代码 bug（见坑 4）。

## 4. 跑冒烟（两段，与 tests/nightly_test.sh 同口径）

### 4.1 UT（24 文件，8 分片并发）

```bash
# 每片：独占一个 die + 独立 TRITON_CACHE_DIR（防旧 cache 造成假阴性/假阳性）
. $WD/activate.sh
export ASCEND_RT_VISIBLE_DEVICES=<die> TRITON_CACHE_DIR=$WD/cache/<tag>
cd $REPO/tests/unit_tests/triton
timeout 2700 python -m pytest -q -p no:cacheprovider -rf test_xxx.py > $WD/logs/ut/<tag>_test_xxx.log 2>&1
grep -aE '[0-9]+ (passed|failed|error|skipped)' <log> | tail -1
```

- 分片用 `ls test_*.py | awk -v s=$s 'NR%8==(s+1)%8'` 轮转；`setsid nohup ... < /dev/null &` 起后台。
- **必须 `cd` 到 `tests/unit_tests/triton` 再跑**：pytest 参数只给文件名时，工作目录不对会 `ERROR: file or directory not found`，但外层脚本仍返回 0，极易漏判（本次踩过）。

### 4.2 ATK 精度（27 算子，串行）

```bash
. $WD/activate.sh
export ASCEND_RT_VISIBLE_DEVICES=<die> TRITON_CACHE_DIR=$WD/cache/atk
cd $REPO/tests/atk_tests/triton
for d in */; do op=${d%/}
  [ -f "$op/$op.yaml" ] && [ -f "$op/generate_$op.py" ] && [ -f "$op/triton_$op.py" ] || continue
  cd "$op"
  timeout 1200 atk case -f "$op.yaml" -p "generate_$op.py" > $WD/logs/atk/case_$op.log 2>&1
  timeout 5400 atk node --backend triton --devices 0 node --backend cpu --devices 0 task \
    -c "result/$op/json/all_$op.json" --task accuracy -p "triton_$op.py" > $WD/logs/atk/atk_$op.log 2>&1
  grep -aoP 'acc_pass_result:\s*\K\S+' $WD/logs/atk/atk_$op.log | tail -1
  cd ..
done
```

- **参考实现必须 `--backend cpu`**。`tests/nightly_test.sh` 里写的是 `--backend npu`，用 npu 做标杆会出现「全部执行成功却 `acc_pass_result: Failed`」的假失败（`l2norm` 实测）。
- **ATK 只能单实例**：`sqlite_web:8881` 与 worker `127.0.0.1:9090` 都是硬编码。并行第二实例会全量失败。

## 5. 判读（别只看退出码）

| 层 | 看什么 | 通过判据 |
|---|---|---|
| UT 单片 | 该文件 pytest log 末行 | `N passed` 且无 `failed/error`；`skipped` 正常（skipif 覆盖未支持 dtype/shape） |
| ATK 执行 | `Total Task: N, success N, failed 0` | 三者一致才说明**跑完了** |
| ATK 精度 | `acc_pass_result: Pass/Failed` | 只有 `Pass` 才算过；`Failed` 时去 report 的 `精度详情` 看 max_abs/max_rel 或 NaN |

- ATK 报告在 `<op>/atk_output/<时间戳>/report/*.xlsx`，sheet：`summary`（总数/通过率/精度是否达标）、`statistic`（逐 case，含 `精度详情`、`运行结果`、`失败原因`）。
- 批量聚合：读每个算子的 `summary` 行即可（列序：名称/总用例/执行成功/执行失败/通过/错误匹配/通过率/精度是否达标）。
- 常见"看着失败其实不是代码问题"的三类：**NaN/Inf**（抢卡）、**OOM**（shape 太大或卡被占）、**假失败**（用 npu 当参考）。

## 6. 失败复跑协议（结论前必做）

1. `npu-smi info -t proc-mem -i <npu>` 确认目标 die 空闲；换一个干净 die。
2. 单算子复跑：`cd tests/atk_tests/triton/<op>` 重跑 `atk case` + `atk node`（脚本：`rerun_op.sh <op> <die>`）。
3. 仍失败 → 写最小复现脚本（`PYTHONPATH=<tree> python repro.py`），并在**多棵树**上跑（`git worktree add <dir> <commit>`）判断是否本次改动引入。
4. 复现脚本要注意：**ATK 的 triton wrapper 会先对 q/k 做 l2norm**，漏这步可能复现不出（本次实测：不加 l2norm 全绿，加了才暴露）。

## 7. 坑与修法

1. **`set -u` + CANN `nnal/atb/set_env.sh` → 整个脚本静默 exit 1（零输出）**
   原文：`/tmp/x.sh: line ...` 之后什么都没有，`rc=1`。
   成因：atb 脚本里有 `until [[ -z "$1" ]]` 之类，无参调用在 `set -u` 下触发 unbound，source 直接终止调用方。
   修法：`activate.sh` 里 source 前后 `set +u`；执行脚本本身别用 `set -u`。
2. **ATK 在 kombu 5.7.0 下必失败**：`amqp.exceptions.ChannelError: Invalid exchange name: '127.0.0.1:9090@create_dataset'` + `create_tasks fail ... 'NoneType' object has no attribute 'client'`。
   修法：降到与已知可用环境一致 —— `pip install kombu==5.6.2 amqp==5.4.1 billiard==4.3.1`。
3. **ATK 端口残留**：`Address already in use`（8881）或 `Connection refused (9090)`。
   修法：`pkill -9 -f 'run_atk_all|atk node|atk case|sqlite_web'`，**等 `ss -lntp | grep -E ':(8881|9090) '` 空出来**再起；起后 30 秒内 `grep -c ChannelError` 应为 0。
4. **共享机抢卡会伪造失败**：别人进程占 die（AICore 100%、HBM 40-60GB）时，triton 算子随机输出 NaN/Inf、大 shape OOM。
   实证：同一份 48 例扫描脚本，在被占 die 上跑两次分别 22/48、14/48 例 NaN；换空闲 die 跑两次 **0/48**。
   修法：跑前选空闲 die；失败后换 die 复跑，再定性。
5. **`/mnt/share` 在两台机器上内容不同**，别把它当共享中转盘（本次 188 写的目录 190 看不到）；跨机搬文件用 `scp 188 -> 190` 直连。
6. **ATK 进程会被外部 SIGKILL**：表现为 `summary` 里 `rc=137` + 主日志 `... Killed`，机器 `free` 仍充足。当成环境事件，复跑该算子，不要写进代码问题。
7. **pytest 工作目录**：见 §4.1；`file or directory not found` 时先查 `cd`。

## 8. 不要做什么

- 不要凭"最新版本号"自己配环境——配套版本只认仓库 `docker/OVERVIEW.zh.md` + pin 文件。
- 不要用 `--backend npu` 做 ATK 参考；不要为消 `pip check` 警告升降 numpy（triton-ascend 硬 pin 1.26.4）。
- 不要在别人占用的 die 上下结论；不要把 OOM/NaN 直接记成算子 bug。
- 不要并行跑两个 ATK 实例；不要在 ATK 运行时 `pkill` 模糊匹配自己的进程组。
- 不要用 `pip install -e .` 的结果冒充冒烟结论（未编译扩展时它只影响 atb/aclnn/tilelang/catlass 用例，后者现在会 skip）。

## 9. CI 镜像与分支配套一致性（换配套前先查这三处）

```bash
grep -n 'image:' .gitcode/workflows/pr-pipeline-mindspeed-ops.yml        # 门禁真正跑的镜像（tag 通常不含版本）
grep -nE '^ARG ' ci/Dockerfile; grep -nE '^(BASE_IMAGE_VERSION|TORCH_NPU_VERSION|TRITON_ASCEND_VERSION)=' ci/build.sh   # 配方版本钉
sed -n '1,12p' ci/CI_GUID.md                                            # 镜像名里写死的版本，人眼可读的真相
```

- **`ci/` 与 `docker/` 是两套配方**：`docker/` 随发版升，`ci/` 会落后。2026-11-10 实测 master 与 26.2.0 的 `ci/{Dockerfile,build.sh,MindSpeed_Ops_ut.sh}` **blob 完全相同**，都还是 CANN 9.1.0 / torch_npu 2.10.0 / TA 3.2.2 / py3.12（26.2.0 的 `docker/` 已是 9.2.0/post7/3.6.0）。改 `docker/` ≠ 改 CI。
- `ci/MindSpeed_Ops_ut.sh:30` 用 `pip install -e . --no-deps` ⇒ 分支 `requirements.txt` 的 TA 钉在 CI 里**不生效**，实际 TA 只由镜像决定。一个镜像只能服务一个 TA 版本，跨分支共用镜像必然有一边静默跑在不匹配的栈上。
- 门禁镜像 tag 只含 `chip/os/py/arch`（如 `...-py3.11-aarch64-0820`），**不能自证版本**；判线上实况只能进镜像：`cat /usr/local/Ascend/ascend-toolkit/version.cfg` + `python -c "import torch,torch_npu,importlib.metadata as m;print(torch.__version__,torch_npu.__version__,m.version('triton-ascend'))"`。
- 换配套时的可得性三查（2026-11-10 实测均 OK）：ascendhub 有 `cann:9.2.0-910b-openeuler24.03-py3.11` 与 `-py3.12`；PyPI 有 `torch_npu-2.10.0.post7-*manylinux_2_28_aarch64.whl`；osinfra 有 `triton_ascend-3.6.0-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl`（`TRITON_ASCEND_WHL` 按此逐字写）。
- 本机两台昇腾机 `uname -m` 都是 **x86_64**，而门禁镜像是 **aarch64**：改完配方需要 aarch64 构建机（或 buildx+qemu，15GB 镜像不划算），且推 `swr cn-north-4` 要登录凭据（匿名只能读 manifest，blob 返 401）。
- 分支选择上优先「各分支改自己的 `.gitcode/workflows`」而不是在一个 workflow 里做 `if` 分支判断：门禁跑的是**目标分支**的 pipeline 文件，天然按分支隔离。

## 10. 把 CI 门禁镜像换到 26.2.0 商发：4 步与逐行改动（2026-11-12 复验）

**顺序是硬约束**：改 `ci/` 配方 → aarch64 建镜像 → 进镜像自证+冒烟 → push → **最后**切 workflow 的 4 处 `image:`。反过来（先切 image）= 目标分支所有 PR 立刻全红。

### 10.1 步骤 1：配方（`ci/` 三文件）

- `ci/Dockerfile:9` `BASE_IMAGE_VERSION` `9.1.0`→`9.2.0`；`:21` `TORCH_NPU_VERSION` `2.10.0`→`2.10.0.post7`；`:23` `TRITON_ASCEND_VERSION` `3.2.2`→`3.6.0`
- `ci/build.sh:9/:13/:15` 同上三值；`:16` `TRITON_ASCEND_WHL` → `triton_ascend-3.6.0-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl`
- `ci/CI_GUID.md:9,25` 示例 tag
- **现成 PR**：`Ascend/MindSpeed-Ops` **!261**（`open`，base `26.2.0`，head `ci/2620-pairing-recipe@63070b3`，只动 ci/ 三文件 +16/−16）。该补丁对今日 master / 26.2.0 **均 `git apply --check` 通过**，可直接复用，别重写。

### 10.2 步骤 2：构建（必须 aarch64 机器；.188/.190 是 x86_64）

```bash
cd MindSpeed-Ops/ci
bash build.sh -t 910b -o openeuler24.03 \
  --python-version 3.12 --base-image-version 9.2.0 \
  --torch-version 2.10.0 --torch-npu-version 2.10.0.post7 \
  --triton-ascend-version 3.6.0 \
  --triton-ascend-whl triton_ascend-3.6.0-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl \
  -i swr.cn-north-4.myhuaweicloud.com/mindspeed/pr-ops:<自证 tag>
```

- **不能直接 `docker build -f ci/Dockerfile`**：`:26` 的 `COPY configure_repo.sh` 由 `build.sh:171` 把 `configure_*_repo.sh` 现拷出来，绕过 build.sh 必失败。
- tag 用自证格式（照 `docker/image_build.sh:187`）：`{分支}-cann{CANN}-torch_npu{PTA}-{chip}-{os}-py{PY}-{arch}`。别再用 `-0820` 那种日期段——线上 tag 连 CANN/TA 都不含，事后无法反查栈版本。

### 10.3 步骤 3：进镜像自证（不过就别推）

```bash
cat /usr/local/Ascend/ascend-toolkit/version.cfg | head
ls -l /usr/local/Ascend/nnal/atb/set_env.sh    # ut.sh:18 无条件 source，缺了整片 UT 直接 exit
python -c "import sys,torch,torch_npu,importlib.metadata as m;print(sys.version.split()[0],torch.__version__,torch_npu.__version__,m.version('triton-ascend'),m.version('triton'),m.version('numpy'))"
```

再按 `ci/MindSpeed_Ops_ut.sh` 同口径跑：`MINDSPEED_BUILD_CATLASS=1` + `pip install -e . --no-deps --no-build-isolation` + `pytest tests/unit_tests/catlass` + `python ci/access_control_test.py --rank 1..4`。

### 10.4 步骤 4：只切目标分支的 4 处 `image:`

- master：L198 / L218 / L238 / L258
- 26.2.0：L173 / L193 / L213 / L233
- **别先切 master**：master 的 `requirements.txt` 仍是 `triton-ascend==3.2.2`，跑了 3.6.0 镜像等于把门禁栈换错。

### 10.5 关键事实（本轮实测）

- 两分支 `ci/` **blob 完全相同**（`Dockerfile=df5b771e`、`build.sh=e5ad3151`、`CI_GUID.md=273d1c10`）；`70c1479`（MR !237）只升了 `docker/`，`ci/` 落后**一整个配套**。
- 门禁镜像 tag 是 `py3.11`，而 `ci/Dockerfile:11` 默认 `py3.12` ⇒ 现镜像**不是**按仓内默认值构建的；换配方时必须显式对齐 py 版本，否则继续"配方一套、镜像另一套"。
- 可得性实测：`ascendhub/cann:9.2.0-910b-openeuler24.03-py3.11` 与 `-py3.12` manifest 均 200 且 `amd64+arm64`；`triton_ascend-3.6.0` cp311/cp312 aarch64 wheel 均 200（322.9 MB）；`torch_npu 2.10.0.post7` cp311/cp312 aarch64 在 PyPI。**只有 `cn-south-1` 匿名可读**（`cn-north-4/1/east-3` 取 token 返 401）。
- 「商发」= 裸 `9.2.0`；该版本线只有 `beta.1/beta.2`，无 RC。`26.2.0` 是产品火车号，不是 CANN 版本。

### 10.6 坑

- 仓内**无** `docker login/push/buildx`，唯一 workflow 是 `pr-pipeline`；镜像人工建、人工推，凭据在仓外。
- `ci/Dockerfile:93` 用一条命令同装 `torch`+`torch_npu`、无重试；`docker/Dockerfile:117-146` 是**分步 + `while … && break` 重试 + 先 `+cpu` 索引**。换基镜像装挂时照 docker/ 改。
- 本地 clone 是浅克隆且落后：判"今天"必须 `git ls-remote`（2026-11-12：`master=ac671f24`、`26.2.0=19a603c0`）。
- PS 5.1 `>` 重定向写 UTF-16，`git apply` 报 `error: No valid patches in input` → 用 `cmd /c "git … > x.patch"`。

## 11. 维护记录

- **2026-11-09 建立**：在 `root@192.168.13.190`（openEuler 22.03 LTS-SP4，8×Ascend910/16 die）上，对 `Ascend/MindSpeed-Ops` 26.2.0 @ `7ccec74` 跑通 UT（24 文件）+ ATK（27 算子）全流程；坑 1/2/3/4/5/6 均为当次实测。
- **2026-11-12 增补 §10**：按今日远端（`master=ac671f24`、`26.2.0=19a603c0`）复验 ci/ 与 docker/ 的漂移、SWR cn-south-1 的 9.2.0 镜像与 3.6.0 wheel 可得性、PR !261 状态；§9 的可得性三查以 §10.5 为准。

## 12. A5（Ascend950DT / arch35）冒烟与换机镜像

A5 与 A3 的差别不在"换台机器"，而在**芯片架构换了**：A5 = `Ascend950DT`（`soc_version=260`，`get_device_name()` 返回 `Ascend950DT_9582`），仓里用 `is_arch35()` 走另一套 kernel 分支。照 A3 的口径直接套会得到一堆"看着是回归、其实是平台不支持"的结论。

### 12.1 先确认是 A5（两条命令）

```bash
npu-smi info -t board -i 0 | grep -E 'Chip Name|Chip Version|Firmware'   # Ascend950DT / V120
python -c "import torch,torch_npu;print(torch.npu.device_count(),torch.npu.get_soc_version(),torch_npu.npu.get_device_name())"
# 期望 8 260 Ascend950DT_9582
```

A5 的实测规格（177.8.21.1，2026-11-13）：openEuler 24.03 LTS-SP3 **aarch64**、192 核 / 2261GiB、8×950DT（98304MB/卡，**一卡一 die**，所以 `ASCEND_RT_VISIBLE_DEVICES` 就是 0..7）、`npu-smi 25.1.rc3`。

### 12.2 配套版本：认 26.2.0 + 950，而不是 master

- 26.2.0 的 `docker/OVERVIEW.zh.md` 里**明确有 950 行**：`26.2.0-cann9.2.0-torch_npu2.10.0.post7-950-openeuler24.03-py3.12`；`requirements.txt` 钉 `triton-ascend==3.6.0`。
- **master 的 `requirements.txt` 仍是 `triton-ascend==3.2.2`**（早于 950 支持），A5 上按 master 的 pin 装会踩栈不匹配。要跑 master 就得显式覆盖成 3.6.x，并在报告里说明偏离了 pin。
- 最省事的"权威反查"：本机跑着 A5 容器时直接问容器，比自己猜版本快得多：
  ```bash
  docker exec <容器> python -c "import sys,torch,torch_npu,importlib.metadata as m;print(sys.version.split()[0],torch.__version__,torch_npu.__version__,m.version('triton-ascend'),torch.npu.get_soc_version())"
  ```

### 12.3 CANN 入口（A5 的路径与 A3 不同）

```bash
export ASCEND_TOOLKIT_HOME=/home/cann/920_b111/ascend-toolkit/latest    # -> /home/cann/920_b111/cann
. /home/cann/920_b111/ascend-toolkit/set_env.sh                          # asc_toolkit_home 必须预设
. /home/cann/920_b111/nnal/atb/set_env.sh
```

- `/home/cann/920_b111/set_env.sh` **不存在**；`cann-9.2.0/` 与 `ascend-toolkit/` 是两个并存的目录树，`ascend-toolkit/latest` 是指向 `cann` 的软链。
- 不预设 `ASCEND_TOOLKIT_HOME` 直接 source，`ASCEND_HOME_PATH` 会是**空的**，随后 `import torch_npu` 报 `ImportError: libhccl.so: cannot open shared object file`。验收只看 `echo $ASCEND_HOME_PATH` 有值 + `torch.npu.is_available()` 为 True。

### 12.4 arch35 门控：判读时先分"平台不支持"和"真失败"

`mindspeed_ops/utils.py` 的 `is_arch35()` 判 `"Ascend910_95" in device_name or "Ascend950" in device_name`。26.2.0 里**部分算子没有 arch35 实现**，在 A5 上走 `raise NotImplementedError("this op is not supported in this platform")`：

| 层 | 实测结果（26.2.0 @ 19a603c，A5） |
|---|---|
| UT collect | **ok=21 / err=3 / 629 用例**；err 的是 `test_mhc_post`、`test_mhc_pre_bmm`、`test_mhc_pre_only`（import 期即报错，不是 skip） |
| ATK | 静态预判约 8 个算子被同一门控拦：`chunk_kda_fwd_intra`、`chunk_local_cumsum`、`chunk_scaled_dot_kkt`、`l2norm`、`mhc_pre_bmm`、`mhc_pre_only`、`recompute_w_u_fwd`、`wy_fast`；其余走 arch35 或通用实现 |

- 快速分类（不占显存，几秒钟一个文件）：`pytest -q -p no:cacheprovider --collect-only <file>`。
- 报告的结论必须把 `NotImplementedError: this op is not supported in this platform` 单列成"平台不支持"，**不要并进失败数**；否则 A5 上的"全绿"永远不可达。
- 顺带一个仓内测试卫生问题：这些被门控的算子在 UT 里是 module-level import，于是 collect 阶段就 error，而不是 skip（对比 `catlass` 用了 `skipif not hasattr(torch.ops.mindspeed_ops, ...)` 的写法）。

### 12.5 换机镜像：别从零建，先找官方 950 底座

A5 机器上通常**已经有人拉过官方 950 配套镜像**，直接当底座，增量只加"冒烟需要但底座没有的"：

```bash
docker images | grep -iE 'mindspeed-ops.*950'
# swr.cn-south-1.myhuaweicloud.com/ascendhub/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-950-openeuler24.03-py3.12   17.2GB
# swr.cn-southwest-2.myhuaweicloud.com/atlas-release/mindspeed-ops:26.2.0-...-950-ubuntu22.04-py3.12                        16.7GB
```

底座实测（2026-11-13）：openEuler 24.03 LTS-SP4 / py3.12.15 / CANN 9.2.0 / torch 2.10.0+cpu / post7 / TA 3.6.0 / numpy 1.26.4 / pytest 8.4.2 / **`mindspeed_ops 26.2.0` 已装** / 仓在 `/workspace/MindSpeed-Ops`；**缺 ATK，且无 clang**。

**派生镜像要做的四件事**（`mindspeed-ops-smoke:2620-950`，17.5GB）：

1. 装 ATK：`pip install atk-26.9.24-cp312-cp312-linux_aarch64.whl` + `kombu==5.6.2 amqp==5.4.1 billiard==4.3.1`。
2. **仓钉 commit 并删掉底座里的旧 `.so`**：底座仓可能是几天前的 commit（实测 `451e094`，而远端 26.2.0 已是 `19a603c`），`.so` 由旧源码编出，源码/二进制不一致会污染 aclnn/atb/catlass 类用例。`git fetch && git reset --hard <commit> && rm -f mindspeed_ops/mindspeed_ops_C*.so`。
3. 把冒烟脚本拷进镜像 `/opt/a5smoke/`（见 §12.6）。
4. `docker save` 出 tar + `.sha256`；顺手 `pigz -p32` 出一份 gz（17.6GB → 6.09GB，换机不走共享盘时用）。

**导出/交接用共享盘**：A5 批次的机器共用 `172.27.1.1:/Share`（`/mnt/share`，350T），把 tar 放那里，目标机 `docker load -i` 即可，省一次 17GB 传输。目标机不共用 NFS 时才走 gz + scp。

**验证导出件**（比 `sha256sum` 更硬的证据）：同机上 `docker load -i <tar>` 回灌，镜像 ID 不变（实测 8s、`Loaded image: ...`、`IMAGE_ID_UNCHANGED_OK`），说明 tar 29 层完整可载。

### 12.6 容器内跑冒烟的两个必要动作

1. **必须 source 一个 `activate.sh` 设 `PYTHONPATH=$REPO`**。底座的 `PYTHONPATH` 只有 CANN 路径，缺了它 UT 里 `from tests.utils import ...` 直接失败——实测 24 个文件里 **22 个 collect error**，极易误判成"镜像坏了"。
2. **NPU 透传**：本机 docker 18.09 **没有 `ascend` runtime**（`docker run --runtime=ascend` → `Unknown runtime specified ascend`）。现有容器两种写法都能用：
   - `--privileged --network host`；或
   - 逐个 `--device /dev/davinci0..7 --device /dev/davinci_manager --device /dev/devmm_svm --device /dev/hisi_hdc`
   另外必须挂宿主机驱动（驱动不在镜像里）：`-v /usr/local/Ascend/driver:/usr/local/Ascend/driver -v /usr/local/dcmi:/usr/local/dcmi -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi -v /etc/ascend_install.info:/etc/ascend_install.info -v /etc/hccn.conf:/etc/hccn.conf`。

### 12.7 建环境时的三个坑（这轮全踩了）

1. **脚本没上传就 source → pip 装进了 base conda，污染共享 base**。`pip install` 前的 `. $WD/activate.sh` 一旦因文件不存在失败，后面的 `pip` 会落到 `/root/miniconda3`（实测把 `atk` 装进去、`kombu 5.7.0→5.6.2`、`amqp 5.4.2→5.4.1`）。修法：`pip uninstall -y atk` + `pip install kombu==5.7.0 amqp==5.4.2` 复原，并把"脚本上传"做成独立一步（sftp put 后再执行）。
2. **`conda create` 卡 repodata**：`Collecting package metadata (repodata.json)` 十几分钟不动（conda-forge + defaults 双源）。修法：`/root/miniconda3/bin/python -m venv <dir>`，直接用 base 的 3.12，cp312 wheel 全兼容。
3. **`docker save` 前先看 docker 根盘**：该机 `/var/lib/docker` 在 `/` 上，只剩 27G；`save` 目标是 `/mnt/share`（共享盘）而不是 `/data`，否则会和镜像层抢空间。

### 12.8 共享机排队纪律（A5 上很常见）

A5 常被多人共占，实测出现过 8 卡全被同一个人容器里的 `VLLMWorker_TP` 占满（**每卡 84.7G/96G 驻留、util 0%** —— 服务在等请求，不是空闲）。判"能不能跑"只看 `npu-smi info -t proc-mem -i <i>` 有没有 `Process id`，不看 util。

- 不要 `pkill`/`docker stop` 别人的任务；要么等，要么换机器（同批 `177.2.25.1` / `177.2.26.1` / `177.11.25.1` / `177.11.26.1` 同一张 A5 隧道可达）。
- 要等就挂一个"空卡即开跑"的驱动（`WAIT_FREE_SEC` + 每 60s 检查），但**记得在切去做别的事时把它停掉**，否则它会在任意时刻抢卡、和你的其他验证互相干扰。

## 12.9 26.2.0 在 A5（950/arch35）的判读基线与四个操作坑

### 12.9 26.2.0 在 950 上的基线（2026-11-13 在 177.11.27.1 全量实跑，可直接对照）

配套：CANN 9.2.0 / py3.12.15 / torch 2.10.0+cpu / post7 / TA 3.6.0 / numpy 1.26.4 / ATK 26.9.24；仓 = 26.2.0 @ `19a603c`。UT 约 12 min、ATK 27 算子约 26 min（总计 36 min）。

**UT（`tests/unit_tests/triton`）**：862 用例 → passed 531 / failed 106 / skipped 225，另 3 个文件 collect 即 ERROR。
- 96 个失败 = 平台门控（`l2norm` 76、`chunk_gated_delta_rule` 20，报 `this op is not supported in this platform`）。
- 10 个失败 = 真缺陷：`kda_fwd_intra` 3、`chunk_gated_delta_rule_fwd_h` 4、`wy_fast` 3。

**ATK（27 算子）**：Pass 18 / Failed 9；1122 用例通过 879（78.3%）。失败里 225 用例是「根本没执行」（门控），15 例是 wy_fast 的 bf16 编译/调优失败，只有 **3 例是真·精度超阈值**（bwd_dhu `[4,1024,32,128]` fp32 max_abs 6.2e-5/max_rel 4.4e-5；rmsnormgated `[4,8192,2048]` fp32 max_abs 6.7e-5/7.7e-5、max_rel 2.99e-5）。

**三处可直接开 issue 的真缺陷（都能定位到行）**
1. `arch35/triton/gdn/cumsum.py:426`（`chunk_local_cumsum_scalar`）→ `error: ub overflow, requires 33554432 bits while 2031616 bits available`，触发 `B1-T2048-H32`。**会连坐**：`test_chunk_kda_fwd_intra` 的 3 个失败其实是它——该算子在 arch35 是门控的，但那 3 个用例在 `_make_inputs` 里先调了这个 cumsum。
2. `arch35/triton/gdn/chunk_gated_delta_rule_fwd_h.py:680` → `error: operand #1 does not dominate this use` + `verification failed after sinking copy chain` + `Failed to run BiShengHIR pipeline`，触发 `B1-T1024/T32768, H32 D128, gk=True`。
3. `arch35/triton/gdn/prepare_wy_repr_bwd.py:225` → `RuntimeError: No valid triton configs. NoneType: None`（autotuner.py:2599），只挂 bf16；底层异常被吞，建议顺手修异常传递。

**归因两条硬结论（别把锅扣错）**
- 换 TA `3.6.0.post2` 复跑上面 3 个文件：`3/4/3` 失败数**完全一致** ⇒ 不是 TA 补丁版本问题。
- 用 master 同配套交叉：`l2norm` 94/94、`chunk_kda_fwd_intra` 3/3、`mhc_post` 48/48 都过 ⇒ 这些是**26.2.0 没带 arch35 实现**，不是 950 硬件不支持；而 `fwd_h`、`wy_fast` 在 master 上也复现 ⇒ 两分支共有缺陷。
- `is_arch35()` 本身判定正确（恒 True，`Ascend950DT_9582`），不要往门控函数上怀疑。

**`recompute_w_u_fwd` 是「半支持」**：`api/triton/gdn_recompute_w_u_fwd.py:23` 在 arch35 只在 `gk is not None` 时抛 `NotImplementedError("gk is not supported on arch35 ...")`，其余走 arch35 实现。所以 UT 6 passed/4 skipped、ATK 5 例全挂——差别只在 gk。

### 12.10 跑这套冒烟的四个操作坑（本轮实踩）

1. **`--rm` 会把 ATK 的 xlsx 报告一起删掉**：报告写在容器内 `<repo>/tests/atk_tests/triton/<op>/atk_output/.../report/*.xlsx`，只有 `/opt/a5smoke/work` 是挂载出来的。跑完（或 `docker run` 结束）再看报告就没了。⇒ 要么别用 `--rm`，要么在收尾前把 `atk_output/` 拷到挂载目录。
   替代判读：**逐算子表格就在日志里**，`sed 's/\x1b\[[0-9;]*m//g' atk_<op>.log | grep -E '^\| *cpu_0 *\|'` 能拿到「总用例/执行成功/执行失败/通过/通过率/精度是否达标」。
2. **`ls test_*.py` 会漏两个目录型用例**：26.2.0 的 `tests/unit_tests/triton/` 下 `test_causal_conv1d/`、`test_rmsnormgated/` 是**目录**（内含 `test_forward.py` 等），必须 `pytest <dir>` 单独跑（实测补上 3 passed/115 skipped 与 88 passed/27 skipped）。
3. **`bash -lc` 里别嵌套带引号的 `git log --format`**：在 paramiko `bash -lc` 的双引号转义里会把格式串打断，报 `fatal: invalid --pretty format`。要打 commit 就单独一行、用单引号。
4. **UT/ATK 并发时给 ATK 留卡**：ATK 固定用 `--devices 0`，UT 分片跑在 1..7 卡上互不影响；但 `docker run --rm` 的容器一退出，还在里面 `docker exec` 跑着的补充用例会被一起杀掉（本轮 `test_rmsnormgated/` 就死在 62%），补跑要另起容器。

## 12.11 跑 26.2.0 商发 = 直接用现成镜像（位置 / 校验和 / 三条命令）

**用户口径（2026-11-13）**：以后说「跑 26.2.0 商发冒烟」= **直接用这张镜像**，不要重新铺环境、不要再建 venv/conda。这条是唯一入口。

### 现成镜像

| 项 | 值 |
|---|---|
| tag | `mindspeed-ops-smoke:2620-950`（镜像 ID `6055738fecd8`，17.5GB） |
| 存放（共享 NFS，同批 A5 均挂 `/mnt/share`） | `/mnt/share/a5_smoke_image/` |
| 未压缩导出 | `mindspeed-ops-smoke_2620-950.tar`，17,603,497,984 B，`sha256 ce21dad32e1f3a66767d695b6ec3d5b524cf427ed663538b3dc912feb47a6c91` |
| 压缩导出 | `mindspeed-ops-smoke_2620-950.tar.gz`，6,092,786,431 B，`sha256 c05f4948f7fcd5ae573ee12730e79e5dd9c22d5156cbf2e9e63a54ab18037eda` |
| 自建小包 | `/mnt/share/a5_smoke_image/rebuild/`（Dockerfile + smoke 脚本 + `atk-26.9.24-cp312-cp312-linux_aarch64.whl`） |
| 历史报告 | `/mnt/share/a5_smoke_image/reports/20261113-2620-a5/`（UT/ATK 全量日志 + 报告 md） |
| 底座 | `swr.cn-south-1.myhuaweicloud.com/ascendhub/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-950-openeuler24.03-py3.12` |

**重要**：这是 **aarch64 / Ascend950DT** 专用镜像，A3（x86_64/910B）不能用。

内容 = 底座(官方 950 配套) + ATK 26.9.24（钉 kombu 5.6.2 / amqp 5.4.1 / billiard 4.3.1）+ 仓钉 `26.2.0 @ 19a603c`（已删底座旧 `.so`，避免源码/二进制不一致）+ `/opt/a5smoke/` 脚本。

### 三条命令（已在 177.11.27.1 实测）

```bash
docker load -i /mnt/share/a5_smoke_image/mindspeed-ops-smoke_2620-950.tar   # 实测 2m27s
bash /mnt/share/a5_smoke_image/rebuild/smoke/verify_image.sh                # 只验栈不占卡：期望 npu True/8 卡，UT collect 21/3
docker run --rm -it --privileged --network host \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
  -v /etc/ascend_install.info:/etc/ascend_install.info \
  -v /etc/hccn.conf:/etc/hccn.conf \
  -v /root/a5smoke_run:/opt/a5smoke/work \
  mindspeed-ops-smoke:2620-950 bash /opt/a5smoke/run_smoke.sh
```

- 卡被占：加 `-e WAIT_FREE_SEC=3600`（每 60s 检查，8 卡全无进程才开跑）。
- 无 `ascend` docker runtime（本批 A5 都是 docker 18.09）：用 `--privileged`，或逐个 `--device /dev/davinci0..7 --device /dev/davinci_manager --device /dev/devmm_svm --device /dev/hisi_hdc`。
- **前置检查**：`/var/lib/docker` 所在的 `/` 至少留 20GB（177.8.21.1 只剩 19G，装不下；177.11.27.1 有 1TB，首选）。
- 跑完判读直接用 §12.9 的基线对照；**`--rm` 会让 ATK 的 xlsx 报告一起消失**，要留报告就别用 `--rm` 或先拷出（坑见 §12.10）。

### 什么时候才需要重建镜像

只有这三种情况：① 底座镜像在目标机上没有且拉不到；② 要换 ATK 版本；③ 要把仓换到别的 commit（如 master）。重建用 `rebuild/Dockerfile`，`docker build --network host -t <新 tag> .`；底座 17.2GB 是本地镜像层，重建只加薄薄几层，几分钟完成。
