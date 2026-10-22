---
name: aidd-report-reader
description: 读华为 AIDD（aidd.huawei.blue）文档质量扫描报告并导出问题清单——gitcode OAuth 登录（DevUI 复选框要直接注入 Vue 状态）、REST API 免爬 DOM 批量拉 issues。适用于"检查 AIDD 扫描报告 / 解析 AIDD 问题 / 导出 issue 数据 / 登录 AIDD 抓文档质量检测结果 / 某个项目的扫描分数和 fatal 问题有多少"。不适用：不是 PR（提 PR 见对应 PR skill）、不是浏览器滑块验证码 → 用 `dingxiang-slider-captcha`。
whenToUse: 要访问 aidd.huawei.blue 检查 / 解析 / 导出"问题报告"，或抓某个项目（如 MindSpeed-Ops）的 AIDD 扫描结果时使用。模型看不到本节。
---

# AIDD 问题报告读取与解析

目标站点：`https://aidd.huawei.blue`（AI 智能文档检测系统）。**未登录访问报告页不是 HTTP 302**：SPA 对任意前端路由都返回 200（实测 `/`、`/login`、`/reports` 全是 200），跳转发生在浏览器里——所以**别用 HTTP 状态码判断登录态**，要看浏览器最终落在哪个路由。常用入口：报告列表 `/reports`、问题列表 `/issues`、项目报告 `/reports/projects/<proj_id>`。

## 何时调用

**加载本 skill 当：**
- 要看 / 解析 / 导出 aidd.huawei.blue 上的文档质量扫描报告（问题清单、score、severity）。
- 要登录 AIDD 并抓某个项目（如 MindSpeed-Ops）的检测数据，或问「有几个 fatal / critical」。
- 想知道报告在哪个接口、issues 明细字段有哪些（`/api/v1/reports/*`、`/api/v1/issues/global`）。

**不要用本 skill（转交）：**
- 要往 GitCode 提 / 修 PR → 用 `gitcode-pr-flow`；往 GitHub 提 PR → 用 `github-pr-flow`。
- 要自动化过滑块验证码 → 用 `dingxiang-slider-captcha`。
- 要 GitHub 组织增量追踪（基准日之后谁在动） → 用 `github-org-delta-watch`。

**前置**：有 gitcode 账号（用绑定邮箱登录）且能用 Playwright 打开浏览器。 ／ **后继**：按 severity / rule_name 聚合出问题清单（§3）。

## 1. 登录流程（gitcode OAuth）

1. 用 Playwright 导航到目标报告 URL，被重定向到 `/login` 后，点导航栏「登录」按钮打开弹窗，再点「gitcode 登录」。
2. 跳转到 gitcode.com（AtomGit）授权登录页。点「密码登录」标签，填入用户名/邮箱与密码。
3. **凭据注意**：gitcode 账号通常要用**账号绑定的邮箱**登录（用户名可能无效），密码**大小写敏感**。若返回 `400 LOGIN_BAD_CREDENTIALS`（`POST .../uc/api/v1/user/oauth/login`），先确认大小写再询问用户，不要盲目重试。
4. **协议复选框是最大陷阱**（见下节）。两个都勾选后点「登 录」。
5. 成功后经 `aidd.huawei.blue/third-login/callback` 回跳（可能停在 `/dashboard`），再导航回目标报告 URL。

### DevUI 复选框无法用常规点击勾选（关键经验）

gitcode 登录页底部的两个协议复选框（「用户协议和隐私政策」「数据共享」）是 vue-devui 的 `DCheckbox` 组件。**对 label/material/input 的任何 Playwright click、element.click()、check() 都只会翻转原生 input 的 checked 属性，Vue 的 model 永远不更新**——表现是：点「登 录」无网络请求，报"请阅读并同意用户协议、隐私政策和数据共享"。

原因（vue-devui 源码 `checkbox.tsx` / `use-checkbox.ts`）：组件在 `<label onClick={handleClick}>` 上切换状态；原生 `<input>` 的 click/change 被显式 `stopPropagation`，且 input 是 0×0 隐藏元素。自动化点击落在 label 内部子元素上时事件链与组件期望不一致。

**解法：直接调用 Vue 组件实例的 model 更新回调**。在 gitcode 登录页上下文执行（browser_evaluate）：

```js
() => {
  const app = document.querySelector('#app').__vue_app__;
  const rootVnode = app._container._vnode;
  const checkboxes = [];
  const seen = new Set();
  const visit = (vn, depth) => {
    if (!vn || typeof vn !== 'object' || depth > 40) return;
    if (vn.component) {
      const inst = vn.component;
      if (!seen.has(inst)) {
        seen.add(inst);
        const name = (inst.type && (inst.type.name || inst.type.__name)) || '';
        if (name === 'DCheckbox') checkboxes.push(inst);
        if (inst.subTree) visit(inst.subTree, depth + 1);
      }
    }
    if (Array.isArray(vn.children)) vn.children.forEach(c => c && typeof c === 'object' && visit(c, depth));
    if (Array.isArray(vn.dynamicChildren)) vn.dynamicChildren.forEach(c => visit(c, depth));
  };
  visit(rootVnode, 0);
  checkboxes.forEach(cb => {
    if (cb.props.modelValue !== true) {
      const h = cb.props['onUpdate:modelValue'];
      if (typeof h === 'function') h(true);
    }
  });
  return checkboxes.length; // 应为 2
}
```

判定成功的标志：`.devui-checkbox` 外层 div 的 class 从 `unchecked` 变为 `active`（不是看原生 input.checked，也不是看 material 背景色）。

**复验本解法的前提（前端升级后先跑一遍）**：在线上 bundle（`cdn-static.gitcode.com/assets/vendor-*.js`）里搜 `name:"DCheckbox"` 组件定义（`emits:["change","update:checked","update:modelValue"]`）、`DCheckboxGroup`、`devui-checkbox` class 与"用户协议/数据共享"文案，并确认 `#app.__vue_app__` 存在——这几条都在，才说明 vnode 树里按 `type.name === 'DCheckbox'` 找实例并调 `onUpdate:modelValue` 的前提仍然成立。（注意：**已登录时无法复看登录页**——`gitcode.com/login` 会直接跳回首页，要复验得在未登录会话里做。）

其他排查手段（已验证无效/有效的经验）：
- 无效：fill_form 的 checkbox、`label`/material/glow-box/长按、`input.click()`（会翻转 DOM 但破坏同步）、等待事件——trusted click/change 确实触发了，只是组件不监听 input 事件。
- Vue 生产版本不暴露 `__vueParentComponent`（元素上扫不到），只能从 `#app.__vue_app__` 的 `_container._vnode` 走 vnode 树。

## 2. 数据提取：优先走 REST API，不要爬 DOM

登录后所有数据都有干净 API，且页面 UI 是分页的（每页 20 条），API 一次可拉全量。

**鉴权**：API 需要 `Authorization: Bearer <token>`（cookie 无效）。token 在登录后的 `localStorage.authToken`（JWT）。在 aidd.huawei.blue 页面上下文里用 fetch 调用：

```js
const token = localStorage.getItem('authToken');
const headers = { 'Authorization': 'Bearer ' + token };
const r = await fetch('/api/v1/reports/tasks?project_id=<PROJ_ID>&page=1&page_size=100', { headers });
const data = (await r.json()).data; // { total, page, page_size, total_pages, items: [...] }
```

**端点清单**（均为 GET，返回 `{code, message, data, timestamp}`）：

| 端点 | 用途 |
|---|---|
| `/api/v1/reports/projects/<proj_id>/summary` | 项目统计：total_issues、severity_distribution（fatal/critical/normal/hint） |
| `/api/v1/reports/tasks?project_id=<proj_id>&page=1&page_size=100` | 该项目全部检测任务（每个文件一个 task）：task_id、filename、total_issues、severity_distribution |
| `/api/v1/reports/tasks/<task_id>` | 单任务完整报告：score（0-100）、level（优秀/良好/合格/待改进）、category_distribution、suggestions、rule_distributions |
| `/api/v1/issues/global?page=1&page_size=100&project_id=<proj_id>` | **全部问题明细**：description、category、severity、rule_name、original_text、suggestion、user_impact、processing.location（chunk 定位） |

注意：
- `page_size=100` 足够覆盖单项目；若 total > 100 需翻页。
- issues 接口的 `project_id` 过滤参数实测有效（total 与项目 summary 一致才可信）。
- task 详情里没有 issues 数组，问题明细只在 `/api/v1/issues/global`。
- 探测未知端点时留意（实测）：**漏 token → 401** `{"detail":"Authentication required. Please provide either Bearer Token or X-API-Key header."}`；**未知路径 → 404** `{"detail":"Not Found"}`。用这个区分"端点还在但没带 token"和"端点没了"。四个文档化端点（`summary` / `tasks` / `tasks/<id>` / `issues/global`）不带 token 时全部返回 401，端点均在线。
- **全站 API 突然全 502 时不要判定端点下线**：实测出现过所有 `/api/v1/*`（连伪路径也）统一 502 的窗口，几分钟后自行恢复成 401。502 = 后端短暂不可用，等一会儿重试即可；只有 404 才说明路径真的不存在。

**从页面找 API 的技巧**：导航到对应页面（如 `/issues`），用 `browser_network_requests` 过滤 `api/v1`，直接抄前端真实调用的 URL 和参数。

## 3. 数据结构速查

- task: `{task_id, filename, file_id, total_issues, resolved_issues, severity_distribution, created_at, completed_at, creator_name}`
- issue: `{issue_id, task_id, filename, file_display_path, category, severity(fatal|critical|normal|hint), rule_name, description, original_text, suggestion, user_impact, processing: {location: {start_pos, end_pos, chunk_id}}}`
- report: `{score, level, severity_distribution, category_distribution[], suggestions[], rule_distributions[]}`

分析产出建议：按 severity / rule_name / category 聚合计数；按文件分组列问题；单独提取 fatal+critical 明细；归纳"共性问题模式"（如术语大小写批量替换、复制粘贴残留注释）与"疑似误报"（描述与建议矛盾的条目，如 epsilon 拼写问题）。

## 4. 浏览器共享与稳定性注意

- Playwright 浏览器可能与用户并行使用（标签页会被切走/导航，`browser_evaluate` 会报 "Execution context was destroyed" 或 window 变量丢失）。
- 对策：用 `browser_tabs action:new` 开**专用标签页**做数据提取，别占用用户正在看的标签；把全量数据一次性 `window.__xxx = ...` 缓存后分块返回（每次 evaluate 返回 ≤ 20 条明细，避免截断）；提取前检查 `window.__xxx` 是否还在，丢了就重新 fetch。
- 不要关闭不属于自己的标签页；结束后只关自己开的那个。

## 5. 公网地址 / 敏感词扫描报告 → 仓库交付件映射与核查口径

（同事给的华为扫描报告也是 xlsx：`Summary` / `WordSummary` / `Detail_1` 三个 sheet。）

**术语是华为内部扫描器口径，公网无词条**：`web_search` 直搜 `公网地址声明` 只会返回 AWS/Aliyun 英文文档，**必须加限定词**（`"公网地址声明" 昇腾`）才命中真实先例 `gitee.com/ascend/MindSpeed-LLM/pulls/1710`（「补充公网地址声明」，已合并；`.diff` 免登录可直下，可作口径标杆）。

**「公网地址声明」不是独立文件、也不是平台白名单**：它是 `SECURITYNOTE.md` 里的一个固定章节 `## 公网地址声明`，5 列表 `类型 | 开源代码地址 | 文件名 | 公网IP地址/公网URL地址/域名/邮箱地址 | 用途说明`。`SECURITY.md` / `PUBLIC_NETWORK_ADDRESS*` / `NOTICE` / `OAT.xml` 实测**全 404**（别去找这些文件名）。各仓实际路径不统一（实测有的在根目录、有的在 `docs/zh/`、有的没有）→ 定位必须先列目录再取文件（命令见 `gitcode-pr-flow` §6.2.1）。

**正确判据 = 覆盖缺口，不是文件是否存在**：取扫描报告的 `Detail_1` 表（列 `B=Scaned Object`、`Q=Match Postion`、`R=Match Content`、`L=敏感词`）拿到逐条 `文件:行号`，再与声明表逐条对账——"文件在、章节在"**不能**推出"声明齐全"。

**报告一定会漏报**：用 `git grep -n -I -E 'https?://|ftp://|www\.'` 全量重取后的命中数**大于**报告给出的命中数；而且**漏的粒度不止行——整个域名都可能整段缺席**（实测漏过一个代码托管域名下的全部命中）。→ **不要用报告的命中数当分母**，必须以全仓 grep 为准再对账（两类漏报的兜法见本节末"对账判据"）。

**xlsx 直读（不需要 openpyxl）**：`Summary` / `WordSummary` / `Detail_1` 三个 sheet；`WordSummary` 的 `G` 列是敏感词分组 JSON（`groupCnName` / `groupEnName` / `source`），`Detail_1` 的 `L/M/N` 是敏感词本体/类型/说明、`Q` 是 `{"Line":N}`。用 Python `zipfile` + `xml.etree` 直读 `xl/sharedStrings.xml` + `xl/worksheets/sheetN.xml`（共享字符串表 + 单元格引用）即可。

**最小改动口径**：只改 `SECURITYNOTE.md` 里**既有表格**（补行 + 修正过窄的行号区间），**不新建文件**；**不要**把"补声明"做成"删代码里的 URL"。先例 MindSpeed-LLM PR !1710 的口径 = 「构建必需的地址登记进表，示例性的公网 `wget` 注释删除」；模板标杆 `Ascend/pytorch/SECURITYNOTE.md`（按文件聚合、一行一地址）。

**交付纪律**：表格里多 URL 单元格**拆成一行一地址**，**不要用 `<br>`**（内联 HTML 有触发文档门禁的风险）。

**扫描口径 ≠ 全仓口径（最容易把活做超的地方）**：华为这个代码扫描器**不扫 markdown、不扫 `.py`、不扫 `.cpp/.h`、不扫 `LICENSE`**，只命中**构建 / 配置 / 脚本类文件**（`.yaml` / `.yml` / `Dockerfile` / `.sh` / `.cmake`）。因此「公网地址声明」**只应覆盖扫描口径内的文件**：把 `docs/**.md` 里的超链接、源码许可证头注释里的地址也塞进声明表，属于**口径放大**——既超出扫描范围，又**给文档门禁引入坏链**（URL 可达性硬规则见 `gitcode-pr-flow` §6.5）。
→ **判据：声明表的行数应对齐"扫描器真会命中的文件"**，而不是"仓库里所有出现过的 URL"。范围不确定时先按文件类型复算一遍，再决定加不加行。实测按此判据把声明表收窄到"只列扫描口径内的文件"后，文档门禁随即转绿。

**对账判据与做法（先对账，再改表）**：判据是「扫描报告 `Detail_1` 的**逐条 `文件:行号`** 是否都能在声明表里找到」——**不是**"文件在、章节在"就能收工。并且**必须用 `git grep` 全量重取后再对账**，不要采信报告的命中数（见上一条"报告一定会漏报"）。遗漏有两类，都要分别兜住：**行级漏报**（某个配置文件里的 URL 没进报告）与**域名级漏报**（整个域名的命中全都不在报告里）。

## 6. 维护记录

**复验清单（怀疑站点或接口变了，就按这三条跑一遍，别凭印象下结论）：**
1. **站点可达性** → 未登录状态导航到目标报告页，看浏览器最终落在 `/login` 还是报告路由（**不要看 HTTP 状态码**，SPA 对任意前端路由都返 200）。
2. **API 在线** → §2 四个文档化端点（`summary` / `tasks` / `tasks/<id>` / `issues/global`）不带 token 应回 **401**；回 **404** 才是端点没了（全站 502 的判别见 §2 最后一条）。
3. **登录解法前提** → 按 §1「复验本解法的前提」在**未登录**会话里搜线上 bundle，四条特征都在才说明 DevUI 注入法仍可用。
