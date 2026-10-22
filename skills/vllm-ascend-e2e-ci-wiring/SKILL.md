---
name: vllm-ascend-e2e-ci-wiring
description: vllm-ascend e2e 用例进 CI 的落位与登记——tests/e2e/pull_request 下新增 test 必须登记 estimated_times.yaml，否则 coverage.py 打印 ✗ MISSING 后 sys.exit(1)；该门禁在 Windows 上必然全报 MISSING；e2e_model 只喂报告，e2e_coverage 值错即硬失败；模型 ID 须在 ModelScope 有仓。适用于"新增 e2e 用例怎么进 CI / 为什么 CI 报 MISSING estimated_times / 本地跑 coverage.py 全是 MISSING / 测试该放 one_card 还是 four_card / e2e_coverage 标记怎么写 / 用例怎么脱钩共享 conftest / 要不要登记 model_dataset_list"。不适用：装或跑 vllm-ascend → 用 `vllm-ascend-source-install`。
whenToUse: 写/审 vllm-ascend 的 e2e 用例落位与 CI 登记时用（模型看不到本节，触发判定只看 description）。
---

# vllm-ascend e2e 用例落位与 CI 登记

对象仓 `vllm-project/vllm-ascend`。**核心结论：README 说"目录决定 runner、无需改配置"只对了一半**——目录决定挂哪个 runner 是真的，但新增/移动 `tests/e2e/pull_request/**/test_*.py` 必须在 `estimated_times.yaml` 登记，否则 LINT 门禁直接失败；而放错目录（runner_mapping 里没有该 pattern）不会失败，只会静默不跑。

## 何时调用

- **触发信号**：CI LINT 打出 `✗ MISSING: tests/e2e/pull_request/...`；本地收集期抛 `[e2e_coverage marker invalid]`；问"新 e2e 用例放哪个目录 / 挂哪个 runner / 怎么进 CI"；问"某能力有没有 e2e 覆盖"；CI 报模型拉不到（离线 + ModelScope）。
- **转交边界**：装 / 编译 / 跑 vllm-ascend → `vllm-ascend-source-install`、`ascend-vllm-serve`；判模型本体适配程度 → `ascend-model-adaptation-recon`；提 PR 的 token / DCO / CI 判读 → `github-pr-flow`；本机 PowerShell 编码与计数坑 → `pwsh-on-windows`。
- **前置**：仓库只读克隆（审计时绝不在原 clone 上改），仓根可跑 python（脚本用相对路径读配置）。／ **后继**：落位与登记通过本地自检后 → `github-pr-flow` 提 PR；合入后覆盖自动补录。

## 前置检查

1. 必须在**仓库根**跑脚本：`coverage.py:10-13` 用相对路径读 `.github/workflows/scripts/test_config.yaml` 与 `estimated_times.yaml`。
2. 先定"我这份 clone 是不是主线"：`git ls-tree -r --name-only HEAD` 与 `git ls-tree -r --name-only upstream/main` 比对测试子树；**别拿旧 clone 的目录结构下结论**。

## 步骤

1. **定卡片数 = 定目录**（`test_config.yaml:109-117` `runner_mapping` 用正则把路径映射到逻辑 partition）：
   `tests/e2e/pull_request/one_card` → `a2-1`（另有 `310p` 变体）；`two_card` → `a3-2`；`four_card` → `a3-4`。
   再由 `partition`（`:122-137`）映射到 `runner_label.json` 的确切 label 与 `count`（如 `a3-4` → `linux-aarch64-a3-4`，`npu_num` 见 `runner_label.json:32-34`）。
   - 验证：目录名必须能匹配 `runner_mapping` 里某个 pattern（这是**硬判据**，见坑 3）。
2. **登记 `estimated_times.yaml`（唯一的硬门禁，最常踩）**：在 `.github/workflows/scripts/estimated_times.yaml` 的 `estimated_times:` 下加一行 `<仓根相对路径>: <秒>`。
   - 判据链：`coverage.py:49` 展开 `tests/e2e/pull_request/**/test_*.py` → `:62` 求 `need_et_files - existing_et_keys` → `:166-168` 打印 `✗ MISSING: <path>` → `:211-223` 有错 `sys.exit(1)`；CI 在 `pr_test.yaml:455-458` 以 `python3 .github/workflows/scripts/coverage.py` 跑它。
   - 记账口径：未列文件默认 600s，**仅文件级**（`::nodeid` 不支持，`estimated_times.yaml:1-9`）；自动铸值 = 中位数 ×1.1 后 round 到最近 10s、最小 10（`update_estimated_times.py:70,87-90`）。手填 600 也能过门禁。
   - **反向规则**：只有 E2E 与 NPU UT 要登记；`tests/ut` 里的 **CPU UT 登记了反而失败**（`coverage.py:64,171-173,214`）。
3. **本地先跑门禁，别等 CI**（在仓根）：
   ```bash
   python .github/workflows/scripts/coverage.py          # 末段 REVIEW RESULT 五项全 ✓，退出码 0
   python .github/workflows/scripts/select_tests.py --all-tests   # 确认新文件被路由
   ```
   `--all-tests` 扫描根为 `tests/ut` + `tests/e2e/pull_request`（`select_tests.py:32-34,106`）。
4. **marker 双件套（`e2e_model` 与 `e2e_coverage` 语义完全不同，别混）**：
   - `@pytest.mark.e2e_model("<ID>")`：注册在 `pyproject.toml:95-97`，**只喂报告**——消费方只有 `tests/e2e/generate_coverage_html.py:126,161-162`，`.github/**` 里 0 处引用。**它既不驱动 CI 运行，也不触发模型下载。**
   - `@pytest.mark.e2e_coverage(...)`：**不打** = 仅 WARNING（`coverage.py:191-199`）；**打了但值不在** `tests/e2e/coverage_taxonomy.py` 的 `ALLOWED_VALUES`（`:30-119`）= 收集期硬失败 `pytest.CollectError`（`tests/e2e/conftest.py:2037-2058`）+ CI 侧 `coverage.py:200-207,218-220` 失败；7 个维度键**必须全给**（`coverage_taxonomy.py:132` `DIM_ORDER`，`:153` `REQUIRED_DIMS = set(DIM_ORDER)`）。
5. **模型下载前置**：CI 容器里 `VLLM_USE_MODELSCOPE=True` + `HF_HUB_OFFLINE=1`（`_selected_tests.yaml:96-97`）→ **模型 ID 必须在 ModelScope 有仓，只有 HF 仓不够**。自动下载通道 = `.github/workflows/misc/model_dataset_list.json`（结构 `{"models":{"a2":[],"a3":[],"a5":[]},"datasets":[]}`）+ PR 打 `model-dataset-download` 标签（`labeled_download_model_dataset.yaml:20,57,102`，用的是 `modelscope download`）。
6. **失败归属看真实执行链**：`pr_test.yaml` select-tests job → run-selected-tests job `uses: ./.github/workflows/_selected_tests.yaml`（`:253/:629/:686`）→ 该 reusable workflow（`on: workflow_call`，`_selected_tests.yaml:20`）→ `.github/workflows/scripts/run_selected_tests.sh`，最终真命令是 `pytest -sv --color=yes "${target}"`（`run_selected_tests.sh:191`）；job timeout 默认 120 分钟（`_selected_tests.yaml:60-64,86`）。
   - **`_selected_tests.yaml` 是 workflow、不是测试清单**，不需要往里登记测试路径（常见误解）。
7. **首次合入的可见性**：改动过的 test 文件会被 `test_selector.py:88-91` 直接加进推荐清单；另两条通道 = `ready-all` 标签跑全量（`pr_test.yaml:400`）与 PR 评论 `/e2e <path>`（`pr_e2e_command.yml:18,36,160`）。合入后 `pr_supplement_new_tests.yaml`（`pull_request_target: closed`，`:5-6`）调 `collect_merged_new_tests.py`，**只盯 `tests/e2e/pull_request/`**（`:40`）补录进 OBS。
8. **判"某能力有没有 e2e 覆盖"必须同时查三条通道**，只查 PR 套件会得出错误结论：
   - PR 套件：`tests/e2e/pull_request/**`
   - nightly：`schedule_nightly_test_a3.yaml:322,364` → `_e2e_nightly_single_node.yaml` + `.github/workflows/configs/nightly_config.yaml`
   - weekly：`tests/e2e/weekly/single_node/configs/*.yaml` + `.github/workflows/configs/weekly_config.yaml`
   - 精度另有 `tests/e2e/models/configs/<MODEL>.yaml`（`tests/e2e/models/conftest.py:10,58-64` 的 `--config-list-file`）。
9. **全树审计**（比逐个 grep 可靠）：`git ls-tree -r --name-only <ref>` 取全树再正则过滤；反查"是否已有未合入的用例/PR"用 GitHub `search/issues?q=repo:vllm-project/vllm-ascend+<KW>+in:title`（查询串必须带 `in:title` 或 `is:issue`/`is:pr`，否则 422 —— 同款坑见 `ascend-model-adaptation-recon`）。

10. **在 Linux 上真跑 coverage 门禁（Windows 上必然假失败）**：
    - 根因（已坐实，行号有效）：`coverage.py:49` 用 `{str(f) for f in Path("tests/e2e/pull_request").rglob("test_*.py")}` 收集路径，Windows 上 `str()` 给**反斜杠**（`tests\e2e\pull_request\...`），而 `estimated_times.yaml` 的 key 是**正斜杠** → `:62` 的 `need_et_files - existing_et_keys` 差集把**每个**文件都判成未登记，`:166-168` 逐条打印 `✗ MISSING`，`:211-223` `sys.exit(1)`。同一反斜杠根因也会让 `:80`/`:94` 的 `runner_mapping` 正则匹配失效（**未验证：这条是同因推断，未单独实测**）。
      → 结论：Windows 上跑 `coverage.py` 得到的一堆 MISSING **与你有没有登记无关**，别据此改仓库。
    - 可复用跑法（实测跑通；只需 `.github` + `tests`，不改原 clone）：
      ```bash
      SCRATCH=/home/vllm/<你的用户目录>/cov_run && mkdir -p $SCRATCH
      SHARED=/mnt/share/<你的工作区>            # 含 .github 与 tests 的那份 clone
      cp -a $SHARED/.github $SCRATCH/ && cp -a $SHARED/tests $SCRATCH/
      # 再把你改过的文件覆盖进 $SCRATCH，然后：
      cd $SCRATCH && PYTHONIOENCODING=utf-8 <python 绝对路径> .github/workflows/scripts/coverage.py
      ```
      `PYTHONIOENCODING=utf-8` 必要：脚本往 stdout 打 `✓/✗`，非 UTF-8 locale 会 UnicodeEncodeError。
    - **先跑原版 yaml 做基线、再跑改过的**，比较 `[2]` 的 `E2E: N/N covered` 与 MISSING 条数。实测量级（本次）：基线 `140/140` → 加一条新 key 后 `141/141`、MISSING=0、退出码 0，`[3]`/`[4]` 全 `✓`，`[5]` unknown marker value = 0（**这一项是硬门禁**）。
    - **门禁只校验 key 是否存在、不校验数值**：新用例的值可先填实测时长的 ~3 倍，`update_estimated_times.py` 会用真实 CI 计时自动纠正；`select_tests.py` 只把该值当**相对权重**做负载均衡，**没有时间预算上限**。
    - **过期文档**：`TEST_README.md` 里提到的 `.github/workflows/scripts/test_select_tests.py` **仓库里不存在**（该行已过期），同目录只有 `test_selector.py` —— 引用前先 `git ls-tree` 核文件。
    - `select_tests.py --all-tests` 的 **stdout 不是纯 JSON**（含 `test_groups=[...]` 字面量行），`json.load` 会报 `Expecting value: line 1 column 1 (char 0)`；**结论看 stderr**（人类可读的 runner 分块树）。
11. **把新用例做成自包含（从共享 conftest 脱钩）**：
    - 触发场景：同目录的 `one_card/rlhf/conftest.py` 是 pytest plugin，**在测试模块之前导入**，会把 `MODEL_NAME` 之类在导入期定死；而且它可能正被别的 open PR 占用（改它 = 与别人的 PR 抢同一文件）。
    - 正确做法：**新建一个独立文件**，只 `import tests.e2e.conftest`（拿到 `RemoteOpenAIServer`），自己在 `tmp_path` 里生成减层 `config.json` + 合成 tokenizer，用 `--load-format dummy` 起服务。
    - 好处（实测）：**零 Hub 调用** → 零外部依赖 → **不需要**登记 `.github/workflows/misc/model_dataset_list.json`。那个工作流只下载「PR 标签列表 − `origin/main` 列表」，登记一个大权重仓会让**每个**相关集群预拉整个 checkpoint。**登记之前先确认用例到底需不需要权重。**

## 坑与修法

- 新增 E2E 文件没登记 → LINT 打印 `    ✗ MISSING: tests/e2e/pull_request/...`（`coverage.py:168`）后 `sys.exit(1)`（`:223`）。
  → 修法：`estimated_times.yaml` 补键。
- 把 CPU UT 也登记了 → `✗ LEAKED (CPU UT should not have et): tests/ut/...`（`coverage.py:173`）→ 删键。
- **放错目录不会报错，只会静默不跑**：`tests/e2e/pull_request/eight_card/` 在磁盘上存在（含 `__init__.py`），但 `runner_mapping` 里**没有** entry；`coverage.py` 只校验 pattern→文件方向（`Pattern '...': matches 0 tests (unused)`，`:81-82`），**从不校验文件→pattern 方向**；`select_tests.py:266-270` 只往 stderr 打 `Warning: E2E test file <path> does not match any runner pattern, skipping.` 就丢掉。
  → 修法：新用例所在目录必须出现在 `test_config.yaml` `runner_mapping` 里；`--all-tests` 后确认它出现在预期 partition。
- **文档与配置不一致，以配置为准**：`.github/TEST_README.md` §Adding a New E2E Test（`:143-152`）写 "The directory determines the runner. No configuration change is needed."，`:150` 还推荐 `eight_card/`；全篇 grep `coverage.py` **0 命中**（不提这道硬门禁），只在 `:52`/`:94` 说 `estimated_times.yaml` 用于负载均衡；`:91` 列的 `pinned_routes` 在整个 `.github/` 下**只剩 README 自己**（配置与脚本 0 处）。
- **时长自动更新不可依赖**：`schedule_daily_test.yaml` 会建 `auto/update-estimated-times-${github.run_id}` 分支并自动开 PR（`:332,384`），但开关 `inputs.update_est_times` 默认 `false`（`:28-32`），且该 workflow 只有 `workflow_dispatch`、无 `schedule`/cron（`:20-21`，grep `cron` 0 命中）→ 不会自己跑，时长得手填。
- marker 写错在**本地收集期**就炸：`[e2e_coverage marker invalid] <nodeid> ... Values must come from tests/e2e/coverage_taxonomy.py (ALLOWED_VALUES). Fix the marker or update the taxonomy.`（`tests/e2e/conftest.py:2054-2058`）→ 回 `coverage_taxonomy.py:30` 对值、`:132/:153` 补维度。
- **别的 manifest 里的悬空路径没人管**：`coverage.py` 的 BROKEN PATHS 只校验 `test_config.yaml` 的 `curated_tests`/`skip_tests`/`accuracy_tests`（`:20-33`）。例：`main2main_tests.json:18` 指向 `tests/e2e/pull_request/two_card/test_hccl_weight_transfer.py`，而真实文件在 `two_card/rlhf/state_transitions/` 下 → 自己用 `git ls-tree` 核，别信清单。
- **目标 HF 仓带 NPU 不支持的量化配置 → 起不来**：实测原文 `ValidationError: mxfp4 quantization is currently not supported in npu`（仓里是 `mxfp4-pack-quantized`）→ 在用例生成的 config 里清掉量化配置。
- **多模态仓 + 只枚举文本塔 → `load_weights` 失败**：用例用 `meta_config_attribute="text_config"` 时实测报 `ValueError: Following weights were not initialized from checkpoint: {vision_tower.*, mm_projector.*}` → 必须同时把顶层 `architectures` 覆盖成**纯文本塔**架构名（值照抄官方 `config.json` 里 `text_config.architectures`）。
- **`checkpoint_name_map` 只能改名、不能融合张量**：昇腾 KDA 把短卷积融合成单个 `self_attn.ascend_conv1d_weight`，而 HF meta 模型给的是分开的 `q/kv_conv1d.weight` → 这种映射**改不出来**，属基建缺口，只能跳过该 case。
- **已实测（本次）**：第 3 步的 `coverage.py` 已在 Linux scratch 上**真跑过**（见步骤 10，退出码 0、`141/141 covered`、MISSING=0）；`select_tests.py --all-tests` 也真跑过（stdout 非 JSON，看 stderr）。**Windows 侧仍然跑不了**（反斜杠根因，见步骤 10），别在 Windows 上用它判登记对错。
- **别拿 hash 相等当「远端实测的文件 == 你提交的 blob」的证据**（本机 `core.autocrlf=true`：工作副本 CRLF、blob LF）→ 判 blob 同一性的方法见 `orchestrating-subagents` §4 第 6 条。
- `未验证：`步骤 10 里「反斜杠也会让 `runner_mapping` 正则失效」是同因推断，未单独实测；第 2 步里 `update_estimated_times.py:70,87-90` 的铸值口径来自读源码，未亲跑该脚本。

## 不要做什么

- 不要只加 `e2e_model` / `e2e_coverage` marker 或改 README 就以为"用例进 CI 了"——硬门禁是 `estimated_times.yaml` 登记。
- 不要把 `e2e_model` 当下载开关（它是报告用的）；不要往 `_selected_tests.yaml` 里登记测试路径。
- 不要只查 PR 套件就判"某能力没有 e2e 覆盖"（还有 nightly / weekly 两条通道）。
- 不要靠 `schedule_daily_test` 自动补 `estimated_times`；不要按 `TEST_README.md` 的配置表办事（它已落后于配置文件）。
- 不要在 vllm-ascend 原 clone 上改动来做审计（只读克隆 + `git ls-tree`）。

## 验收标准

1. `python .github/workflows/scripts/coverage.py` 退出码 0，`REVIEW RESULT` 里 `[1] BROKEN PATHS 0`、`[2]` 无 `✗ MISSING`/`✗ LEAKED`、`[3]`/`[4]` 无 `✗`。
2. 新文件路径被 `test_config.yaml` 的 `runner_mapping` 匹配，且 `select_tests.py --all-tests` 输出里落在预期 partition（而不是 stderr 的 `does not match any runner pattern`）。
3. `estimated_times.yaml` 有该文件键、且 CPU UT 无键。
4. 若打了 `e2e_coverage`：7 维齐备、每个值都在 `ALLOWED_VALUES`。
5. 用例引用的模型 ID 在 ModelScope 有仓（否则离线 CI 拉不到权重）。
6. 门禁**在 Linux 上**跑过（步骤 10 的 scratch 跑法）：`[2] E2E: N/N covered` 里 N 比基线大 1、MISSING=0、退出码 0、`[5]` unknown marker value = 0。在 Windows 上跑出的 MISSING 不作数。

## 零权重范式与补强实测 → `references/zero-weight-and-fixup.md`

- **零权重范式**：权重搬运类 e2e 用例只需要一个 `config.json`，不必放真权重。
- **补强实测（merge 4004d10e）** 六条：`tests/ut/**` 的 CPU UT 登记 = **主动制造 `✗ LEAKED`**；新 e2e 文件缺 `e2e_coverage` marker 时 CI 只 WARNING；`main2main_tests.json` 的悬空引用在该提交上仍然悬空；「改名/搬家」的用例 GitHub API 只给 removed+added、**必须同步改 `estimated_times` 的 key**；判"权重真的换上了"要比对**行为签名**，不要比对张量；同一 PR 的打包开关 / 缓冲区 / 主机侧 / 触发标签。

命令、原文与逐条出处都在该文件；上面只留判据。
