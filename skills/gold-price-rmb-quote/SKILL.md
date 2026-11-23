---
name: gold-price-rmb-quote
description: 抓黄金实时行情、换算人民币每克、拆解内外盘溢价；用于查金价、判断跌幅构成与短期区间
disable-model-invocation: true
warm-triggers: 查金价 / 金价大跌 / 换算黄金每克多少钱 / 黄金一个月走势
warm-reason: 低频/兴趣类：用户偶尔问金价与短期走势，非日常开发任务，放热目录会长期占成本
---

# 黄金行情取证与人民币每克换算

## 何时调用

用户问「金价多少 / 今天金价大跌 / 黄金后面怎么走 / 多少人民币一克」时加载。覆盖：抓实时报价 → 统一折算成人民币/克 → 判断跌幅里有多少是金价、多少是溢价。

不适用：股票/外汇单品种技术分析；不含交易执行。

## 行情抓取端点（2026-11-23 实跑复核，价格数字本身仍须当轮取）

国际盘与汇率，新浪行情接口一次可批量取，逗号分隔。**必须带 `Referer: https://finance.sina.com.cn`**，否则一律 `403 Forbidden`（本轮实测）：

```
https://hq.sinajs.cn/list=hf_XAU        # 伦敦现货黄金，美元/盎司
https://hq.sinajs.cn/list=hf_GC         # COMEX 黄金期货
https://hq.sinajs.cn/list=fx_susdcny    # 在岸 USD/CNY
https://hq.sinajs.cn/list=fx_susdcnh    # 离岸 USD/CNH
```

日 K（含开高低收，用于算日内振幅与区间高低点）：

```
https://stock.finance.sina.com.cn/futures/api/jsonp.php/var%20_xau=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=XAU
```

国内品种用东方财富 `secid`，这是唯一稳定拿到上金所/上期的口径：

```
https://push2.eastmoney.com/api/qt/stock/get?secid=118.AU9999   # 上金所 Au99.99，元/克
https://push2.eastmoney.com/api/qt/stock/get?secid=118.AUTD     # Au(T+D)
https://push2.eastmoney.com/api/qt/stock/get?secid=113.aum      # 沪金主力
```

`push2` 会 302 到 `push2delay.eastmoney.com`（数据仍可用，是延时盘）。连打太快会得到 `Remote end closed connection without response`，隔 1–2 秒重试即可，那不是端点失效。

注意国内收盘时间不同：Au99.99 / T+D 约 15:45、沪金约 15:12，夜盘 20:00 后才更新；取到的数不含 15:30 后的国际波动（该时钟未在本轮复核，以交易所公告为准）。

## 人民币/克换算与溢价拆解

金衡盎司固定 31.1034768 克，所以：

```
人民币/克 = 美元/盎司 × USD/CNY ÷ 31.1034768
```

必须同时给出两个数并解释差值：

- **国际折算价**：按上式算，是「理论价」
- **上金所 Au99.99**：是「成交价」，两者之差就是内外盘溢价/贴水

判断跌幅时先拆三层，否则一定误读：

1. 国际金价变化（美元计价）
2. 汇率变化（人民币升值时，美元金价不动、人民币金价也跌）
3. 溢价变化（内地对国际的升贴水，可剧烈摆动）

国内单日跌幅因此可能是国际的 2–4 倍。若溢价由正转负，跌幅里相当一部分是「溢价回吐」，属一次性补跌，不是基本面二次恶化。

## 坑与修法

- `https://hq.sinajs.cn/list=AU9999,AUTD` → 返回**空字符串**（2026-11-23 复测仍空）。`AU0` 有返回但停在 `2024-07-17` 的旧行，不可用。新浪不认这些代码，国内品种必须走东财 `secid`。
- 漏 `Referer: https://finance.sina.com.cn` → 所有新浪行情接口 `403 Forbidden`。
- `https://data-asg.goldprice.org/dbXRates/USD` → `远程服务器返回错误: (403) 已禁止。`
- `https://stooq.com/q/d/l/?s=xauusd&i=d` → 返回 `This site requires JavaScript to verify your browser.`，非 HTML 响应，解析必失败。
- `https://www.investing.com/currencies/xau-usd-technical` → `403`。技术位改从 blockchain.news / primexbt 等可抓站点取，并在回答里标注来源。
- 品牌金饰价（周大福/老庙/中国黄金）只从财经媒体转载页拿得到，**是否含工费通常未说明**，必须标「挂牌价、工费另计」，不能当投资成本价。
- 首饰价与原料价差可达 40% 以上，回答里要明确区分「投资口径（基础金价/积存金/金条）」与「首饰口径」，否则误导配置决策。

## 数据可信度纪律

- 行情接口给的是实时，国内收盘价是滞后快照，**必须分别标时间戳**，不要混在一张表里当同一时刻。
- 折算前先确认用的是**当日汇率**；用错汇率会让人民币金价偏几十元/克。
- 机构目标价常发布于暴跌前且**事后不下修**，直接引用会系统性高估上涨空间。引用时标注发布日，并说明「未随最新价下修」。
- 一个月对黄金是噪声区间（日波动 1–3%），**给区间+概率，不给单一点位**；明确写出触发条件（议息会议、CPI/PCE、关键支撑与阻力位），并换算成人民币/克给出可盯的数字。
