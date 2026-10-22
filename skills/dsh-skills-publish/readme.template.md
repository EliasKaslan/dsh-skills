# DSH Skills

本仓库是我本机 DeepSeek Harness（DSH）全部 skill 的只读镜像，由 `skills/dsh-skills-publish/publish-dsh-skills.ps1` 自动生成并推送，请勿手工修改（下一次同步会覆盖）。

## 分支约定

| 分支 | 含义 |
| --- | --- |
| `main` | 最近一次同步的完整快照，也是默认分支 |
| `<YYYY-MM-DD>` | 每日快照分支。每天凌晨 2:00 的同步会新建（或快进）当天日期分支，并让 `main` 与它指向**同一个 commit**，即内容逐字节一致 |

## 使用

```bash
git clone https://gitcode.com/EliasKaslan/dsh-skills.git
```

本仓库公开可克隆，但只有仓库所有者可以推送。需要改动请 fork 后自行维护，或直接 `git pull` 跟随每日快照。

## 清单

共 **{{SKILL_COUNT}}** 个 skill、**{{FILE_COUNT}}** 个文件、**{{TOTAL_BYTES}}** 字节。凭据文件（`credentials.txt`、`*.key`、`*.pem` 等）按规则排除，不入库。

| # | Skill | 说明 | 文件 |
|---:|---|---|---:|
{{SKILL_TABLE}}
