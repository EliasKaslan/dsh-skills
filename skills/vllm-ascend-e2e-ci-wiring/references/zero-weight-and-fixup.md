# 零权重范式 + merge 4004d10e 补强实测（从正文原样拆出）

> 从 `vllm-ascend-e2e-ci-wiring/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

## 零权重范式：权重搬运类 e2e 用例只需要一个 `config.json`

**实测对象**：`tests/e2e/pull_request/rlhf/weight_transfer_test_utils.py`（**712 行**，commit `12e7e1cb`）。该 harness 里**已经存在**"减层 + 合成权重"范式，**不必自己发明**——给新模型加权重搬运用例照抄它即可。

- `MODEL_CASES`（`:149` 起）里既有的 `qwen3.5-35b-a3b-moe-layout` 用例**就是**这个范式：
  `hf_overrides={"architectures": [...], "text_config": {"num_hidden_layers": 4, "layer_types": [...]}}` ⇒ **减层靠 `hf_overrides`，不靠改真权重**。
- 权重由 `FixedRandomWeightSource` **合成**（迭代参数 yield name/shape/dtype），`write_checkpoint`（`:419`）用 `save_file` 写出 `model.safetensors`。
- **唯一的联网点只有一个文件**：`write_checkpoint` 里 `:439 from huggingface_hub import hf_hub_download`、`:444 shutil.copyfile(hf_hub_download(self._case.model, "config.json"), target / "config.json")` ⇒ **只取 `config.json`，不取任何权重**。

⇒ **可复用判据**：给新模型加权重搬运 e2e 用例时，**只需一个能提供 `config.json` 的来源**（Hub / ModelScope 仓，或改成本地目录优先），**权重全部合成** —— **不需要真权重、不需要下载模型**。（与步骤 11「零 Hub 调用」的自包含做法同族；区别是这条直接来自 harness 自带的既有用例，可照抄。）

- **当时的真实缺口（可复现判据）**：`grep -c -i kimi <该文件>` 实测 = **0** ⇒ 该 harness 里**没有** Kimi 用例。
- **同一道门禁的另一次实测（2026-10-09；仓库状态与步骤 10 那次不同，条数自然不同，两者不矛盾）**：Windows 本地直跑仍**全量假报** `E2E: 0/146` + **146 条** `✗ MISSING: tests\e2e\…` + `exit 1`（反斜杠根因同步骤 10，**不许据此改仓库**）；**真门禁侧的读数**（Windows 必然全假报 ⇒ 这两个数不可能来自 Windows）为：**未登记 → `E2E: 146/147` + `✗ MISSING` + `exit 1`；登记后 → `147/147` + `exit 0`**。

## 补强实测（merge 4004d10e）：LEAKED / marker / 悬空引用 / 改名 / 行为签名

以下六块全部取自同一次实测：merge commit `4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6`（实测父 = `baa023ada41a5b889cac6249845a688aab130892`）。上文已写过的口径在此只做**补强**——把"规则"变成"该提交上的实测证据"，不重复陈述。

### A. `tests/ut/**` 的 CPU UT 登记 = 主动制造 `✗ LEAKED`（补强上文步骤 2 的反向规则与坑里的 LEAKED 条）

- 机制：`coverage.py:51-64` 收集 `tests/ut/**/test_*.py`，`:171-173` 对命中 `tests/ut/` 的 estimated_times key 打印 `✗ LEAKED`。
- 实测（数该提交上整张表的条目数）：
  ```bash
  git -C <clone> grep -c 'tests/ut' 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- .github/workflows/scripts/estimated_times.yaml
  ```
  结果 = **0**：该提交上整张 `estimated_times.yaml` 里 `tests/ut` 条目数为 0。
- 同 PR 新增的 CPU UT oracle `tests/ut/distributed/weight_transfer/test_e2e_weight_transfer_oracle.py`（+189 行）**正确地没有登记**。复核：`git -C <clone> show --stat 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- tests/ut/distributed/weight_transfer/test_e2e_weight_transfer_oracle.py`。
- ⇒ 口径：**只有 `tests/e2e/**` 下的用例才登记**；登记 `tests/ut/**` 不是"多一层保险"，而是主动制造 `✗ LEAKED` 硬失败。

### B. 新 e2e 文件缺 `e2e_coverage` marker 时 CI 只 WARNING（补强上文步骤 4 的口径）

- 机制：`coverage.py:191-199` 与 `:211-221`——`has_errors` 只收集 `_marker_unknown_values`，所以"未打 marker"只落进 WARNING 桶，不进 `has_errors`，不触发 `sys.exit(1)`。
- 实测：该 PR 两个新 e2e 文件**都没有 `e2e_coverage` marker**（只经 `pytest_model_cases()` 间接打 `e2e_model`），CI 不会因此红。复核：
  ```bash
  git -C <clone> show --name-only --format= 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 | grep '^tests/e2e/pull_request/'
  git -C <clone> grep -n 'e2e_coverage' 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- <上面列出的新文件>
  ```
  后者对新文件零命中。
- ⇒ 口径：**没 marker ≠ CI 会挂**，别把它当硬门禁。硬门禁只有两条：`estimated_times` 的 MISSING（`coverage.py:166-168,223`）与 marker **值**非法（`:200-207,218-220`）。

### C. `main2main_tests.json` 的悬空引用在该提交上仍然悬空（补强上文"别的 manifest 里的悬空路径没人管"）

- 实测：merge 提交上 `main2main_tests.json` **仍指向已被删除的** `tests/e2e/pull_request/two_card/test_hccl_weight_transfer.py`（该文件在本 PR 里被删、内容搬到了 `two_card/rlhf/state_transitions/`）。
- 它由 `.github/workflows/schedule_main2main.yaml:210` 经 `MAIN2MAIN_CASES_FILE` 消费。
- `coverage.py` 的 **BROKEN PATHS 检查（`:20-33`）不覆盖这个文件** ⇒ **没有任何 CI 会因此报红**。复核：
  ```bash
  git -C <clone> show 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6:.github/workflows/scripts/main2main_tests.json | grep hccl_weight_transfer
  git -C <clone> ls-tree -r --name-only 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- tests/e2e/pull_request/two_card/test_hccl_weight_transfer.py
  ```
  前者仍命中、后者无输出（文件确实已不在）。
- **是否真会导致那个 workflow 运行期失败：本次未能确认。**（只证明了"清单悬空"+"无 CI 检查"两件事，没有触发 `schedule_main2main` 实跑。）这句"未确认"是结论的一部分，别升级成断言。

### D. "改名/搬家"的用例，GitHub API 可能只给 removed+added、不给 renamed —— 必须同步改 estimated_times 的 key

- 实测：`one_card/test_npu_ipc_weight_transfer.py` → `one_card/rlhf/state_transitions/test_npu_ipc_weight_transfer.py`，`files.json` 里是 `removed` + `added`（内容差异大，相似度不够被判 renamed）。
- `estimated_times.yaml` 的 key 是**路径字符串**，必须同步改；两个 key 在文件里**不相邻** ⇒ 出现**两个 hunk、各 1 增 1 删**（合起来 +2/−2）。逐字：
  ```diff
  -  tests/e2e/pull_request/one_card/test_npu_ipc_weight_transfer.py: 180
  +  tests/e2e/pull_request/one_card/rlhf/state_transitions/test_npu_ipc_weight_transfer.py: 1800
  -  tests/e2e/pull_request/two_card/test_hccl_weight_transfer.py: 130
  +  tests/e2e/pull_request/two_card/rlhf/state_transitions/test_hccl_weight_transfer.py: 1800
  ```
- 复核命令（先解析出父，再 diff 该文件）：
  ```bash
  git -C <clone> diff $(git -C <clone> rev-parse "4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6^1") 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- .github/workflows/scripts/estimated_times.yaml
  ```
- ⇒ 口径：**搬家改名时漏改 estimated_times 的 key = MISSING 硬失败**；而且因为 GitHub 侧不是 renamed，很容易在 diff 里看漏——**别靠 `renamed` 事件去驱动改 key，要按"路径字符串有没有变"逐条核**。

### E. 判"权重真的换上了"要比对行为签名，不要比对张量

- 实测：该 PR 的共享测试工具 `tests/e2e/pull_request/rlhf/weight_transfer_test_utils.py` 里，`allclose` / `isclose` / `load_state_dict` / `torch.equal` / `np.array_equal` **一个都没有**（检索结果 NONE）。复核：
  ```bash
  git -C <clone> grep -nE 'allclose|isclose|load_state_dict|torch\.equal|np\.array_equal' 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- tests/e2e/pull_request/rlhf/weight_transfer_test_utils.py
  ```
  零命中。三条断言的复核命令（去找断言行号，本文件不写行号以免过期）：
  ```bash
  git -C <clone> grep -nE 'dummy != reference|updated == reference|reloaded == reference' 4004d10e9b82b6bb36d7093a8e8ae19bdb97a1f6 -- tests/e2e/pull_request/rlhf/weight_transfer_test_utils.py
  ```
- 它改为比对**行为签名**：同样 prompt 生成的 **(文本, token logprob 元组)**，用 Python 元组 `==` 做**精确相等**（无 atol、无阈值）。三条断言：`dummy != reference`、`updated == reference`、`reloaded == reference`。
- 第一条 `dummy != reference` 是**保险丝**——保证测试有区分能力；没有它，后面两条等于没测（参照物和被测对象一起错也会"通过"）。
- ⇒ 口径：**只比对张量列表，可能因为"列表里确实有正确张量"而误判通过**；要比对"模型行为变了没有"。

### F. 同一 PR 的其它可复用事实（打包开关 / 缓冲区 / 主机侧 / 触发标签）

- 参数化打包开关用 `@pytest.mark.parametrize("packed", [False, True], ids=["unpacked","packed"])`，**没有 fixture**。
- HCCL 侧 `packed` 必须**传两处且一致**：服务端 `update_info["packed"]` 与 `HCCLTrainerSendWeightsArgs(packed=)`；两处不一致 = 静默按未打包处理。
- 缓冲区尺寸与 packed 无关地总按 `max(最大张量尺寸 + 128MiB, 1GiB)` 算；不这么算，大 embedding（实测约 1.9GB）会报 `ValueError: Tensor ... exceeds buffer_size_bytes`。
- 主机侧：`one_card` → `linux-aarch64-a2b3-1`（A2/910B，1 卡）、`two_card` → `linux-aarch64-a3-2`（A3，2 卡）；镜像来自私有 SWR，`VLLM_USE_MODELSCOPE=True` + `HF_HUB_OFFLINE=1`。**公开 CI 跑不动这些用例**——GitHub 上只有 lint job（真正跑 e2e 的 job 需要自建 runner label）。
- 触发：`pr_test.yaml` 的 `on.pull_request` types 含 `labeled`，但**必须维护者贴恰好一个** `ready-precise` / `ready-all` / `main2main`，否则 `ci-gate` 判失败（多贴一个 = 失败，不是取并集）。
