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

- 190 的环境入口（CANN 9.2.0 路径、py310 env、激活顺序、软链）见 references/a3-2620-env.md。

**代码锁定**：不要改动现有主 worktree；`git worktree add --detach <ws>/ops <26.2.0 tip>`。tip 用 `git fetch origin 26.2.0` 后的 `FETCH_HEAD` 并记录 SHA（26.2.0 常有只有 docs 的提交，仍须记录，否则结果不可追溯）。

**UT（triton）**：`tests/unit_tests/triton/test_*.py`，**必须在 triton 目录内** `pytest -q -p no:cacheprovider -rf`。12 分片绑 die 0..11，每片 `ASCEND_RT_VISIBLE_DEVICES=<die>` + 独立 `TRITON_CACHE_DIR`，单文件 `timeout 10800`；汇总看各片末行 `N passed`。

- ATK 27 算子精度的完整命令序列、单实例约束、pkill/端口清理与超时阈值见 references/a3-2620-atk.md。

- 编译型覆盖（aclnn/catlass）的安装与两个自检判据命令见 references/a3-2620-env.md。

- 非 triton 算子（aclnn/atb）的 ATK 口径命令与报错原文见 references/a3-2620-atk.md。

**atb 的固定失败**：`/mnt/share/cann/cann-9.2.0/nnal/atb/latest/{include,lib}` 为空（只有 install.sh/whl）→ 编译报 `atb/types.h: No such file or directory`，ATK 报 `ImportError: …npu_matmul_add_fp32.so: cannot open shared object file` + `matmul_add_fp32 run error!`；UT 表现为 **7 个 FAILED 而非 SKIP**（用例 skip 判据只在 RuntimeError 含 "cann-nnal" 时触发）。这是环境与判据问题，不是算子缺陷；同目录 fp16/不走 ATB JIT 的路径照常全绿（8/8 Pass）。tilelang 需独立 whl，未装即 skip。

**回归基线（190 / 26.2.0@b1ef3ad）**：UT 593 passed / 0 failed / 63 skipped；ATK 27/27 算子 Pass、1122/1122 任务；aclnn+catlass 155 passed。结果显著偏离时先查 env 与 die 占用，再判代码。

**坑**：
- Windows PowerShell 5.1 会把带空格的远端命令拆散（只发第一段 → `SyntaxError` / `~: 未找到命令`）→ 用「本地写 `.sh` → SFTP → `bash`」或清单式 `put`/`run` 执行器。
- 188 的 sshd 拒绝客户端→服务端写入：sftp put、stdin 上传、>1.5KB 的 inline 命令均 `ConnectionResetError 10054` / `Server connection dropped`；只能短单行，落文件用 800 字符一段 base64 追加后 `base64 -d`。
- pytest 未 source CANN 表现为 **2 个 collection errors**（torch_npu 导入失败），不是用例失败。
- `nnal/atb/set_env.sh` 引用未绑定的 `ZSH_VERSION`，外层 `set -u` 会静默中断（空日志 + rc=1）。

## CI 门禁镜像配套与可拉性核查（改 container.image 前后）

门禁实际生效的 CANN / torch_npu / triton-ascend / Python **完全由 `container.image` 决定**：`ci/MindSpeed_Ops_ut.sh` 用 `pip install -e . --no-deps`，分支 `requirements.txt` 的 pin 在 CI 里不生效。所以「配方改了」不等于「门禁栈改了」。

- 需逐项对齐的六处位置（workflow / ci/Dockerfile / ci/build.sh / pin / 发布配方 / 文档版本表）见 references/ci-image-verify.md。
- SWR 匿名 registry 三步探测命令（401 取 realm → token → manifest/tags）见 references/ci-image-verify.md。

判读要点：
- **必须做对照**：同一个 repo 里拿一个已知存在的旧 tag 测 200，再用新 tag 测 404，才能断定新镜像缺失；私有 repo 对匿名一律 404（不泄露存在性），只测一个 tag 会误判。
- manifest list 的 `manifests[].platform.architecture` 判定有无 `arm64`（门禁 runner 是 aarch64；x86_64 构建的镜像用不了）。
- 镜像判读细则（ascendhub 命名与芯片段、UT 容器四项检查、镜像内 mindspeed_ops 覆盖）见 references/ci-image-verify.md。

**回滚**：`container.image` 退回上一个可用 tag 的同时，把配方与 pin 一起回退，三者保持一致；只退其一都会留下静默不一致。
