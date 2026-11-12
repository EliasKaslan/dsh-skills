import shutil, sys
p = "/home/vllm/x00886548/work/anima-comfy/comfy/ops.py"
src = open(p, encoding="utf-8").read()
anchor = "def cast_bias_weight(s, input=None, dtype=None, device=None, bias_dtype=None, offloadable=False, compute_dtype=None, want_requant=False):"
if src.count(anchor) != 1:
    print("anchor count", src.count(anchor)); sys.exit(1)
head, tail = src.split(anchor, 1)
needle = "\n    if input is not None:\n        if dtype is None:"
if tail.count(needle) < 1:
    print("needle missing"); sys.exit(1)
guard = ("\n    # torch_npu Module.to() calls cast_weight(device) positionally; treat it as device.\n"
         "    if isinstance(input, torch.device):\n"
         "        if device is None:\n"
         "            device = input\n"
         "        input = None\n")
tail = tail.replace(needle, guard + needle, 1)
shutil.copy(p, p + ".bak")
open(p, "w", encoding="utf-8").write(head + anchor + tail)
print("patched", p)
