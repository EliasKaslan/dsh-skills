# 来源检查细节

源经验：ai-vendor-official-source-audit 与 llm-landscape-recon（2026-11-16 审查）。保留方法，未迁入历史模型/价格/日期和某站永久可达性。

按问题选择发布页、技术博客、模型详情、API清单、定价、changelog/退役通知和模型仓文件。新闻页常有竞品比较而详情页没有，引用时读上下文与比较方向。没有相同数字只能说明“未找到同口径依据”；不自动判厂商造假或实验失败。

HF列表字段会因API参数、版本、权限与分页变化：检查响应 schema，按当前文档决定 full/expand；不要断言某字段永远只在 full=true。createdAt 是仓创建时间，lastModified 是仓更新线索，均不独自证明发布时间。许可字段 null/other 时查许可正文和版本，不等于无许可或通用宽松许可。

第三方排行榜页面可能有多个模型、多个effort和多套时序。优先有文档的数据接口；HTML/SSR提取必须锚定完整模型对象、区块和版本，保留原载荷及字段来源。不能在整页拿第一个同名字段，也不能简单全局反转义后把所有块拼成一个JSON。抓取器截断、页面骨架或付费接口不可达时写未确认，不擅自找未经验证的镜像。

官方文档入口也会迁移，跟随已验证重定向或官方链接。OpenAI 产品、配置与API问题查当前官方文档及实际接口版本；若DSH已配置文档检索工具，先查其schema再使用，不假定安装了特定文档技能。DSH界面名称不等于模型API参数。

安全地保存快照：任务目录命名为 vendor-models.md 等普通名；Windows大小写不敏感时，claude.md可能与指令文件CLAUDE.md同名，避免意外注入或覆盖。原始带认证信息的响应先最小化、脱敏，不复制凭据。

一手参考：[Hugging Face Hub API](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)、[Hub错误类别](https://huggingface.co/docs/huggingface_hub/package_reference/utilities)、[模型下载统计](https://huggingface.co/docs/hub/models-download-stats)。API字段与限流使用当前版本文档核实。
