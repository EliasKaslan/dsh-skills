# AI 娘设定卡（逐帧核验版）

> **唯一依据**：B站 `BV14C456WEXN`《谁是最适合当老婆的AI？五个AI挑战逆天恋爱测试题！【牢大百科16】》
> （UP：牢大百科，32:42，852×480）。核验方式：正片 1 fps 抽帧 1962 张 → 按角色裁切 → **逐格人工复核**。
> 存档帧在 `references/frames/<char>/`，文件名 `tNNNNN.png` 里的数字就是**视频秒数**，可回原片对帧。
> **身份口径**：参赛的只有五个——Claude、DeepSeek、GPT、Grok、Gemini；**千问「豆姐」不在五人里**，
> 她是片中的 3D 写实主持（原片 313 帧里只在少数镜头出现），本 skill 按同组特征转 2D。
> **判定纪律**：四项（发色 / 瞳色 / 头饰 / 主色板）全中才算对；只中一项必错。

## 零、先看这张"别认错"表

| 角色 | 最强识别点 | 主色板 | 存档帧数 |
|---|---|---|---|
| claude | **橙发 + 耳边大朵橙色雏菊 + 手抱一本皮质书** | 橙 / 白 / 黑 | 6 |
| deepseek | **深蓝渐变长发 + 两侧耷拉的鲸鱼鳍耳（藏青鳍 + 窄白边）+ 白荷叶边女仆头箍** | 深蓝 / 白 / 蓝宝石 | 6 |
| gpt | **银白长发 + 一对大号象牙白羊角** | 白 / 银 / 淡紫 | 3 |
| grok | **金钻卷 + 金色繁复王冠嵌黑宝石 + 长尖精灵耳** | 黑 / 金 / 酒红 | 3 |
| gemini | **蓝紫发 + 左粉右金异色瞳 + 珠光星星发饰** | 蓝紫 / 紫 / 金 | 4 |

**最容易混的两组**：
- **grok ↔ gpt**：两人都浅色发、都戴头饰。grok = 金发 + **金冠** + 尖耳 + 蓝瞳；gpt = 白发 + **白羊角** + 淡紫瞳 + 面无表情。
- **gemini ↔ deepseek**：都蓝色系。gemini = **蓝紫** + **异色瞳** + 星星；deepseek = **深蓝渐变** + **耷拉的鲸鱼鳍耳（白边）** + 白女仆头箍 + 蓝宝石胸针。

---

## 一、claude（Anthropic）

| 项 | 细节 |
|---|---|
| 发 | 橙色长发，中分偏侧，发根略深、发尾偏亮橙；额前有斜向长刘海，发梢外翻微卷 |
| 瞳 | 琥珀橙（amber-orange），上眼线加粗，眼尾上挑；表情常带"逗你玩"的笑意 |
| 头饰 | **viewer 右侧（她的左侧）耳上方一大朵橙色重瓣雏菊**，花心深褐；另有金色花形垂坠耳饰（单侧） |
| 服装 | 白色衬衫，**肩线处有奶油色雏菊刺绣**；白色蕾丝高领，领口系**黑色缎带蝴蝶结**；胸前别一枚橙色雏菊胸针 |
| 道具 | **手抱一本深棕色皮质书本**（正片多次出现，是最稳的识别道具） |
| 体态 | 站姿，微侧身，常低头看书再抬眼说话 |
| 神态谱 | 温柔笑 / 挑逗半笑 / 无奈叹气 / 被打断时的停顿 |
| 错法 | ① 花画到 viewer 左侧；② 画成红发；③ 白衬衫画成礼服 |
| 提示词 | `long orange hair, amber-orange eyes, large orange daisy on the viewer-right side of her head, gold flower earring, white blouse with cream daisy embroidery, white lace high collar with a black ribbon bow, orange daisy brooch, holding a dark brown leather book` |
| 存档帧 | t00784 t00790 t01428 t01438 t01448 t01568 |

## 二、deepseek（鲸鱼娘）

| 项 | 细节 |
|---|---|
| 发 | 极长深蓝发，**发梢渐变成青蓝/浅蓝并带波浪**；单根细呆毛；两侧各一缕长发垂到胸前 |
| 瞳 | 柔和的宝蓝色大眼，虹膜**外深内亮**径向渐变，通常只有一个小高光；上睫毛深藏青 |
| 头饰 | **白色荷叶边女仆头箍**（窄箍、bonnet 式横过额顶）；两侧太阳穴各一只**鲸鱼鳍状大耳**：藏青蓝、先向外横展再耷拉到下颌旁，**下缘一圈窄白荷叶边**，鳍根各一个小浅蓝蝴蝶结。**不是蓝色发带** |
| 胸饰 | 领口**黑缎带蝴蝶结** + 圆形蓝宝石胸针（浅金边，宝石深蓝带亮蓝中心） |
| 服装 | 藏青短袖连衣裙 + **白色荷叶边围兜**（正面竖褶 + 小纽扣）+ 白荷叶边肩饰/袖口；白色围裙式腰线 |
| 体态 | 站姿略前倾，双手常交叠在身前；说话时会眯眼笑 |
| 神态谱 | 温柔微笑 / 眯眼笑 / 委屈瘪嘴 / 惊讶睁大 |
| 错法 | ① 把鳍耳画成**蓝色发带/普通蝴蝶结**（旧版错在这）；② 只有白色羽片、没有藏青蓝鳍；③ 两只鳍竖成**兔耳**（要横展耷拉）；④ 漏掉白荷叶边下缘；⑤ 漏掉黑缎带 + 蓝宝石胸针 |
| 提示词 | `very long deep-blue hair fading to cyan-blue wavy tips, one thin ahoge, large soft sapphire-blue eyes, a narrow white frilled maid headband, at each temple a navy-blue whale-flipper ear flaring sideways and drooping beside her cheek with a narrow white ruffled trim on the lower edge and a small light-blue ribbon bow at its root, black ribbon bow with a round blue gem brooch at the collar, navy short-sleeve dress with a white ruffled bib and apron collar, white frilled cuffs` |
| 存档帧 | t00513 t00523 t01045 t01055 t01297 t01307 |

## 三、gpt（OpenAI）

| 项 | 细节 |
|---|---|
| 发 | 银白/月白超长波浪发，**头顶两束大环状呆毛**；发量极大，垂到腰下 |
| 瞳 | 淡紫色（lilac），半垂眼，几乎无表情；眼线细而长 |
| 头饰 | **一对象牙白羊角，从太阳穴向外后卷**（要"大"且"象牙白"，否则会出成小圆环）；**viewer 右侧一条白色编绳/盘绳头饰**带流苏 |
| 服装 | 白色蕾丝礼服，露肩；胸口有蕾丝荷叶边；整体纯白无彩 |
| 体态 | 站得笔直，极少动作，声音平淡（"人机感"的来源） |
| 神态谱 | 面无表情 / 微微偏头 / 极浅的笑 / 眨眼 |
| 错法 | ① 角画小、画成米色发圈；② 瞳画成蓝色；③ 加了彩色装饰（她几乎全白） |
| 提示词 | `very long wavy silver-white hair, two-loop cowlick on top, light purple half-lidded eyes, two big ivory-white ram horns curling outward from the temples, a thick white braided rope headdress on the viewer-right side, white lace dress with bare shoulders` |
| 存档帧 | t00663 t01820 t01830 |

## 四、grok（xAI）

| 项 | 细节 |
|---|---|
| 发 | 金色长发；**viewer 左侧一缕粗长钻卷**；**viewer 右侧高侧马尾，用带金边的黑色大蝴蝶结扎起** |
| 瞳 | 亮蓝色，眼尾上挑，浓眼线；**两侧长尖精灵耳**（最容易被漏掉的一项） |
| 头饰 | **金色繁复王冠**，正面嵌一颗**大黑宝石**，冠顶有小十字饰；冠体有镂空金丝；**两侧各一只黑色蝙蝠翼发饰**（正片帧可见，封面裁切里被挡住——2026-11-11 修正） |
| 服装 | 黑色哥特裙，**酒红/暗红丝绒立领**，黑色薄纱内衬；胸口金色圆形星纹胸针 + 金链 |
| 体态 | 抱臂、抬下巴、侧身睨视；常叼一支红玫瑰（舞台动作，非固有设定） |
| 神态谱 | 坏笑 / 挑眉嘲讽 / 大笑 / 被噎住 |
| 错法 | ① 写 `black crown` → 出黑冠；② 写 `red gem` → 出红宝石（原片是黑宝石）；③ 漏尖耳；④ 漏掉**黑色蝙蝠翼发饰**（正片有，别删） |
| 提示词 | `long blonde hair, high side ponytail tied with a large black ribbon bow with gold piping, one long blonde drill curl, bright blue eyes with sharp eyeliner, long pointed elf ears, black bat-wing hair ornaments, ornate gold crown set with a large black gemstone and a small cross finial, black gothic dress with a dark maroon velvet collar, gold star brooch` |
| 存档帧 | t00130 t00915 t01699 |

## 五、gemini（Google）

| 项 | 细节 |
|---|---|
| 发 | **蓝紫（blue-violet）**长发，发尾转淡紫并带**钻卷**；单根呆毛；两侧长发垂到肩前 |
| 瞳 | **异色瞳：viewer 左眼粉品红、viewer 右眼金黄**（镜像互换 = 错） |
| 头饰 | **珠光/彩虹质感的立体星星发饰**（多颗，粉蓝金渐变）+ 蓝色缎带蝴蝶结；发侧有星形发夹 |
| 服装 | 深紫露肩礼服，金色滚边；白色泡泡袖；胸口金色星形胸针嵌紫宝石 |
| 体态 | 前倾、抬眼看人，动作幅度大，元气 |
| 神态谱 | 元气大笑（露小虎牙）/ 挑眉 / 卖萌 / 突然认真 |
| 错法 | ① 写成"紫发"（偏红紫）；② 异色瞳只写 `heterochromia` 不控左右；③ 星星画成普通发夹 |
| 提示词 | `long blue-violet hair fading to lavender curled tips, one ahoge, heterochromia with the viewer-left eye pink-magenta and the viewer-right eye golden-yellow, iridescent pastel star hair ornaments, blue ribbon bow, deep purple off-shoulder dress with gold trim and a gold star brooch` |
| 存档帧 | t00382 t00392 t00402 t00412 |


## 六、画风：正片口径（`--style show`，2026-11-11 用户定稿）

> 要求：**画风严格参照 BV14C456WEXN 正片**，不要把五位 AI 娘画成"海报立绘"。
> 依据：源片 852×480、1 fps 抽帧；存档帧 648×816（裁切放大）。逐项对照 `references/frames/*/`。

| 项 | 正片口径 | 一眼判错的画法 |
|---|---|---|
| 线稿 | 细、均匀、**深藏青**（不是纯黑），转角圆润 | 黑粗描边、线宽跳动 |
| 头发 | 深蓝 → 青蓝**发梢渐变**；高光只有几根**细浅线** | 大片白色镜面高光、玻璃发 |
| 上色 | **平涂哑光、低饱和**，两档阴影柔和过渡 | 高饱和 poster color、塑料感 |
| 皮肤 | 奶白偏暖、轻腮红、阴影少 | 橘黄、过度阴影、写实皮肤 |
| 眼睛 | 大而圆，虹膜**外深内亮**径向渐变，通常**单个小高光** | 多颗星形高光、玻璃眼 |
| 光 | **柔和平光**，无镜头光斑 / 强轮廓光 / 景深散景 | 摄影棚轮廓光、强 bokeh |
| 质感 | 广播截图**轻微柔化**（源 480p） | 4K 商业插画级锐化 |

**复现顺序**（从强到弱）：

1. `--ref` 2~3 张同角色正片帧：内置模板已带 style-lock（细藏青线 / 平涂哑光 / 禁玻璃高光 / 小高光单点），最稳。
2. 纯文字：`--style show`（默认）。不要用 `anime`——那是 key visual 风，会被判"画风不一致"。
3. 后处理：`match_style.py --strength 0.5~0.7` 轻微趋同；**别直接 1.0**——参考帧整体偏暖金，拉满会把肤色与背景带黄。要量化就用 `eval_match.py` 看 `dE_mean ≤ 8`。

验收时把成图与参考帧拼一张对比图（`sheet.py` 或 PIL 拼接），重点看**发丝高光、线宽、肤色**三处。

## 七、原片镜头语言（想复刻"正片感"时看这里）

- **场景**：金色宫廷法庭，深红帷幕 + 金色栏杆 + 木质审判台；暖黄顶光，背景常有 bokeh。
- **机位**：单人半身/全身居中，人物占画面高度约 75%，头顶留 ~5% 空间；**每镜头只有一位 AI 娘**。
- **色调**：整体暖金，人物用高饱和对比色（橙 / 蓝 / 白 / 金 / 紫）才跳得出来。
- **文字层**：左上角有"第 N 期"小标题、左下角有角色名标签、底部有对话气泡——**生成时不要复刻这些 UI**。
- **复刻构图**：`medium shot, character centered, full figure visible, gilded courtroom background with dark red curtains and gold railings, warm top light`。
