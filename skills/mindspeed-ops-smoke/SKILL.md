---
name: mindspeed-ops-smoke
description: MindSpeed-Ops 冒烟：按版本矩阵建环境、UT + ATK 精度双读判绿。适用于"跑 26.2.0 冒烟 / ATK 精度怎么判 / 冒烟全绿了吗 / CI 镜像配套对不对"。
---

# MindSpeed-Ops 商发配套冒烟（UT + ATK）

**本 skill 只讲「怎么把 26.2.0 商发配套的冒烟跑起来并判读」。** 环境铺设（CANN / conda / torch 栈）细节一律在 `ascend-*` 子 skill；本文件只写这一套冒烟实测跑通的路径、坑与判据。

## 何时调用

**加载本 skill 当：**
- 用户说"跑一遍 26.2.0 的商发配套冒烟""看看 MindSpeed-Ops 最新代码有没有问题""冒烟是不是全绿"。
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

## 10. 维护记录

- **2026-11-09 建立**：在 `root@192.168.13.190`（openEuler 22.03 LTS-SP4，8×Ascend910/16 die）上，对 `Ascend/MindSpeed-Ops` 26.2.0 @ `7ccec74` 跑通 UT（24 文件）+ ATK（27 算子）全流程；坑 1/2/3/4/5/6 均为当次实测。
