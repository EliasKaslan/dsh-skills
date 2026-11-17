---
name: "mindspeed-ops-smoke"
description: "MindSpeed-Ops接口兼容、wheel验收及UT/ATK冒烟（含A3双机26.2.0配套）。适用于\"跑Ops冒烟 / ATK精度怎么判 / UT全绿了吗 / 跨仓接口兼容吗\"。"
whenToUse: "处理MindSpeed-Ops接口兼容、wheel验收及UT和ATK冒烟时加载；模型看不到本节，触发以description为准。"
---

# MindSpeed Ops工程验证

## 何时调用

**触发**：跑Ops冒烟 / ATK精度怎么判 / UT全绿了吗 / wheel能用吗 / 跨仓接口兼容吗。

**转交**：基础CANN环境故障见 [ascend-cann-env](../ascend-cann-env/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

固定Ops与消费仓完整SHA、目标SoC/架构、CANN/torch_npu/Triton、Python ABI和验证任务。沿用用户选择的发布分支或实验栈，不因旧案例默认master、26.2.0、A3/A5或某个镜像。基础环境与资源准入用现有ascend-cann-env/ascend-server-layout。

按任务读取：[接口与增量](references/interfaces.md)、[wheel和构建](references/build.md)、[UT/ATK和CI](references/smoke.md)。三个能力互相提供证据但不能代替：源码能import不证明wheel能用，wheel能安装不证明目标算子执行，CI绿不证明发布配套上的精度。

包名/版本串、镜像tag、SOC_VERSION和HAS标志都不是源码/产物来源的充分证据。记录模块__file__、metadata、源码/二进制hash、实际加载库、目标分支与设备派发。防止旧wheel遮住源码或源码目录遮住待验wheel。

静态检查、导入、编译、执行、数值、性能分别给结论；未知接口/缺依赖/目标平台未实现/资源错误/有效数值差异分开登记。没有NPU或构建权限时继续完成源码/包结构核对和最小复现准备，明确未执行范围，不将历史PASS继承到新SHA。

来源：DSH mindspeed-ops-interface-compat-audit、mindspeed-ops-smoke、mindspeed-ops-whl-build，2026-11-16整理。旧固定机器、邮箱、自动发信、版本组合及门禁状态未继承；旧“半覆盖Triton版本对比”流程剔除。

## A3 双机跑 26.2.0 商发配套冒烟

**机台选择（2026-11-17 实测）**：两台 A3 芯片同档（soc 253 / 16 die / 65536MB HBM·die⁻¹ / PCI 19E5:D803），NPU 侧常全空闲，**冒烟优先 190**：
- 190：fp16 matmul **303.2 TFLOPS**（8192³×200）、HBM copy 1182 GB/s；CPU load ~21/64 线程；`/home` 4.1T 可用；SFTP/长命令正常。
- 188：同脚本 fp16 **291.7 TFLOPS**、copy 1133 GB/s（低约 4%）；常驻他人 vLLM E2E，load 277/256 线程；`/` 仅剩 177G；**sshd 拒绝客户端写入**（见坑）。
- 换机复核用同一脚本 `bench.py`（fp16/bf16 matmul 8192³×200 + 512MB HBM copy/add），不要凭 `npu-smi` 型号名推断性能。

**环境入口（190）**：CANN 9.2.0 在 `/mnt/share/cann/cann-9.2.0/cann-9.2.0/set_env.sh`（**`/usr/local/Ascend` 只有 driver**）；python env `/home/vllm/x00886548/smoke2620/envs/py310`；激活脚本先 `set +u` 再 source CANN 与 `nnal/atb/set_env.sh`。`/home/vllm/x00886548` 是指向 `/home/x00886548` 的软链，conda 里列出的两条 env 实为同一目录。

**代码锁定**：不要改动现有主 worktree；`git worktree add --detach <ws>/ops <26.2.0 tip>`。tip 用 `git fetch origin 26.2.0` 后的 `FETCH_HEAD` 并记录 SHA（26.2.0 常有只有 docs 的提交，仍须记录，否则结果不可追溯）。

**UT（triton）**：`tests/unit_tests/triton/test_*.py`，**必须在 triton 目录内** `pytest -q -p no:cacheprovider -rf`。12 分片绑 die 0..11，每片 `ASCEND_RT_VISIBLE_DEVICES=<die>` + 独立 `TRITON_CACHE_DIR`，单文件 `timeout 10800`；汇总看各片末行 `N passed`。

**ATK 精度（triton 27 算子）**：单实例、独占一个 die（与 UT 并行不冲突）。`atk case -f <op>.yaml -p generate_<op>.py` → `atk node --backend triton --devices 0 node --backend cpu --devices 0 task -c result/<op>/json/all_<op>.json --task accuracy -p triton_<op>.py`；**参考实现必须 `--backend cpu`**（npu 当标杆会“执行全成功但 acc=Failed”）。每算子前后 `pkill -9 -f "<env>/bin/atk"` 清残留，`ss -lntp | grep -E ':(8881|9090) '` 必须为空（8881 硬编码在 `atk/tasks/sqlite_web_process.*.so`，无 CLI/env 可改 → 全局只能一个 ATK）。超时给 `1800`（case）/`7200`（task）。

**编译型覆盖（aclnn/catlass，值得做）**：系统无 cmake → `pip install cmake`；独立 clone + `python -m venv --system-site-packages`，再
`SOC_VERSION=ascend910_93 MINDSPEED_BUILD_CATLASS=1 MAX_JOBS=32 pip install -e . --no-build-isolation --no-deps`（**实测 71 秒**）。自检必须两个都 True：`hasattr(torch.ops.mindspeed_ops,'npu_add_rms_norm_bias')`、`…'catlass_chunk_loss'`。编译后 aclnn+catlass 由 skip 全转实跑（155 例）。`--no-build-isolation` 时 PATH 必须含该 venv 的 bin，否则找不到 pip 装的 cmake。

**非 triton 算子的 ATK 口径**：第一个 node 必须换 `--backend npu`——`atk node --backend npu --devices 0 node --backend cpu --devices 0 task -c result/<op>/json/all_<op>.json --task accuracy -p function_<op>.py`。aclnn/atb 的 yaml 里 `triton_name` 为 null，用 `--backend triton` 会 0/N 全失败（`Error: Triton api name is not given.` + `run opp task failed!`）。

**atb 的固定失败**：`/mnt/share/cann/cann-9.2.0/nnal/atb/latest/{include,lib}` 为空（只有 install.sh/whl）→ 编译报 `atb/types.h: No such file or directory`，ATK 报 `ImportError: …npu_matmul_add_fp32.so: cannot open shared object file` + `matmul_add_fp32 run error!`；UT 表现为 **7 个 FAILED 而非 SKIP**（用例 skip 判据只在 RuntimeError 含 "cann-nnal" 时触发）。这是环境与判据问题，不是算子缺陷；同目录 fp16/不走 ATB JIT 的路径照常全绿（8/8 Pass）。tilelang 需独立 whl，未装即 skip。

**回归基线（190 / 26.2.0@b1ef3ad）**：UT 593 passed / 0 failed / 63 skipped；ATK 27/27 算子 Pass、1122/1122 任务；aclnn+catlass 155 passed。结果显著偏离时先查 env 与 die 占用，再判代码。

**坑**：
- Windows PowerShell 5.1 会把带空格的远端命令拆散（只发第一段 → `SyntaxError` / `~: 未找到命令`）→ 用「本地写 `.sh` → SFTP → `bash`」或清单式 `put`/`run` 执行器。
- 188 的 sshd 拒绝客户端→服务端写入：sftp put、stdin 上传、>1.5KB 的 inline 命令均 `ConnectionResetError 10054` / `Server connection dropped`；只能短单行，落文件用 800 字符一段 base64 追加后 `base64 -d`。
- pytest 未 source CANN 表现为 **2 个 collection errors**（torch_npu 导入失败），不是用例失败。
- `nnal/atb/set_env.sh` 引用未绑定的 `ZSH_VERSION`，外层 `set -u` 会静默中断（空日志 + rc=1）。

## CI 门禁镜像配套与可拉性核查（改 container.image 前后）

门禁实际生效的 CANN / torch_npu / triton-ascend / Python **完全由 `container.image` 决定**：`ci/MindSpeed_Ops_ut.sh` 用 `pip install -e . --no-deps`，分支 `requirements.txt` 的 pin 在 CI 里不生效。所以「配方改了」不等于「门禁栈改了」。

**升级配套时要逐项对齐的六处**（只改一处 = 门禁与声明不符）：

1. `.gitcode/workflows/pr-pipeline-mindspeed-ops.yml` 的 `UT_MindSpeed_1~4` 四处 `container.image`
2. `ci/Dockerfile` 的 `BASE_IMAGE_VERSION` / `TORCH_NPU_VERSION` / `TRITON_ASCEND_VERSION`
3. `ci/build.sh` 默认值（含 `TRITON_ASCEND_WHL`；该参数当前未被 Dockerfile 消费，但留旧值会误导）
4. `requirements.txt` 与 `pyproject.toml` 的 `triton-ascend==` pin
5. `docker/Dockerfile` 发布镜像配方（与 ci/ 是两套，可分批）
6. `docs/*/install_guide.md`、`docker/OVERVIEW*`、`supported_tags.md` 的版本表

**验证镜像真能拉（SWR 匿名 registry API）**：

```python
# 1) 直接取 manifest 会 401，从 WWW-Authenticate 拿 realm
GET https://<host>/v2/<repo>/manifests/<tag>
# 2) 换匿名 token
GET <realm>?service=dockyard&scope=repository:<repo>:pull      -> {"token": ...}
# 3) 带 Bearer 重取 manifest / 列全部 tag
GET https://<host>/v2/<repo>/manifests/<tag>   (Accept: manifest.list.v2+json, oci.image.index.v1+json)
GET https://<host>/v2/<repo>/tags/list
```

判读要点：
- **必须做对照**：同一个 repo 里拿一个已知存在的旧 tag 测 200，再用新 tag 测 404，才能断定新镜像缺失；私有 repo 对匿名一律 404（不泄露存在性），只测一个 tag 会误判。
- manifest list 的 `manifests[].platform.architecture` 判定有无 `arm64`（门禁 runner 是 aarch64；x86_64 构建的镜像用不了）。
- 官方社区镜像在 `swr.cn-south-1.myhuaweicloud.com/ascendhub/<产品>`，公开可匿名拉；同名 tag 按 `版本-cann-torch_npu-芯片-系统-py-架构` 组织，芯片段必须与 runner 实际硬件一致（`910b` / `a3` / `950` 各段都有）。
- 官方发布镜像可直接当 UT 容器前的四项检查（本仓 26.2.0 的 910b py3.12 镜像实测满足前三项）：`User=root`、history 里有 gcc/gcc-c++/make/cmake/ninja-build、`/usr/local/Ascend/nnal/atb/set_env.sh` 存在、WORKDIR 里已有代码 checkout（可能影响 checkout 步骤落入非空目录）。仍未验证的是 `torch.npu.is_available()` 与 CATLASS UT 实跑。
- 用官方发布镜像跑 PR UT 还要确认：镜像内已装的 `mindspeed_ops` 会被 `pip install -e .` 覆盖，否则可能跑发布版代码得到假绿。

**回滚**：`container.image` 退回上一个可用 tag 的同时，把配方与 pin 一起回退，三者保持一致；只退其一都会留下静默不一致。
