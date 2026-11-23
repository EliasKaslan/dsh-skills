# CI 门禁镜像配套：六处对齐清单、SWR 可拉性探测与 GitCode 验证归因

## 六处必须一起改

1. `.gitcode/workflows/pr-pipeline-mindspeed-ops.yml` 的 `UT_MindSpeed_1~4` 四处 `container.image`
2. `ci/Dockerfile` 的 `BASE_IMAGE_VERSION` / `TORCH_NPU_VERSION` / `TRITON_ASCEND_VERSION`
3. `ci/build.sh` 默认值（含 `TRITON_ASCEND_WHL`；该参数当前未被 Dockerfile 消费，但留旧值会误导）
4. `requirements.txt` 与 `pyproject.toml` 的 `triton-ascend==` pin
5. `docker/Dockerfile`、`docker/image_build.sh` 发布镜像配方（与 ci/ 是两套，可分批；注意发布分支上的值可能才是对的）
6. `docs/*/install_guide.md`、`docker/OVERVIEW*`、`supported_tags.md` 的版本表（含正文里「requirements.txt 固定 X 版本」这类叙述句）

## SWR 匿名探测（真能拉才算数）

```python
# 1) 直接取 manifest 会 401，从 WWW-Authenticate 拿 realm
GET https://<host>/v2/<repo>/manifests/<tag>
# 2) 换匿名 token
GET <realm>?service=dockyard&scope=repository:<repo>:pull      -> {"token": ...}
# 3) 带 Bearer 重取 manifest / 列全部 tag（Accept: manifest.list.v2+json, oci.image.index.v1+json）
GET https://<host>/v2/<repo>/manifests/<tag>
GET https://<host>/v2/<repo>/tags/list
# 4) 取 config blob 看 Env / history：架构、User、Python、CANN、torch/torch_npu/triton、装过哪些 gcc/cmake/ninja
```

判读：
- 官方社区镜像在 `swr.cn-south-1.myhuaweicloud.com/ascendhub/<产品>`，tag 按 `版本-cann-torch_npu-芯片-系统-py` 组织，**没有 arch 段**（多架构 manifest）；自建 tag 才带 `-{arch}`。
- 四项预检：`User=root`、history 里有 gcc/gcc-c++/make/cmake/ninja-build、`/usr/local/Ascend/nnal/atb/set_env.sh` 存在、`WORKDIR` 里可能有旧 checkout。
- 镜像内若只有 `pip install -e /workspace/<repo>`，UT 脚本在 `CODE` 重装 editable + `PYTHONPATH` 后不遮源码；只有跳过该步的 job 才有遮蔽风险。
- **`cat /usr/local/Ascend/ascend-toolkit/version.cfg` 不存在**（`latest/version.cfg` 也没有）；版本在 `/usr/local/Ascend/ascend-toolkit/latest/*/ascend_toolkit_install.info`。
- triton wheel 索引 `https://triton-ascend.osinfra.cn/pypi/simple/triton-ascend/` 是目录页（200 + html，假 200）；真实包 301 到 `repo.huaweicloud.com/ascend/repos/pypi/triton-ascend/`。

## GitCode 门禁的三个坑（2026-11 实测 PR#278）

1. **评论触发的 PR 流水线跑默认分支侧 workflow**：run 的 `head_sha` 是 PR 分支的底座，不在 head 上；四个 UT job 派发的 `container.image` 仍是旧 tag。取证端点（匿名可用）：
   `GET https://web-api.gitcode.com/api/v2/projects/<o>%2F<r>/actions/workflow-runs/<run_id>`
   查 `head_sha` / `is_real_execution` / `exist_in_default_branch` 与每个 job 的 `resource.container.image`；再对 head/base/预合并三份 workflow 做 sha256 比对确认用的是哪份。
   `api.gitcode.com/api/v5/.../actions/runs/...` 匿名 401，job 日志需登录 → 逐条 pytest 计数拿不到属正常。
2. **预合并 ref 建在旧底座**：`refs/merge-requests/N/merge` 的两个 parent 可能停在 PR 创建时的 master，缺之后合的修复（实测 `b229041` 的 TA3.6 规避缺失 → 单文件 18 passed 变 17 failed，容易被误判成 PR 引入）。
3. **官方镜像按芯片段打算子包**：同一次 26.2.0 构建里，910b tag 的 `kernel/ascend910b` 4.6G、`ascend910_93` 仅 5.4M，a3 tag 反过来。装错段后任何 aclnn 算子报 `561103` / `JSON configuration file of operator aclnnXxx cannot be found`。

没有目标芯片的机器时：用同版本另一芯片段 tag 代跑全量 UT（要 `--privileged --ipc=host --network host`，关 ip_forward 的机器 bridge 下 pip/git 全废；不要 `--pid=host`，UT 脚本里有 `ps -ef|grep python|xargs kill -9`），结论里明确「不是同一份算子包」。
