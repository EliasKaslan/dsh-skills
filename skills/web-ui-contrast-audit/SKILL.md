---
name: web-ui-contrast-audit
description: "定位网页主题切换后文字与背景难辨的问题，按实际渲染背景计算WCAG文本对比并复测修复；适用于浅色/深色主题可读性，不以静态颜色值替代复杂背景检查。"
whenToUse: "网页切换主题后文字难辨，需要按实际渲染背景定位、计算WCAG文本对比并验证修复。"
---

# 网页文本对比度核查

在真实页面确认用户反馈的主题、状态、viewport和实际CSS构建产物。通过应用自己的主题入口切换并等渲染稳定；data-theme或某个CSS变量单项变化不证明全部样式已生效。

采集实际自有可见文本、computed颜色/字体/字号与对应有效背景。先定位继承根与主题token，再改局部；body颜色和--text不同只是线索，不独自证明根因。表单placeholder、hover/focus/disabled等状态分别按适用标准检查，不把隐藏节点当普通正文。

WCAG2.x AA普通文本至少4.5:1；大文本至少3:1，通常18pt(24 CSS px)或14pt(18⅔ CSS px)粗体。不能将font-weight600一律当bold；非标准字体还需核查等效笔画。禁用、纯装饰、logo等例外按目标标准确认。阈值前不四舍五入。

半透明前景/多层背景需按实际叠层合成。渐变、图片、混合模式、滤镜、text-shadow与遮罩不能简单backgroundColor还原；标记需渲染/局部最差背景检查，不能跳过后仍称全页通过。纯色计算可用 [scripts/contrast_metrics.py](scripts/contrast_metrics.py)，它不采集浏览器，也不判页面整体合规。

按用户任务修复源CSS/token并构建必要产物，在相同主题和节点复测前后实际颜色/比值；同时看截图是否文字可读与视觉层级保持。报告列节点、状态、测量范围、复杂背景未知项，不把单一数值当全部可访问性验收。

一手依据：[WCAG 2.2对比度说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)。来源旧同名skill，2026-11-16核对并修正大字字重、渐变跳过与静态根因过度推断。
