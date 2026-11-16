---
name: anime-art
description: "维护用户明确选择的SDXL、Anima/ComfyUI、H3等自托管图像与LoRA工作流，核对版本、设备、生成与训练结果。"
whenToUse: "用户明确要求本地或自托管扩散模型部署、复现实验、LoRA训练或后端比较；普通图片请求先查当前DSH已配置图像工具。"
disable-model-invocation: true
---

# 自托管扩散模型与 LoRA

先确认用户明确选择自托管/指定模型，恢复已有项目、模型revision、框架commit、设备、任务预算与输出目标。普通图片请求先检查当前 DSH 已配置图像工具及实际 schema；历史更快的服务不产生换模型/换机器授权。没有可用工具时说明缺口，不假定内置后端存在。

底本中的SDXL/Animagine、Anima+ComfyUI、MiniMax-H3-Image是三种不同后端：encoder/VAE、prompt语法、negative、步数/CFG、LoRA兼容和参考图路径各自取当前模型卡/接口。先校验权重索引/校验和与变体，不能把文件名含BF16当存储精度。昇腾环境/存储/设备准入用[ascend-cann-env](../ascend-cann-env/SKILL.md)、[ascend-server-layout](../ascend-server-layout/SKILL.md)；模型支持先取证，不能从CPU/CUDA运行推出NPU可用。

## 执行与验证

在独立环境最小冒烟：准确解释器与加载路径、目标设备、有限张数/尺寸、同步与真实图像。记录完整workflow、model/LoRA哈希、scheduler/seed/steps/CFG、prompt/encoder截断、图像尺寸及版本；seed仅在相同后端条件下提供可重复线索。

ComfyUI先核对当前节点schema与model目录，再构建workflow。提交后按本任务prompt_id跟踪history/status/error及所有输出节点，不硬编码node9或把queue为空当成功；下载保持文件名安全、核对实际响应图像，落任务目录。探活/端口占用不证明是本任务的正确服务，不对外默认bind0.0.0.0。

新LoRA需核对底模结构、权重key、rank/alpha、触发词和许可；验证真实加载与强度改变的效果。原资料某些组合文件尚未下载，不能写成已可用。构图/人脸幼态/颜色漂移用对照seed与实际图像判断，不把某一LoRA的倾向推广所有模型。

源码补丁只在精确版本复现问题后局部改动，保存diff/备份并重跑原失败分支、幂等与回退测试。不能执行旧顶层patch_ops.py或patch_qwen_rotary.py到共享环境；GLIBCXX、position/device绑定和lowvram offload先各自定位。更多边界见 [references/backend-notes.md](references/backend-notes.md)。

训练先确认参数/梯度/optimizer精度与显存预算，小步验证loss/梯度/checkpoint+resume，再长跑；不能从“CPU太慢”推断不具备训练可行性。交付实际通过范围，速度数字带硬件和采样设置；未上机就不称可部署通过。

服务持续运行、自动看护和共享设备占用需本轮任务确实要求；不要为出一张图永久启动自愈进程，停止/重启仅本任务资源。来源：旧anime-art、ai-musume-4k-art、minimax-ai-musume-4k-art、anima-ai-musume-lora，旧脚本保留历史文件；不要按旧路径直接执行补丁/下载器，已确认缺陷见 [references/legacy-script-boundaries.md](references/legacy-script-boundaries.md)。
