---
name: korea-official-source-research
description: 韩国（济州）官方一手信息源——官方页面怎么抓、没日期怎么看：web_fetch 对韩国站点多数不可用，urllib 按站点分档，pwsh 最稳；含出入境/入境申告官方源结构（e-AC 的 bbsId / flId、mofa.go.kr 详情页、无日期戳用响应头 Date 与 등록일 定锚、判废止）、假页面陷阱、公交 BIS、visitjeju、休馆日、门票 xlsx、潮汐。适用于"韩国出入境/入境申告/法务部/关税厅/检疫 Q-CODE 官方源怎么抓 / 韩国官方页面没有日期怎么看 / 驻外使馆 mofa.go.kr 详情页怎么取 / 政策是否已废止怎么查 / 查济州公交线路和末班车 / 韩国景点开放时间与休馆日 / 抓 visitjeju 详情页字段 / 门票 xlsx 怎么解析 / 潮汐表怎么取 / 抓韩国站点全失败怎么办"。不适用：本机 pwsh 编码坑 → 用 `pwsh-on-windows`；判厂商官网链接真假 → 用 `ai-vendor-official-source-audit`。
whenToUse: 要拿韩国官方一手数据（出入境/入境申告、公交时刻、景点与店铺营业时间/休馆日、门票、渡轮、潮汐）时用：先按站点量本机可达性（web_fetch / python urllib / pwsh 三级），再按端点配方抓取。模型看不到本节。
---

# 韩国（济州）官方一手信息源：抓取通道与端点配方

实测环境：Windows + DSH（`web_search` 可用；`web_fetch` 对本主题韩国站点普遍不可用，`python urllib` **按站点分档**——`koreatourinfo.com` / `visitjeju.net` 实测可通；`bus.jeju.go.kr` 旧实测报 `WinError 10060`，但可达性会漂移，须现测）。目标：拿**官方**的公交线路/末班车、景点与店铺营业时间、休馆日、门票、渡轮、潮汐、出入境政策等**现行**数据，而不是二手转述。

## 何时调用

- **触发信号**：用户要韩国/济州的官方数据（公交、末班车、开放时间、休馆日、门票、渡轮、潮汐、**出入境/入境申告政策**）；或 `web_fetch` 抓韩国站点成片失败、`403`、`WAF`；或 "这站到底有没有官方数据"；或"**这政策还在生效吗 / 是不是已经废止了**"、"韩国官方页面没有日期怎么定时间"。
- **转交边界**：本机 pwsh 命令自身的坑（编码、BOM、二进制、别名撞名、PS7 语法） → 用 `pwsh-on-windows`。
- **前置**：`pwsh` 工具可用（`web_fetch` 多数站点不可用、按站点分档，见前置检查）。 ／ **后继**：结论按"官方 URL + 抓取通道 + 官方原文片段 + 状态码/字节数"落盘；官方确实没给的字段（如站间耗时）明确写"官方不提供"，不要用估计值冒充实测值。

## 前置检查：先量本机可达性，别默认 web_fetch 能用

对目标站先做一次"web_fetch → python urllib → pwsh 直连"三级探测，记录**状态码 + 响应体长度 + `<title>`** 三连。本机实测矩阵（结果按通道分档；未标注通道的历史行多来自 `web_fetch`，勿当成"python 也不通"）：

| 站点 | 本机探测结果（通道见括号） | 可用替代 |
| --- | --- | --- |
| `bus.jeju.go.kr` | web_fetch `Error: fetch failed`；python `URLError <urlopen error [WinError 10060] …>`（**旧实测；复测首页 python urllib 已 200**） | **pwsh 直连可通**（端点仍以现测为准） |
| DuckDuckGo HTML / Naver / `r.jina.ai` | WinError 10060；Naver 另返 `HTTP Error 403: Forbidden` | 换 `web_search` |
| Bing | **HTTP 200，但内容是不相关的缓存页**（曾返回 "Fix Bluetooth problems in Windows"）← 假成功 | 不采用 |
| `map.kakao.com` / `nominatim.openstreetmap.org` | `net::ERR_CONNECTION_TIMED_OUT` / 无法连接 | Naver Directions API（下） |
| Overpass | 间歇 `(429) Too Many Requests` / `(504) Gateway Timeout` | 加间隔重试 |
| `jejusi.go.kr` / `council.jeju.kr` | 被 WAF 拦：`contrary to the Web firewall security policies … blocked` | 找同级官方替代站 |
| `namu.wiki` / `konest.com` / `www.hallimpark.co.kr` / `www.kkday.com` / `bestwestern.com/co.kr` | 403 / 406 / 403 / Cloudflare 403 / `403 Please enable JS` | 只用官方站 |
| `jeju.go.kr/download.htm` | `timed out after 120000ms` | 换同级官方站 |
| `siksinhot.com` | 403（CloudFront 拦截） | 换官方/镜像站（见第 2b 条） |
| `nate.com` | `SSL hostname mismatch` 握手失败 | 不用 |
| `daum.net` | 超时 | 不用 |
| `koreatourinfo.com` / `visitjeju.net` | **web_fetch 不可用，但 python urllib 实测可通**（分档反例，别一刀切） | python urllib 或 pwsh 直连 |
| `www.e-arrivalcard.go.kr`（e-AC） | **HTTP 200，body 为服务端直出的 `<div class="vtBody contentPre">`**（详情页正确 URL 下） | python urllib / pwsh 直连 |
| `us-losangeles.mofa.go.kr`、`overseas.mofa.go.kr` 系列 | HTTP 200，正文是外交部门 404 页（`<title>페이지를 찾을 수 없습니다…`，约 1557B）← 假成功 | 用**正确域名段**（见第 8 条） |
| `www.mofa.go.kr` | 未验证：本次未直接抓取该主域 | 三级探测后再定 |

**按站点分档（修正）**：`web_fetch` 对韩国站点**普遍**不可用（403 / 超时 / SSL 不匹配 / WAF），但**不是全都不可用**——`python urllib` 对 `koreatourinfo.com`、`visitjeju.net` 实测可通，能省掉 pwsh 中转（复测：两者分别返回 200，响应体 18 万 / 158 万字节）。反向的坑同样要防：本 skill 里 `bus.jeju.go.kr` 的旧记录也是**假设不是结论**——复测其首页 `python urllib` 返回 200，说明可达性**随时间和路径漂移**（首页通 ≠ 私有端点通，反之亦然）。结论永远是**当次逐站点实测**（状态码 + 响应体长度 + `<title>`），"韩国站一律打不通"这类整类断言已被证伪，别再写也别再信。

**可用通道**：`pwsh` + `Invoke-WebRequest -UseBasicParsing` / `System.Net.WebClient` **直连官方站**——仅 `bus.jeju.go.kr`、`visitjeju.net`、`access.visitkorea.or.kr`、`kdfa.or.kr` 实测都能通（`web_fetch` 对 `access.visitkorea.or.kr` 报 `TypeError: fetch failed`，必须 pwsh）。打车距离/车费走 Naver Directions API：`map.naver.com/p/api/directions/car`（返回 JSON）。

抓取通道本身的编码 / 二进制写法（WebClient 编码、`DownloadData` 存 zip/xlsx、别名撞名） → 用 `pwsh-on-windows`，本 skill 不重复。

## 步骤

1. **济州公交官方 BIS 私有端点**（需 pwsh 直连；官方站无公开文档，端点靠页面内 JS 反查）
   - 全线路：`GET https://bus.jeju.go.kr/publicTrafficInformation/getBusRouteNum?GROUTE_TYPE=<0..16>`（枚举含义：1=제주/서귀포간선，2=지선，3=일반간선，4=급행，5=읍면지선，6=리무진，8=관광지순환，9=심야）
   - 单线页面：`GET /schedule/viewNew/<번호>` → 页内含 `showTab(<scheduleId>)`，从那里取 scheduleId
   - **逐班时刻表**：`GET /data/schedule/getScheduleTableInfo?scheduleId=<id>` → 据此算首末班与배차간격
   - 站名检索：`POST /data/search/searchStationByKeyword`（keyword 用**韩文**；返回中英日站名 + 经纬度 → 可自算步行距离）
   - 站经停线路：`POST /data/search/getNewStationInfoByStationId`
   - 线路站序：`POST /data/search/getLineInfoByLineId`
   - 限制：批量循环 **>100 次返回 `(500) Internal Server Error`** → 分片重试；**官方不给站间耗时**，只能给区间估计，必须在输出里标注这是数据本身的口径。
2. **visitjeju.net 详情页字段提取**（页面存在性先按第 7 条判）
   - URL：`https://www.visitjeju.net/kr/detail/view?contentsid=<CONT_/CNTS_ ID>`
   - 数据在 **Nuxt SSR payload** 里且被**双重转义**成 `\"key\":\"value\"`。做法：抓 raw HTML → 先反转义 `\uXXXX` → 再提 `<pre data-key="usedescinfo">`（里面就是运营时间 / 休馆 / 限制条件的官方原文）+ homepage / address。
   - **禁用回溯型正则**：`(?:[^"\\]|\\.){0,1500}` 实测 **120s 超时**（回溯爆炸）→ 改「手动扫描字符 + 遇到反斜杠就跳过下一个字符」。
   - 搜索页 `?keyword=` 是 **JS 渲染**：返回 764KB 但 `CNTS_[0-9]{15}` 匹配数为 **0** → 别用它找 ID；改用 `web_search` 反查 URL 里的 contentsid。
2b. **`koreatourinfo.com` = 한국관광공사 TourAPI 的网页版全字段镜像**（单页即含 주소 / 영업시간 / 휴무일 / 대표메뉴 / 전화 / 最后更新日；其中「휴무일（休业日）」与「最后更新日」是别处最难拿到的两个字段）
   - **反查 contentid**：`web_search` 搜 `koreatourinfo <지역> <업종/菜名>` → 命中详情页 URL 即为该条的 contentid 页；**不要**用该站的 WordPress 站内搜索页（实测 30s 超时）。
   - **分类页可翻页批量索引**：按分类页逐页翻、逐条取 contentid，可建"某地区某行业全量店铺名录"（实测翻 44 页得到 409 家济州餐饮条目 → 该镜像能当名录源用，不必先去别处枚举店铺）。
   - **已落盘脚本**（会话产物，路径会变、做法可复用）：`kti.py`（抓单页全字段）、`kti_dates.py`（一行一店输出「店名 | 最后更新日 | contentid」）、`kti_index2.py`（分类页批量索引），位于 `D:\workspace\tmp\jeju\`；运行前必须 `$env:PYTHONIOENCODING='utf-8'`。
   - **该镜像不提供价格**——"字段都抓到了但没有价格"是数据口径本身，不是抓取失败，不要重试或改判。
3. **韩国观光公社「열린관광」**：`https://access.visitkorea.or.kr/ms/detail.do?cotId=<UUID>` 是**服务器渲染**，含 `휴무일` / `이용시간` / `이용요금` 三字段，纯文本好解析（该域 `web_fetch` 报 `TypeError: fetch failed`，必须 pwsh）。
4. **韩国免税店协会营业时间表**：`https://www.kdfa.or.kr/ko/member/dfs_view.php?no=<N>`（实测编号 12=신라，13=신세계，14=JDC제주공항/제주항，17=제주관광공사）；编号清单页 `dfs_list.php`。
5. **官方门票价目表（每周更新）**：`http://visitjeju.or.kr/issue/spots.htm` → 取最新帖 `?act=view&seq=NNNNN` → `?act=download&seq=NNNNN&no=1` 下 xlsx。解析：python `zipfile` 读 `xl/sharedStrings.xml` + `xl/worksheets/sheet*.xml`，**必须按 `<c t="s">` 的索引去 sharedStrings 还原文本**——只取 `<v>` 得到的是**数字索引**，不是票价。
6. **潮汐**：`https://www.badatime.com/<stationId>-<YYYY-MM-DD>.html`（数据源 국립해양조사원）。济州站点 ID：제주 67 / 서귀포 72 / 모슬포 73 / 화순항 74 / 한림항 77。
7. **假页面陷阱（判存在性的正确姿势）**：`jeju.go.kr` 的若干子路径（`/seongsan/`、`/sanbangsan/`、`/yongmeori/`、`/soesokkak/`、`/udo/`）返回**通用 5138 字节导航页且 HTTP 200** → 判"页面存在"要用 **raw 长度 + `<title>`**，不能只看状态码；同理，Bing 的 200 缓存页也不等于目标站可达。
8. **出入境 / 入境申告类官方源（e-AC 与驻外使馆）**（新增；字段口径与 URL 结构见下）
   - **e-AC（法务部，`https://www.e-arrivalcard.go.kr`）详情页**：`/portal/board/viewBoardDetail.do?bbsId=<文章id>&eacBbsKndCd=<n>&pageIndex=1&flId=<附件id>`
     - **`bbsId` 是文章 id，`flId` 是附件 id 且常为空**——把它当"板块 id"去找列表页会一直找不到正文，这是本次绕最久的坑。
     - 正文**服务端直出**在 `<div class="vtBody contentPre">` 里，不是 JS 异步加载（见坑表"被证伪的判断"）。
     - **列表页**：`/portal/board/boardList.do?bbsId=0000012014&eacBbsKndCd=2&pageIndex=N`（FAQ；`pageIndex=1` 韩文、`2` 英文）。找正文的路径是**先列表页取文章 id → 再拼详情页**，不要用"板块 id"直接猜详情页。
   - **驻外使馆（mofa.go.kr 系列）通用详情页形态**：`https://<cc>.mofa.go.kr/<city>-<lang>/brd/m_<板块id>/view.do?seq=<文章id>`
     - **域名段拼写陷阱**：韩国驻洛杉矶总领馆正确段是 `us-losangeles-ko`（另有 `-en`）；写作 `us-losangeles`（**缺连字符**）返回 **HTTP 200 但内容是外交部门 404 页**（约 1557B，`<title>페이지를 찾을 수 없습니다…`）→ 判存在性必须看 `<title>`/正文或字节数，不能只看状态码 200。
   - **页面无日期戳时怎么定锚**：韩国官方页常**不给 작성일**——① 用 HTTP 响应头 `Date` 作为"抓取当日"锚点；② 看**列表页上该文章的 등록일**；③ `?ver=` 这类静态资源版本号可反推站点改版时间。
   - **判"某政策是否已废止"的方法**：翻遍**主管机关**的全部公告列表 + FAQ 全条目 + 가이드 页 + 部门 보도자료 + 국민콜110 与 immigration.go.kr 首页，对 `폐지` / `종이` 等关键词逐处计数；命中 0 时，**"找不到废止公告本身"也是证据**，但必须**写明查过哪些页（URL + 页码范围）**，否则等于没查。
     - 反例纪律：航司 / 二手渠道会出现与官方原文**直接冲突**的说法（本次实测某航司 PDF 声称纸质作废，与 4 个独立官方源原文冲突）→ 冲突时以主管机关原文为准，并把冲突双方都写进结论。

## 坑与修法

- 现象：`Error: fetch failed`（web_fetch）、`URLError <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复…>`（python）。
  → 原因：**按站点**到该域不可达，**不是**站点不存在，**也不是**"韩国站一律打不通"（同批实测里 `koreatourinfo.com` / `visitjeju.net` 的 python urllib 是通的）。
  → 修法：先按站点分档量一次——python urllib 通就直接用；不通再 pwsh 直连同一官方站；仍不通才换官方同级站，最后退到 `web_search`。
- 现象：Bing 返回 200，内容却是无关的 Windows 帮助页。
  → 原因：搜索回退页/缓存页。
  → 修法：状态码不是成功判据，必须看 `<title>` 与响应体长度。
- 现象：Overpass `(429) Too Many Requests` / `(504) Gateway Timeout`。
  → 原因：公共服务限流 / 抖动。
  → 修法：加间隔重试，并把失败与"0 条命中"分开记，别写成"查无"。
- 现象：`jejusi.go.kr` / `council.jeju.kr` 返回 `contrary to the Web firewall security policies … blocked`。
  → 原因：WAF 拦非浏览器/非本区域请求。
  → 修法：改用可直连的官方替代站（visitjeju.net / visitkorea 系列）。
- 现象：整页 HTML 上跑 `(?:[^"\\]|\\.){0,1500}` **120s 超时**。
  → 原因：回溯爆炸。
  → 修法：手动扫描 + 跳过反斜杠；或先反转义再窄正则。
- 现象：visitjeju 搜索页返回 764KB，`CNTS_[0-9]{15}` 命中 **0**。
  → 原因：搜索页 JS 渲染。
  → 修法：用 `web_search` 反查 `contentsid`。
- 现象：BIS 批量拉到第 100 多次回 `(500) Internal Server Error`。
  → 原因：私有端点限流/超时。
  → 修法：分片循环 + 重试，结果按线路编号落盘断点续抓。
- 现象：xlsx 解析出来的"票价"是一串整数。
  → 原因：只读了 `<v>`，那是 sharedStrings 索引。
  → 修法：按 `<c t="s">` 还原文本（第 5 条）。
- 现象：按旧笔记断言某韩国域"打不通"，现测却通（或反之），照旧结论走就白绕一圈。
  → 原因：可达性是**时间 + 路径**相关的（同一域首页通而私有端点不通；今天 200、明天 403/WAF）。
  → 修法：把"打不通 / 必须用某通道"当**假设**，开工先跑一次三级探测（`web_fetch` → python urllib → pwsh），落盘状态码 + 长度 + `<title>`；本 skill 矩阵里的每一行都同样要现测刷新。
- 现象：`koreatourinfo.com` 的 **WordPress 站内搜索页 30s 超时**。
  → 原因：站内搜索不可用，与站点其余页面（python urllib 可通）无关，别据此判整站不可达。
  → 修法：不用站内搜索找 ID；`web_search` 搜 `koreatourinfo <지역> <업종/菜名>` 反查 contentid，或走分类页翻页索引（第 2b 条）。
- 现象：`koreatourinfo.com` 详情页字段都拿到了，但**一个价格字段都没有**。
  → 原因：该站是 TourAPI 镜像，**字段集里本来就不含价格**。
  → 修法：주소/영업시간/휴무일/대표메뉴/전화/最后更新日 照收，价格另找官方价目源（第 5 条 xlsx）；不要把"无价格"写成抓取失败或重试。
- **被证伪的判断（照着旧结论走会白绕一圈）**：曾判定「e-AC `제도 안내 2025-12-29` 公告正文由 JS 异步加载、抓到 90KB 空壳」——**该判断不成立**。
  → 原因：正文是**服务端直出**在 `<div class="vtBody contentPre">` 里；抓不到的真实原因是**没定位到正确的文章 URL**（把 `bbsId` 当成"板块 id"、打开了列表页/错误 URL）。
  → 修法：判"JS 空壳 / SPA"之前先确认自己拿到的**是不是详情页**——对比**列表页 vs 详情页的字节数**与 `<title>`；站点的"JS 渲染"结论只对**具体那类页面**成立（如 visitjeju 的 `?keyword=` 搜索页），不能从一个页面的失败推广到整站。
- 现象：含韩文的 python 脚本用 `Out-File -Encoding ascii` 写出后，韩文变 `??`，随后正则报 `error: nothing to repeat`（正则里本该是韩文字符的位置成了 `?` 量词）。
  → 原因：`ascii` 编码**丢弃**非 ASCII 字符，把韩文换成 `?`，`?` 在正则里是量词 → 语法错误。
  → 修法：写文件用 `[IO.File]::WriteAllText($path, $text, [Text.UTF8Encoding]::new($false))`（无 BOM UTF-8）。**编码类陷阱的完整清单不在本 skill**，见 `pwsh-on-windows`。
- 现象：`us-losangeles`（缺连字符的驻外使馆域名段）返回 **HTTP 200**，但正文是外交部门 404 页。
  → 原因：域名段拼写错，回退到部门级 404。
  → 修法：正确段是 `us-losangeles-ko`（或 `-en`）；判存在性看 `<title>`（`페이지를 찾을 수 없습니다…`）/ 字节数（约 1557B），不看状态码。
- 现象：翻遍官方列表页与 FAQ，`폐지` / `종이` **命中 0**，但无法直接断言"未废止"。
  → 原因：废止公告可能不在你翻的那几页，也可能根本不存在。
  → 修法：按第 8 条把"查过哪些页（URL + 页码范围）+ 关键词计数 0"一起写进结论，并交叉核对航司/二手渠道的冲突说法，冲突时以主管机关原文为准。

## 不要做什么

- 不要因为 `web_fetch` 全灭就判"韩国没有官方数据"——先换 pwsh 直连官方站。
- 不要把"web_fetch / python 打不通"写成整类结论——`python urllib` 对 `koreatourinfo.com` / `visitjeju.net` 实测可通，必须按站点分档量。
- 不要把旧笔记里的"某域不可达 / 必须用 X 通道"当结论——可达性随时间与路径漂移，开工先现测。
- 不要用 `koreatourinfo.com` 的 WordPress 站内搜索页找 contentid（30s 超时）。
- 不要把 `koreatourinfo.com`（TourAPI 镜像）没有价格判成抓取失败。
- 不要用 HTTP 200 判页面存在（jeju.go.kr 导航页、Bing 缓存页、驻外使馆缺连字符 404 页三个反例都在上文）。
- 不要拿 `jeju.go.kr` 的 `/seongsan/` 这类子路径当"景点官方页"。
- 不要用 visitjeju 的 `?keyword=` 搜索页找 contentsid。
- 不要把回溯型正则用在整页 HTML 上。
- 不要只取 `<v>` 就下票价结论。
- 不要把 403 / 429 / 504 / WAF 拦截写成"查无此数据"。
- 不要编造 BIS 不提供的站间耗时。
- 不要把"抓到空壳 / 90KB 空响应体"直接判成站点是 JS SPA——先确认打开的是**详情页**且 URL 参数（`bbsId`=文章 id）没拼错，并对比列表页与详情页的字节数。
- 不要用一个页面（如 visitjeju `?keyword=` 搜索页）的 JS 渲染结论推广成"整站 JS 渲染"。
- 不要用 `Out-File -Encoding ascii`（或任何非 UTF-8）写出含韩文的脚本——韩文变 `??` 后正则报 `error: nothing to repeat`。
- 不要只凭 HTTP 200 断定驻外使馆页面存在——必须看 `<title>` 或响应体字节数。
- 不要用航司 / 二手渠道的说法取代主管机关原文来判"政策是否已废止"。

## 验收标准

1. 每条结论附**官方 URL + 抓取通道**（web_search 还是 pwsh 直连哪条通道）。
2. 页面存在性结论附 **raw 字节数 + `<title>`**。
3. 时刻表结论注明端点与 scheduleId 的来源（`/schedule/viewNew/<번호>` 页内 `showTab(<scheduleId>)`）。
4. 门票结论来自**最新一期**价目表 xlsx，且解析路径含 `<c t="s">` 索引还原。
5. 抓取失败（403/429/504/WAF/超时）与"官方没有该数据"分栏陈述；官方不提供的字段（站间耗时、镜像站不含的价格）显式标注。
6. 说某个站"打不通"时，必须给出**按站点**的探测记录（通道 + 状态码/响应体长度），不得用"韩国站都不可用"这类整类断言代替实测。
7. 出入境/入境申告类结论：注明是**列表页还是详情页**（附 `bbsId` / `seq` 参数）、正文所在容器（如 `vtBody contentPre`）、页面无日期戳时用的锚点（响应头 `Date` / 列表页 등록일）。
8. 判"政策是否已废止"时，列出**查过的全部页面（URL + 页码范围）**与关键词计数结果；引用航司/二手说法时标明它与官方原文是否冲突。
