# 后端差异与已确认旧工具问题

2026-11-16静态审查，不继承.190的固定目录、端口、卡号、镜像或已启动状态。旧SDXL和musume旧管线已经被原库标为归档，仍可作为用户明确要求复现旧实验的线索，不自动推荐恢复。

- SDXL：77通常是CLIP序列窗口，不是所有pipeline的统一完整prompt极限；长提示分块、双encoder、加权语法和提示词剪裁取决于实际实现。不要用字符估算冒充真实tokenizer，更不因文件名猜模型族就写“官方推荐标签”。
- Anima/ComfyUI：旧经验的Module.to(device)位置参数误绑、cast_bias_weight、highvram与libstdc++为特定版本排障线索。旧补丁patch_ops.py的非幂等缺陷见 [legacy-script-boundaries.md](legacy-script-boundaries.md)，不要导入。
- H3-Image：旧服务使用自然语言、参考图、6步/CFG1及32网格，这些为部署接口约束而非模型永久能力。不要承诺固定几张die/8秒一张，也不以/v1/models200替代完整生成路径。
- 旧自写下载器不等于pip tag兼容解析，也不核对Range响应；改用当前可靠包管理与下载能力并核sha。缺陷证据见 [legacy-script-boundaries.md](legacy-script-boundaries.md)。
- 下载/安装和模型服务均有外部副作用。本轮只做静态解析与纯逻辑fixture，没有下载模型、启动服务、安装包或占用NPU，旧运行成功记录保留其历史状态。

原方法中的全局dE/方差不能验证角色身份；裁切、模糊、重采样与内容都会影响指标。图像必须以用户要求实际检查，样本/风格阈值不升级成通用PASS门禁。
