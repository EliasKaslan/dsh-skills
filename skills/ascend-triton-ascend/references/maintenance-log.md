# ascend-triton-ascend 维护记录（原 §维护记录原样拆出）

> 从 `ascend-triton-ascend/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

## 维护记录

- **2026-10-09（补两条实测，未动 frontmatter / description / 「何时调用」）**：新增**坑 9**——同版本换 base triton wheel 是 pip 的静默空操作（`already installed with the same version`，`WHEEL` 的 `Tag:` 不变，必须先 `uninstall` / `--force-reinstall`），且换 base wheel **只买到 provenance、买不到功能差异**（`triton_ascend` 的 RECORD 有 243 条覆盖 `triton/` 内，含 `_C/libtriton.so`；两个 base wheel 的 `libtriton.so` 同为 140,886,096 B）。步骤 ② 增记反面写法：判 `backends/ascend` 只能从 `triton.__file__` 出发，用 editable 包的 `__file__` 拼路径恒为 `False`。

- **2026-10-08（并入并行 lane P3）**：新增**步骤 ⓪**——把 triton-ascend 的 whl 预下载（本包 279.9 MB + 社区 `triton==3.2.0` 约 250 MB，**整条流程最大的单项**）提前到并行段，与 CANN 三包下载 / conda 建环境 / 两仓 clone 同时发；步骤 ① 改为**用 wheelhouse 离线装**并保留在线回退。同时钉死**单一归属**：这一组只在本 skill 下载，`ascend-torch-npu` 步骤 3 只下 torch 栈 + torch_npu，避免两个 `pip` 并发写同一个 `$WH` 的同名 wheel。下载组带上了与 torch 栈共用的 `-c constraints.txt`（`torch==2.12.0+cpu`），万一 triton-ascend 也依赖 torch 也不会拉 CUDA 大包（约束语义已在 `ascend-torch-npu` 步骤 3 实测）。含"是否依赖 torch""并发写同一 `$WH`"两条**未验证**标注。编排全貌见 `ascend-env` §3.1。

- **2026-09-23（定向修正，原判据不准确）**：原「用 `triton/backends/ascend` 目录是否存在判可用 / 被覆盖后变 `False`」被新证据推翻——`pip install -U triton`（装 3.8.0，342s）后 `triton_ascend 3.2.2` 的 dist-info 与 `triton/backends/ascend/` **都还在（孤儿残留）**，真正症状是 `import triton` 抛 `ModuleNotFoundError: No module named 'triton._C.libtriton.ascend'; 'triton._C.libtriton' is not a package`；判据改为「`import triton` 成功 **且** `triton.__version__ == 3.2.0`」，恢复命令实测 5 秒恢复。同批补：坑 2 的 RECORD 级覆盖证据（376/249/重叠 73、ascend 目录 0 vs 111、覆盖 `triton/__init__.py`）、坑 8（华为云 `ascend/repos/pypi` 非 PEP503 index）、坑 7 的 3.2.2 无 gitcode tag/release 存疑项。证据包：`D:\workspace\agent\skill\_recon\torch_stack_verified.md` §6（RECORD 级覆盖关系）/ 附录 A（破坏/恢复实测）。

