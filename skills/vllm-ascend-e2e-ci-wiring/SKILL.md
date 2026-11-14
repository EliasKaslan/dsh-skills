---
name: vllm-ascend-e2e-ci-wiring
description: vllm-ascend e2e 进 CI：estimated_times 登记、coverage 门禁、目录归属。适用于"新增 e2e / CI 报 MISSING / 本地全 MISSING"。
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
- **`hf_overrides` 的嵌套 dict 是深合并，不是整体替换**（vLLM 侧证据：`vllm/config/model.py` 的 `_apply_dict_overrides` → `_update_nested`，对已存在的子 config 对象递归 `setattr`）→ 只写 `{"text_config": {"num_hidden_layers": 4, "layer_types": [...]}}` 时，`num_experts` 这类兄弟字段会被保留；若某版 vLLM 退回浅替换，`get_hf_text_config()` 会先抛 `ValueError: The text_config extracted from the model config does not have num_attention_heads attribute`，用例根本走不到后面的断言。注意 `text_config` 若已是 plain dict（不是 config 对象）走的仍是整体替换分支。
- **`enforce_eager=True` 会把 conftest 注入的 cudagraph_mode 清成 NONE**（vLLM `config/vllm.py`：`if model_config.enforce_eager: compilation_config.cudagraph_mode = CUDAGraphMode.NONE`）→ marker 里写 `graph_mode="eager"` 是准确的，ModelCache 默认塞进来的 `FULL_DECODE_ONLY` 不会与它冲突。
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

## 新增 four_card / BI e2e 用例的验收清单（marker / 显存 / 触发 / 分支对齐）

## 新增 four_card / BI e2e 用例的验收清单（marker / 显存 / 触发）

**适用**：往 `tests/e2e/pull_request/four_card/**` 加一条用例（尤其批次不变性这类要吃满显存的），从写 marker 到让 CI 真正跑起来。

### 1. marker 与路径必须自洽

- `graph_mode` 的合法取值见 `tests/e2e/coverage_taxonomy.py:107`：`eager / full_graph / full_decode_only / piecewise / full_and_piecewise / aclgraph / xlite_*`。写 `eager` 是合法的，但必须和 `extra_kwargs` 里的 `enforce_eager=True` 同时出现，否则覆盖率报告与实际执行模式不符。
- `four_card/*` 一律路由到 A3 4 卡（`/e2e` 路由表：路径含 `four_card` → A3 4 卡；含 `two_card` → A3 2 卡；`one_card` → A2 单卡；`_310p` 优先）。改 marker 前先 `git grep 'hardware=' -- tests/e2e/pull_request/four_card` 看该目录是否全部一致（本仓当前 19 处全是 `A3`），别照抄旧用例的 `A2`。
- `e2e_model("...")` 必须写字符串字面量：`tests/e2e/generate_coverage_html.py` 用 `ast` 读 marker，只接受常量，模块常量会让用例在覆盖率报告里丢掉模型。
- 新文件必须登记 `.github/workflows/scripts/estimated_times.yaml`，CI 会查缺失；用户可见的行为改动还要补 `release_notes/fragments/<PR号>.yaml`（category: bugfix/feature…，格式见 `TEMPLATE.yaml`）。

### 2. 显存预算：先算「峰值」，再定 utilization

切片用例的 OOM 往往不在权重，而在**第二份 cache**：

- 解码注意力按**单个 full-attention 层**的整份 KV cache 申请 FIA max workspace（`vllm_ascend/attention/attention_v1.py` 里 `_npu_fused_infer_attention_score_get_max_workspace`）。实测关系：`workspace = cache / full_attention_层数`。
- 只有 1 个 full-attention 层时，切片要把 cache 装两遍，峰值 ≈ `weights + 2 × utilization × die`。于是 `utilization` 必须明显小于 0.5（例如 0.45 留出约 10% 余量），而 0.9/0.95 这种「cache 摊在很多 full-attn 层上」的默认值在这里必 OOM。
- 写成 `gpu_memory_utilization=min(float(os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "<ceiling>")), <ceiling>)`：CI 可降不可升，忙机也能跑。
- 图模式下 capture 会常驻 max workspace（`vllm_ascend/compilation/updatable_graph.py`），要么 `enforce_eager=True`，要么再留一份 cache。

未验证：`weights` 具体占用不能靠参数量估，必须从启动日志的 `Available KV cache memory` 反推（层数很少的切片尤其容易估错）。

### 3. 触发与判读

- 硬件 e2e **不会**随 push 自动跑：在 PR 评论 `/e2e tests/e2e/pull_request/four_card/<...>/test_x.py`（只接受 `tests/e2e/pull_request/` 下的路径；`/nightly` 才管 nightly）。PR 作者本人即可触发，其他人需 triage+。
- 触发后看 repository_dispatch 的 `Handle /e2e Command` run，再等它派生的 A3 job；普通 PR 的 `E2E` workflow 只跑 pre-commit + cpu-ut，别把它当硬件验证。
- MCP 的 `update_issue` 改 PR 元数据可能报 `Permission Denied: Resource not accessible by personal access token`，但用同一 PAT 直接 `PATCH /repos/{owner}/{repo}/pulls/{n}` 返回 200；发 `/e2e` 评论用 `POST /repos/{owner}/{repo}/issues/{n}/comments`（201）。改 PR 正文时保留自动维护的 `- vLLM version:` / `- vLLM main:` 行。

### 4. fork 分支落后 main 时不要硬来

浅克隆（`git clone --depth N --branch <br>`）后直接 `git merge upstream/main` 会报 `fatal: refusing to merge unrelated histories`。补历史再合：

```bash
git fetch --shallow-since=<YYYY-MM-DD> upstream main
git fetch --shallow-since=<YYYY-MM-DD> origin <branch>
git merge-base HEAD upstream/main      # 有输出才继续
git merge --no-ff --signoff upstream/main
```

不要 force push；merge commit 带 sign-off，DCO 能过。推 fork 分支用一次性 URL，不写进 `.git/config`：

```bash
git push "https://x-access-token:$(cat <token-file>)@github.com/<user>/<fork>.git" HEAD:refs/heads/<branch>
```

改完跑 `ruff check` / `ruff format --check`（本仓 line-length=120），再确认 `git ls-files --eol` 里 index 是 `lf`（Windows 工作区 CRLF 是 autocrlf 正常现象）。

## 合并前的门禁：ci-gate 的 label 规则、/e2e 结果读取与「真模型优于切片」

## 合并前的门禁：ci-gate 的 label 规则与结果读取

**适用**：PR 在 vllm-ascend 上已经跑过 `/e2e`，但 `ci-gate` 仍红；或想知道一条 PR 到底还差什么才能合。

### 1. `ci-gate` 不是「CI 都绿了」的意思

`.github/workflows/pr_test.yaml` 里的 `ci-gate` 汇总 `pre-commit` / `cpu-ut` / `select-tests` / `run-selected-tests*`，规则分两类：

- PR **只改测试/文档/CI**：`select-tests` 因没有触发 label 而 skipped，gate 直接放行（不需要 e2e）。
- PR **触碰源码**（哪怕只在测试 PR 里加了一个 backend 声明）：`has_tests=true`，gate 要求 `ready-precise` / `ready-all` / `main2main` 之一；没 label 就报
  `This PR touches source code (test selection source: ...), so precision/full tests are required before merge`。
  **手工 `/e2e` 不能替代它**——gate 读的是本 run 的 `run-selected-tests`，不是 dispatch 出来的 e2e job。

推论：把「驱动测试的源码修复」塞进 test-only PR，会同时得到「e2e 能跑」和「gate 必须有 label」两个结果。要么让维护者加 label，要么把源码改动拆成独立 `fix:` PR（它自己也要 label）。

### 2. 触发与判读

- 硬件 e2e 只能由评论 `/e2e <tests/e2e/pull_request/... 路径>` 触发；PR 作者或有 triage+ 权限者可发。路由按路径：`four_card` → A3 4 卡，`two_card` → A3 2 卡，`one_card` → A2 单卡，`_310p` 优先。
- `/e2e` 一次跑两条 vLLM 车道（verified main 与 release tag）。**两条都绿才算数**，只看一条容易漏。
- job 结论里 `cancelled` 不等于失败：常见是节点级基础设施错误（例如 `HCCL function error: hcclCommInitRootInfoConfig ... code 7 (resource unavailable)`）把 4 个 rank 全打挂，case 挂到超时被 runner 取消。此时结论是「无判定」，重跑一次，不要据此改代码。

### 3. 不点网页也能拿到 pytest 输出

```bash
# 1) 取 job id：GET /repos/{o}/{r}/actions/runs/{run_id}/jobs
# 2) 取日志：GET /repos/{o}/{r}/actions/jobs/{job_id}/logs
#    -H "Authorization: Bearer <PAT>"，不要自动跟随跳转，先读 302 的 Location
# 3) 再 GET 那个签名 URL（不带 auth），响应体就是纯文本日志（不是 zip）
```

然后 grep `collected|passed|failed|PASSED|Running target` 就能确认「真的跑了这条用例、真的过了」，而不是只有 job 绿。

### 4. BI 的 e2e 用例：能用真模型就别只用切片

- 切片（`hf_overrides` 减层 + `load_format=dummy`）只能证伪，不能证真：它只覆盖被切到的层与形状。
- 先查同目录是否已有该模型的四卡用例（真权重在 runner 上已缓存），有缓存就直接服务完整模型；显存按 **workspace = KV cache / full-attention 层数** 估：层数多时 0.9 的 utilization 也能放下，只有单层 full attention 的切片才需要把 cache 装两遍（那时才要压到 ~0.45）。
- 用例里把模型形状钉死（层数、GDN/full 的条数、experts/top-k），否则上游 interleave 变化时会「静默换个模型还绿」。

未验证：不同 checkpoint 的真实权重体积/加载耗时差异较大，显存预算仍要以启动日志的 `Available KV cache memory` 为准。

## 切片用例：多模态 hf_overrides 的作用域，以及 setup 阶段失败的判读

## 切片用例：`hf_overrides` 的作用域（多模态 checkpoint）与 setup 阶段的基础设施失败

**适用**：给 e2e 用例做「减层切片」却加载成了全模型；或 e2e job 在 `Set up job` 就红，日志里没有任何 pytest 输出。

### 1. 扁平 override 到不了 text tower

vLLM 对 `hf_overrides` 分两条路（`vllm/config/model.py:626-640`）：

- **扁平键**（`{"num_hidden_layers": 4}`）→ `config.update(...)`，只写顶层 config；
- **dict 值**（`{"text_config": {...}}`）→ `_apply_dict_overrides`（`:565`）递归进嵌套 config。

多模态 checkpoint（文本塔在 `text_config` 里，例如 Qwen3.5 / Qwen3-VL 系）要减层**必须**写嵌套：

```python
SMALL_OVERRIDES = {
    "architectures": ["<TextOnlyForCausalLM>"],   # 只服务语言塔
    "text_config": {
        "num_hidden_layers": 4,
        "layer_types": ["linear_attention", "linear_attention", "linear_attention", "full_attention"],
    },
}
```

只写扁平 `num_hidden_layers` 时文本塔仍是完整层数，用例会悄悄加载全模型（显存、时长、权重下载全变），但 marker 和断言仍显示"切片"——这是最容易误判的一类。

配套检查：断言 `hf_text_config.model_type`（例如 `qwen3_5_moe_text`）确认落到哪个 tower；改 `num_hidden_layers` 时同步把 `layer_types` 截到相同长度、按真实 interleave 写，否则上下游的层数/列表长度约束容易对不上（未验证：不同 vLLM/transformers 版本是否强校验长度）。

### 2. `Set up job` 就失败 = 基础设施，不是代码

e2e job 在 `Set up job` 阶段 failure，日志只有：

```text
Failed to download archive 'https://codeload.github.com/runs-on/cache/tar.gz/...' after 3 attempts.
Error: The request was canceled due to the configured HttpClient.Timeout of 100 seconds elapsing.
```

说明 runner 连 action 都没拉下来，pytest 一行没跑 ⇒ 改代码无意义，直接重跑 `/e2e`。同类还有：跑到引擎启动才挂的 `HCCL function error: ... code is 7 (resource unavailable)`，最终表现为 job `cancelled`——同样是"无判定"，不是 case 失败。

判断顺序：先看失败 step 名（`Set up job` vs `Run selected tests with device`），再看日志里有没有 `collected/passed/failed`。没有这两样就不要动测试代码。

### 3. 评审要求切片、而你想要真模型证据时

切片是 CI 成本的妥协，不是证明手段。做法：代码按维护者要求回到切片；把「完整模型也跑过一次并通过」的记录（哪两条车道、耗时）写进 PR 正文作为补充证据，注明它不是本用例的交付形态。这样既满足评审，又不丢"全模型 BI 成立"这一条事实。
