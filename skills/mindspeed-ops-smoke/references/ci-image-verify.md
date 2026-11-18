# CI 门禁镜像配套：六处对齐清单与 SWR 可拉性探测

> 本节由 SKILL.md 正文逐字移出，未改写；六处位置、探测命令与镜像判读细则均为原文。

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

- 官方社区镜像在 `swr.cn-south-1.myhuaweicloud.com/ascendhub/<产品>`，公开可匿名拉；同名 tag 按 `版本-cann-torch_npu-芯片-系统-py-架构` 组织，芯片段必须与 runner 实际硬件一致（`910b` / `a3` / `950` 各段都有）。
- 官方发布镜像可直接当 UT 容器前的四项检查（本仓 26.2.0 的 910b py3.12 镜像实测满足前三项）：`User=root`、history 里有 gcc/gcc-c++/make/cmake/ninja-build、`/usr/local/Ascend/nnal/atb/set_env.sh` 存在、WORKDIR 里已有代码 checkout（可能影响 checkout 步骤落入非空目录）。仍未验证的是 `torch.npu.is_available()` 与 CATLASS UT 实跑。
- 用官方发布镜像跑 PR UT 还要确认：镜像内已装的 `mindspeed_ops` 会被 `pip install -e .` 覆盖，否则可能跑发布版代码得到假绿。
