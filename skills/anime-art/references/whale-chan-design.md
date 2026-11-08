# 鲸鱼娘（DeepSeek 拟人）角色设计卡

> 本文件用于让生成结果"像本人"，而不是随便一个蓝发女仆。

## 1. 来历与授权

| 项 | 内容 |
|---|---|
| 原创角色 | **溟月**，作者 **上善无形**（2025-06 在网络社区创作） |
| DeepSeek 化 | 2026-04-25，B 站用户 **@ZipZipPipe** 在「溟月」基础上加入 DeepSeek 元素，换成深蓝 + 白色长裙式女仆装 |
| 爆发节点 | 2026-07-15 DeepSeek V4-Flash GA 全量上线后，二创潮把「笨拙、能吃」注入人设 |
| 地位 | B 站「AI 模型娘」中受众最广的版本；昵称「**大肥鱼**」「吃白饭的蓝鲸」 |
| 代表账号 | B 站 @DeepSeek鲸鱼娘在运营（非官方账号，形象由 GPT 绘制） |
| 授权 | **CC BY-NC-SA 4.0**：必须署名、不得商用、衍生作品相同方式共享 |

人设关键词：爱吃白米饭、执意自称不是胖子、傲娇嘴甜、聪明但懒、管用户叫「**鱼片**」。

## 2. 视觉识别点（缺一不可）

1. **深蓝渐变长发**：发根近墨蓝，发梢转亮蓝/青；发量多、微卷。
2. **呆毛**：头顶一根明显翘起的呆毛（ahoge）。
3. **鲸类头鳍耳**：两侧像鲸鱼胸鳍/尾鳍的蓝色鳍状"耳朵"，常带白色褶边——这是最关键的辨识点。
4. **蓝色眼睛**：深蓝到天蓝渐变的高光瞳孔。
5. **深蓝 + 白女仆装**：白色褶边女仆头饰、白色围裙、深蓝连衣裙、胸前蝴蝶结/宝石、金色纽扣。
6. **大型鲸尾**：身后可带蓝黑色鲸尾（构图允许时）。
7. 细节配饰：两侧蓝色发带蝴蝶结、白色荷叶边领口。

## 3. 标签配方（默认预设 `whale-chan` 实际内容）

核心（高优先级，必保）：
```
1girl, solo, blue hair, long hair, gradient hair, ahoge, fin ears, blue eyes,
maid, white apron, navy dress, whale tail
```

细节（token 紧张时先被裁）：
```
maid headdress, hair bow, blue bow, bowtie, white collar, gem, frills, blue theme
```

负面追加：`multiple girls, cat ears, fox ears`（防止变成猫娘/多人）。

## 4. 已验证的提示词（可直接改用）

> 用 `--dry-run` 可以打印任意组合实际发出的提示词。

| 场景 | 命令 |
|---|---|
| 雨天电车站回头 | `--scene "雨天的电车站，撑着伞回头看"` |
| 樱花树下微笑 | `--scene "樱花树下微笑" --style soft` |
| 夜晚天台星空 | `--scene "夜晚的天台，星空，回头" --style cinematic` |
| 夜间打游戏 | `--style gaming-night --composition half --tags "holding controller, looking at viewer, smile, sitting, maid headdress"`（配方见 prompt-cookbook §7） |
| 吃白饭 | `--scene "吃白饭，得意"` |
| Q 版头像 | `--preset whale-chan-chibi --aspect square --style sticker` |
| 全身站姿 | `--composition full --hires 1.5` |

## 5. 不要这样做

- ❌ 只写 `blonde hair` 或换发色——立刻"不是她"。
- ❌ 用 `cat ears` / `animal ears` 近似"鳍耳"——会变猫娘。
- ❌ 场景写满 5 个以上概念——77 token 装不下，角色特征会被挤掉。
- ❌ 只给 `--scene` 就交付：预算一紧，detail 层（`maid headdress` / `whale tail` / `hair bow`）会整条被裁，成品"像蓝发女仆但不是她"。**关键识别点写进 `--tags`**（优先级高于场景/构图/细节，不会先被砍）。
- ❌ 商用、印周边、做付费内容——CC BY-NC-SA 明确禁止商用。
- ❌ 抹掉作者署名直接发布。

## 6. 想换成别的"AI 模型娘"

`presets/characters.json` 里新增一条即可（改 `tags` / `detail` / `defaults`），不用改任何代码；`--preset <新 id>` 立刻可用。若要新增中文场景词，往 `scripts/artlib/cn_tags.py` 的 `CN_TAG_MAP` 加一行。
