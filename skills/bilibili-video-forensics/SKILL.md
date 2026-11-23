---
name: bilibili-video-forensics
description: B站视频取证：412 风控下用浏览器上下文调 API 拿标题、统计、评论、弹幕与封面
---

# B 站视频取证（412 风控绕行）

## 何时调用

用户拿 B 站某个 UP 的实测视频当证据（"某 UP 今早发了 X 模型的视频"），或要判断"一条没写模型名的测试视频到底测的是谁"。不适用：只想看榜单分数 → 用 [llm-landscape-recon](../llm-landscape-recon/SKILL.md) 的第三方榜路径。

前置：`api.bilibili.com` 直连与 `space.bilibili.com` 在本机一律 412（补 UA/Referer、buvid3/buvid4、WBI 签名都无效；`search/type` 头两次可用，连续请求后也 412）。不要在这上面反复试错。

## 唯一可用通路

1. 调用当前 Playwright 工具 `mcp__playwright__browser_navigate`，参数 JSON 为 `{"url":"https://www.bilibili.com/"}`；实际以当次会话 schema 为准。
2. 在**该页**上下文里 fetch（从 www 页发起才不被 CORS 挡，直接对 api 域名 fetch 会被拦）：

```js
fetch('https://api.bilibili.com/x/web-interface/view?bvid=BV1vwsY67ED9',
      { credentials: 'include' }).then(r => r.json())   // code: 0
```

3. 字段：`title / ctime / stat{view,like,reply,danmaku} / pic / aid / cid / desc / desc_v2`。`pubdate` 可能为 0，**用 `ctime`**。
4. 封面 `pic` 是 https CDN 直链（示例域名 `i0.hdslb.com`，不是本地路径），下载后 `read_image` 看画面风格（3D/前端/体素）。

## 端点清单（同一页面上下文）

| 用途 | 端点 |
|---|---|
| 顶层评论（按赞） | `/x/v2/reply?type=1&oid=<aid>&sort=2&ps=20&pn=1` |
| 热门 / 置顶 | `/x/v2/reply/main?oid=<aid>&type=1&mode=3` |
| 楼中楼 | `/x/v2/reply/reply?type=1&oid=<aid>&root=<rpid>` |
| 弹幕（XML） | `/x/v1/dm/list.so?oid=<cid>` |
| 章节 / 字幕 | `/x/player/v2?cid=<cid>&bvid=<bvid>` |
| 找 UP 的 mid | `/x/web-interface/search/type?search_type=bili_user&keyword=<名字>` |

## 搜索某 UP 的视频候选

`space.bilibili.com` 走不通时改搜索页（可正常打开）：`https://search.bilibili.com/all?keyword=<UP名>`，再解析：

```js
[...document.querySelectorAll('.bili-video-card')].map(c => ({
  bv: c.querySelector('a[href*="/video/BV"]').href.match(/BV\w+/)[0],
  title: c.querySelector('.bili-video-card__info--tit').getAttribute('title')
}))
```

上述结果仅为候选：须核对作者与已确认 mid、取发布时间（同 pubdate/ctime 口径），作者一致且时间与分页覆盖闭合才称“最新”，否则只能说“窗口内候选”。

## 判据与坑

- 判“未公布模型的测试视频”：标题不含型号、desc/tags/章节/字幕为空及 UP 既往习惯，仅支持“本次未发现公开型号，原因未知”。厂商、UP 或可核验公告明确提到 NDA 时，按来源写“据×称受 NDA 限制”；不得仅凭阴性线索断言 NDA，也不得用“否则只是普通评测”排除其他原因。
- 评论区是重要线索源：高赞长篇常在做排除法（配色/体素风格/z-fighting 特征），把"排除项"和"倾向项"分开记。
- reply 接口默认只回 3 条顶层高赞；总 `reply` 数含楼中楼，继续翻页通常仍是空。
- `view` 返回 `code=0` ≠ 视频页能打开（视频页仍 412）；元数据够用就不要硬拉视频流。
- 站外代理（`r.jina.ai`、`api.allorigins.win`）对该站失败（fetch failed / 522），别浪费轮次。
