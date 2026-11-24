# `git push` 在本机的两类坑

## 1. 假红：命令成功但退出码是 1

- **stderr 包装**：PowerShell 5.1 把原生命令写到 stderr 的每个字节包成 `NativeCommandError`，工具层报 `[exit code: 1]`。git 把进度/摘要写 stderr，所以几乎每次 `git push` 都会命中。逐字特征：
  ```text
  git : To https://<host>/<owner>/<repo>.git
      + CategoryInfo          : NotSpecified: (To https://...:String) [], RemoteException
      + FullyQualifiedErrorId : NativeCommandError
     <old>..<new>  main -> main
  ```
  同一段输出里已经有 `main -> main` —— 那是成功。
- **管道提前关闭**：`<cmd> 2>&1 | Select-Object -Last N` 读够 N 行后就关管道，原生命令继续写 stderr 拿到 EPIPE，退出码变 1。对照：`<cmd> 2>&1 | Out-Null; $LASTEXITCODE`。
- 真失败会带非零退出码**且没有产物**，或报 `fatal:` / `error:`。

## 2. 真挂住：远端可能已经更新

症状：`git push`（含 `--dry-run`）几分钟到几十分钟不返回、进程零 CPU；同一时刻 `git ls-remote` 秒回；杀进程重试仍然挂。

判据：`git ls-remote <remote> main`；tag 比 `refs/tags/<t>^{}`（看 `^{}` 那一行才是它指向的提交）。

### 三步把责任分开

1. 远端有没有（上一步，唯一判据）。
2. 网络与端点——绕开 git 与凭据：
   - `https://<host>/<owner>/<repo>.git/info/refs?service=git-upload-pack` → 期望 200
   - 同 `service=git-receive-pack` → 未带凭据时 401 属正常
   两者都秒回 ⇒ 网络与服务器没问题，问题在本机。
3. 凭据助手——`git -c credential.helper= push --dry-run <remote> <branch>`：若 1 秒内报
   `fatal: could not read Username for 'https://<host>': terminal prompts disabled`，阻塞点就在 helper（Windows 上是 `wincred`）。

### 修法：把用户名写进推送 URL

凭据条目键**带用户名**（`cmdkey /list` 可见 `git:https://<user>@<host>`），而 `origin` 的 URL 是 `https://<host>/<owner>/<repo>`——没有用户名，匹配不到已存条目，helper 卡在一个永远不会来的输入上。

```powershell
git -c http.version=HTTP/1.1 push https://<user>@github.com/<owner>/<repo>.git main
git -c http.version=HTTP/1.1 push https://<user>@github.com/<owner>/<repo>.git v1.2.3
```

比换 `credential.helper=manager`（要交互登录）省事。

### 边界

- 不要把令牌写进 URL 或 `.git/config`；不要用"关掉 helper / 允许交互提示"当解法。
- 同一台机器上另一个远端可能完全正常：helper 按 host 存条目，一个 host 坏了不代表网络坏。
- 推完两个远端逐个复核：`git ls-remote <r> main` 与本地 `git rev-parse HEAD`；tag 比 `^{}` 解引用。**"命令没返回"与"没推上去"是两件事。**
