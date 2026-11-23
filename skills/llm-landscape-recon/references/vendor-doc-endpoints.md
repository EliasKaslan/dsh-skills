# 厂商文档取数入口（2026-11-23 实跑复核）

正文只留「加 `.md`」这一条通则；各家精确入口与坑在此，用不到别加载。下表入口写成完整 https URL，可直接 web_fetch；本文件里不带 scheme 的裸域会被当成相对路径。

| 来源 | 入口 | 备注 |
|---|---|---|
| OpenAI | https://developers.openai.com/api/docs/pricing.md | 200，给全 Standard/Batch/Flex/Fast 分档与 cached / 30m 写 / 12h 写列；全站索引 https://developers.openai.com/llms.txt |
| Anthropic | https://platform.claude.com/docs/en/about-claude/pricing.md | 200，一次给全价格表 + 缓存倍率脚注 + tokenizer 说明 |
| Google | https://aistudio.google.com/docs/pricing.md | 200 且是干净 Markdown（自带索引 https://aistudio.google.com/llms.txt）。`<page>` 换成 `pricing`、`models` 等即可；**先试 aistudio 域**，`ai.google.dev/gemini-api/docs/*.md` 会被 302 到 aistudio 的 HTML 壳（只回 `<!doctype html>`），web_fetch 遇跨域 302 直接报 `cross-origin redirect ... not followed automatically` |
| Z.ai | https://docs.z.ai/release-notes/new-released.md 、https://docs.z.ai/llms.txt | `llms.txt` 一次性索引全部文档，搜版本号最快；价格页 https://docs.z.ai/guides/overview/pricing |
| 智谱开放平台 | https://docs.bigmodel.cn/cn/guide/start/pricing | 与 z.ai 定价口径不同，两边要分别核 |
| Artificial Analysis | https://artificialanalysis.ai/leaderboards/models | 只有该表能出数（Index / Cost per Task / Time per Task / TTFT / 上下文）；页面 1.4MB、数字靠前端渲染 |
| Artificial Analysis | https://artificialanalysis.ai/agents/coding-agents | 200 但纯 JS 图表且自述 `No publicly available API`，只拿得到「持平 / −N 分」这类相对描述；https://artificialanalysis.ai/leaderboards/coding-agents 实测 404 |
| Artificial Analysis | https://artificialanalysis.ai/articles/<slug> | 拿发布方解读最快的入口（`/articles/` 列表可达） |
| arena.ai | 直连 403（Cloudflare） | WebDev/Design Arena 分数只能取官方社媒或第三方镜像，标「非直读」并记多源差异 |
| ModelScope | 纯 JS SPA | https://www.modelscope.cn/api/v1/models 实测 404，https://www.modelscope.cn/dolphin/models 200 但只是前端壳，都不能举证权重；查权重优先用 HuggingFace API |

## HuggingFace API 取权重事实（比翻网页可靠）

- 搜某模型是否存在：https://huggingface.co/api/models?search=<model> ，返回 `[]` 即该名字全站无仓库（2026-11-23 复测仍可用）。
- 看某组织最新发布：https://huggingface.co/api/models?author=<org>&sort=createdAt&direction=-1&limit=25 ，读 `createdAt` 即发布日期，可直接引用。
