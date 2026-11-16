---
name: anima-ai-musume-lora
description: "Anima/ComfyUI与AI娘LoRA的场景入口，转自托管图像方法并按需复用角色参考。"
whenToUse: "用户明确选择Anima、ComfyUI或AI娘LoRA，需要工作流、兼容性、训练或单卡实验验证。"
disable-model-invocation: true
---

# Anima 与 AI 娘 LoRA

用户明确选择 Anima/ComfyUI 时，按 [自托管图像工作流](../anime-art/SKILL.md) 核对模型与 LoRA 版本、节点 schema、设备和训练/生成验收；不要把旧单卡速度或 Turbo 参数当当前承诺。

需要五角色身份与画风时再读 [AI 娘参考与验收](../minimax-ai-musume-4k-art/SKILL.md)。本目录旧 patch_ops.py 与 wheel_par.py 已确认存在缺陷，不能当默认入口；在目标版本定位后采用局部、幂等、可回退补丁及可靠下载能力。
