# lgtm / approve 权限来源：sig-info.yaml（AtomGit/GitCode 昇腾仓）

实测 2026-11-19，`Ascend/MindSpeed-Ops`。评审权限**不在仓库里**：仓内无 OWNERS/CODEOWNERS（`contents/` 均 404），`.gitcode/` 只有 workflows 与 `opensource-repo-layout.yaml`；`GET /repos/{o}/{r}/pull_request_settings` 返回的 repo 级 `approval_approvers`/`approval_testers` 本仓是空数组、`approval_required_reviewers=0`。

## 唯一来源

`Ascend/community`：`MindSpeed/sigs/<仓名>/sig-info.yaml`。匿名可读，`content` 为 base64：

```python
import json, urllib.request, base64
U = 'https://api.gitcode.com/api/v5/repos/Ascend/community/contents/MindSpeed/sigs/MindSpeed-Ops/sig-info.yaml'
d = json.load(urllib.request.urlopen(U, timeout=40))
txt = base64.b64decode(d['content']).decode('utf-8')
```

## 结构（模块怎么划分）

```yaml
committers: []            # SIG 级，MindSpeed-Ops 为空
reviewers: []
repositories:
- repo: [Ascend/MindSpeed-Ops]
  committers: [...]       # 仓库级模块（页面/口头常叫 repo-Ascend/MindSpeed-Ops）
  reviewers: [...]
  entry_configs:
  - path: [docs]
    committers: [...]     # docs 模块，名单常是仓库级的子集
    reviewers: [...]
```

- 模块 = 仓库级 + 每个 `entry_configs[].path`；只动 `docs/` 的 PR 只用 docs 名单。
- 同时改代码与文档的 PR，两个模块各要 1 lgtm + 1 approve。
- docs 的 committers 通常比仓库级少（更严），reviewers 可能反而更多（含外部文档检视人）。

## 判「为什么没打上 lgtm/approved」

1. 评论人 gitcode-id 必须逐字符匹配该模块名单，大小写敏感。
2. sig-info.yaml 改动合入后约 10min 权限才生效。
3. 评论时间必须晚于 PR 最新 commit，否则无效。
4. 命令表与排障问答：`Ascend/infrastructure` 的 `docs/robot/robot使用指南.md`（`/lgtm`、`/approve`、`/check-pr`、`/merge` 及各自所需角色）。

## 排除过的错误路径

- `GET /api/v5/repos/{o}/{r}/reviewer` → 405（只有 PUT，且是 repo 级单模块）；`/reviewers`、`/members`、`/approval_rules` → 404；`/orgs/Ascend/members` → 403（非 org admin）。
- `web-api.gitcode.com/api/v2/...` 从 Python 直连被 CloudWAF 拦成 **418**，但浏览器上下文 `fetch` 同路径返回 200/404 —— 探 web-api 端点走 Playwright `page.evaluate`。
