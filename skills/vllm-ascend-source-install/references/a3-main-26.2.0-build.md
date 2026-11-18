# main + 商发 26.2.0（CANN 9.2.0）在 A3 x86_64 上的构建链（自 SKILL.md 逐字迁移）

### 版本口径

`.github/vllm-main-verified.commit` 给 vLLM commit（本例 `ba15685a…`）；**商发 26.2.0 = CANN 9.2.0 /
torch_npu 2.10.0.post7 / triton-ascend 3.6.0**（依据：`atlas-release/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-a3-…` 镜像标签
与 MindSpeed-Ops 门禁 PR 文案）。main 的 README 写 CANN==9.2.1，实测 9.2.0 **无运行时版本闸门**可跑；
这是对"官方认证组合"的偏离，交付报告里必须单列。基础镜像直接用上面这个 26.2.0 镜像最省事
（CANN、torch、torch_npu、triton 都已就位，避免在纯 `cann:9.2.0` 镜像里再找 cp312 轮子）。

### 构建顺序（实测）

```bash
# 1) vLLM：只取配对的单个 commit，不 --depth 1 拉全历史
git clone --filter=blob:none --no-checkout https://github.com/vllm-project/vllm.git vllm
cd vllm && git fetch --depth 1 origin <verified-commit> && git checkout FETCH_HEAD
pip install setuptools_rust setuptools_scm cmake ninja   # 否则 setup.py 直接报下面的错
VLLM_TARGET_DEVICE=empty pip install -e . --no-build-isolation

# 2) vllm-ascend：先只编 _C，再用官方脚本单独装 BI 算子
cd ../vllm-ascend && git checkout <main-commit>
COMPILE_CUSTOM_KERNELS=0 pip install -e . --no-build-isolation --no-deps
pip install transformers==5.19.0 fastokens memfabric-hybrid==1.3.0 memcache-hybrid==1.3.0
bash csrc/build_batch_invariant_ops.sh ascend910_93     # A3；A2 用 ascend910b，950 用 ascend950
```

BI 脚本会：装 OBS 的 `cann-ops-batch_invariant-<A3|910b|950>-2.0.0-linux.<arch>.run` 到
`$ASCEND_HOME_PATH/opp/vendors/batch_invariant`，再编译 `batch_invariant_ops` wheel（本例 1.0.0）。
自检必须同时为真：

```python
torch.ops.batch_invariant_ops.npu_fused_infer_attention_score_batch_invariant.overloads()  # ['default','out']
hasattr(batch_invariant_ops, "_npu_fused_infer_attention_score_batch_invariant_get_max_workspace")  # True
```

