# 两条重叠 PR：验证优先合入顺序

1. 用 `git ls-remote` 同时读取目标分支和两个 PR 的 head 引用；REST `base.sha` 可能落后于目标分支。把当前 PR 相对目标分支的文本冲突与两条 PR 顺序合入后的语义问题分开。
2. 隔离副本中运行 `git merge-tree --write-tree <base> <priority-head>`，干净时拿到优先 PR 的合并树；用 `git commit-tree <tree> -p <base> -m <message>` 构造仅本地 squash 基线，在隔离分支 `git merge --no-commit --no-ff <other-head>`。
3. 即使 Git 返回 0，也要核对同名方法、旧签名和测试夹具，避免重复定义覆盖或旧测试使用过时的数据表示。验证最终树及双方回归断言。模拟历史不能推送。
4. 若先发布实际主线冲突的修复，在自己的 PR 明确合入顺序，并回读当前 head 及 mergeable。冲突标签可能滞后，`mergeable=true` 也不是 CI 或评审门禁通过。
