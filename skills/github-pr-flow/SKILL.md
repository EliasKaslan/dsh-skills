---
name: "github-pr-flow"
description: "GitHub/GitCode PR 交付与 CI 核验：提 PR、改正文、修冲突、看红。适用于\"提PR / 改PR正文 / CI为什么红 / 修PR冲突 / 处理评审意见\"。不适用：仅审版本差异 → git-tag-diff-audit。"
whenToUse: "处理GitHub及GitCode PR交付、评审处置与当前head的CI核验时加载；模型看不到本节，触发以description为准。"
---

# PR / MR交付与门禁

## 何时调用

**触发**：帮我提PR / 更新PR正文 / CI为什么红 / 处理评审意见 / 修PR冲突。

**转交**：仅审版本实质差异见 [git-tag-diff-audit](../git-tag-diff-audit/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

用当前已配置的DSH连接器或进程级认证处理API，先发现schema与权限，先核对账号、规范远端、base/head和用户请求。旧skill记录的账号、CLA、免确认compile评论、强推/合并权限不构成本次授权；不为探权限向创建端点发试探写请求，也不按token前缀断定能力。

读目标仓AGENTS/CONTRIBUTING、PR模板、提交身份/DCO/CLA、title和lint规范。保护用户未提交改动；分支基线/工作树/暂存区分开检查。修正身份先确认CLA/DCO绑定邮箱，不能为过检查伪造他人身份。commit消息用UTF-8文件，检查实际提交tree、message与diff。

推送使用无凭据远端URL和进程内认证。push超时先查远端ref，避免重复写入；收到失败或权限错误先辨认证/策略/限流/网络。冲突前确认历史深度和merge-base，不用allow-unrelated-histories掩盖浅历史；保留两侧语义，不能整块theirs覆盖已合入修复。仅在本次已允许改写历史时对确切分支使用带期望SHA的lease；不强推共享分支或重指release/tag来“整理版本”。

PR标题/正文描述最终问题、结果行为和相关验证，保留仓库机器人管理字段；范围变化时同步更新。创建/更新后回读base/head/title/body，检查中文/换行、完整分页files和实际diff；hash不同可能因换行clean filters，要比较提交blob或受控规范化结果，不能悄悄抹掉语义差异。

CI按当前head SHA、run/job、配置和所有必需车道核对。PR标签、旧机器人评论与“最近一次绿”不足以证明当前提交通过。GitCode compile/retry、GitHub /e2e 等评论会通知他人并消耗CI资源，只按本轮仍有效的用户明确授权发送；写后回读评论及派生run。避免重复触发，重试有截止和停止条件。

失败先读首个失败step及原始日志，对同head基线区分确定回归、既有问题、flaky与基础设施。相同commit有一绿一红只证明不稳定，不直接判平台故障；也不能统一SKIP gitleaks/bandit或把缺工具当通过。取消/skip/no-tests与失败分别记录，按合入策略判断必需证据是否齐。

收齐普通评论、inline review与review总结，逐条确认实际触发条件；机器人建议不是事实。合理修复后补对应回归，误报用源码/实验解释。回复评审或解决线程仍须本次沟通授权。作者不能自批所需审批，不能用标签冒充维护者认可。

交付PR链接、完整head、改动/验证/未覆盖、当前门禁与需要维护者动作。创建PR不自动授权合并、发release、回合并版本分支或给其他人发消息；已授权的交付步骤直接完成，不重复增加确认流程。

来源：DSH github-pr-flow、gitcode-pr-flow及其3份历史reference；2026-11-16去除固定仓权限、凭据URL、平台接口与门禁时延假设。具体API/标签从目标仓当前规范和一手文档读取。

## 跨 fork 提 PR 被 403：先读 x-accepted-github-permissions

分支能 push 成功、`GET /repos/{base}` 显示 `permissions.pull=true`，都不代表能建 PR。fine-grained PAT 只被授权到自己的 fork 时，`git push` 与读 base 仓都正常，只有写 PR 会被拒：

```text
HTTP 403 POST /repos/{owner}/{repo}/pulls
{"message":"Resource not accessible by personal access token",
 "documentation_url":"https://docs.github.com/rest/pulls/pulls#create-a-pull-request","status":403}
```

判据看响应头而不是猜账号权限：`x-accepted-github-permissions: pull_requests=write` 就是缺这一项（`GET /repos/{base}` 的 `permissions` 里 `pull: true` 只是可读）。对照 `GET /repos/{fork}` 看 `permissions.admin/push`，能立刻分辨「令牌只覆盖 fork」还是「账号本身无权限」。

出路三选一，按代价排序：

1. 换一份对 base 仓有 `pull_requests: write` 的凭据（classic 令牌的 `repo` scope 也够）。别自行给现有令牌提权。
2. 把 compare 链接交给用户点一次：`https://github.com/{owner}/{repo}/compare/{base}...{forkOwner}:{branch}?expand=1&quick_pull=1&title=<quote>&body=<quote>`，title/body 用 `urllib.parse.quote(..., safe="")` 编码，4KB 量级的 body 仍可用。用户提交后回读校验。
3. 浏览器代点前先确认当前 URL、页面已加载及登录状态（登录入口/用户菜单、页面快照，必要时用已授权只读 API）。`mcp__playwright__browser_find` 找不到 “Create pull request” 只记“按钮未发现，原因未知”，不得单独据此判定未登录，也不要盲目反复重试。

push 侧不要为绕开这个问题把令牌塞进 URL 或 `.git/config`。用进程级环境变量传认证头：

```python
env.update({"GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + base64.b64encode(b"x-access-token:" + token).decode()})
subprocess.run(["git", "push", "https://github.com/{fork}.git", f"{local}:refs/heads/{remote}"], env=env)
```

坑：

- fork 名可能不等于仓名（`<user>/<repo>` 不存在时先读既有 PR 的 `head.repo.full_name`，或 `GET /repos/<user>/<repo>` 一个个试），别假设。
- `git push` 时本地分支名与期望的远端分支名不同，refspec 要写 `{local}:refs/heads/{remote}`；直接写远端名会得到 `src refspec ... does not match any`。
- 建 PR 后必须回读 `base.sha`/`head.sha`/`changed_files`/`additions` 与本地 `git rev-parse`，机器人还会自动加标签、补 `- vLLM version:` 尾行。

## CI 门禁红：先分「等评审」与「真失败」

`codeowner-approval` 类的失败常常不是脚本坏了，而是审批没到位。判读顺序：

1. 先看 gate 脚本而不是 job 日志。vllm-ascend 仓内 `.github/workflows/scripts/codeowner_gate.py` 的 `check_approvals()` 写清了规则：PR 改到的每个文件都要有该路径 CODEOWNERS owner 的 APPROVED；没有 owner 的路径（`unclaimed`）与「作者本人是唯一 owner、无法自批」（`self_owned`）按策略只记 notice，不算门禁失败。读这一段就能得到 "waiting for approval from one of: ..." 的准确含义。
2. 自建 check 的 `GET /repos/{o}/{r}/check-runs/{id}` 经常 `output.summary` 为空、只给 conclusion（实测 codeowner-approval 就是空 title/summary）。空 summary ≠ 失败原因缺失，去读仓里的 gate 脚本或 workflow，比下载 job 日志快得多。
3. 找 owner 用 CODEOWNERS 语义解析被改路径：gitignore 式前缀匹配 + **最后一条匹配规则生效**，别用一条通配拍全体；`/docs @someone` 这种粗规则通常就是文档 PR 的实际 owner。
4. 汇报时把「等谁的 approve」单独列出来，与「真的失败」分开；`cpu-ut`/矩阵类 check 仍在跑时也照实写，不要把 pending 说成绿。

请求 codeowner 评审会给人发通知：这是对外的写操作，按本次沟通授权决定发不发，别默认代发。

## 双 PR

[模拟顺序](references/pr-order.md)
