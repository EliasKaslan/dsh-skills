"""Port Qwen-Image-2.1's complex64 rotary embedding to the real (cos, sin) path.

WHY THIS FILE EXISTS
--------------------
QwenImage21Transformer2DModel stores its rotary table as complex64 and does
`self.freqs[i][idx]` on the device. CANN has no complex kernels, so inference dies:

    RuntimeError: index_high_dims_op_api ... call aclnnIndex failed, error code is 161002
    AclNN_Parameter_Error(EZ1001): Tensor self not implemented for DT_COMPLEX64,
      should be in dtype support list [DT_FLOAT, ... DT_BFLOAT16 ...]

Still true on CANN 9.2.0 (MindSpeed 26.2.0 stack) — verified 2026-11-10.

diffusers already ships a real-valued branch, `apply_rotary_emb_qwen(use_real=True)`,
that this model simply does not use. We switch it on and fix the two places where
the code still assumes the complex/tensor form.

THE FOUR EDITS
--------------
1. pos_embed: build the table on CPU (complex indexing is fine there) and return
   the real (cos, sin) pair, moved back to the device.
2. call sites: use_real=False -> True  (2 occurrences).
3. broadcast: the real branch does `cos[None, None]`, i.e. it assumes x is
   [B, H, S, D] (flux layout). This transformer feeds [B, S, H, D], so shape it
   as [1, S, 1, D].
4. KV-cache branch slices `rotary_emb[prefix_len:]` as a tensor; with a tuple
   that returns () and you get "not enough values to unpack (expected 2, got 0)".
   Slice each element instead.

Idempotent. Writes a .orig backup before the first change.
Run it after (re)installing diffusers — a fresh install loses these edits.
"""
import io
import os
import shutil
import sys

TARGET = os.environ.get(
    "QWEN_TRANSFORMER_PY",
    "/home/vllm/ai-musume/venv-qwen/lib/python3.12/site-packages/diffusers/"
    "models/transformers/transformer_qwenimage21.py")

OLD_RET = ("        return torch.cat([self.freqs[0][frame_index], self.freqs[1][height_index], "
           "self.freqs[2][width_index]], dim=-1)")

NEW_RET = '''        # CANN has no complex kernels, so build the table on CPU and return the
        # real (cos, sin) pair that apply_rotary_emb_qwen(use_real=True) expects.
        if not hasattr(self, "_freqs_cpu"):
            self._freqs_cpu = [f.detach().to("cpu") for f in self.freqs]
        _out = torch.cat([self._freqs_cpu[0][frame_index.detach().to("cpu")],
                          self._freqs_cpu[1][height_index.detach().to("cpu")],
                          self._freqs_cpu[2][width_index.detach().to("cpu")]],
                         dim=-1).to(torch.complex64)
        # D/2 complex entries -> D real entries, duplicated interleaved so the
        # [B, S, H, D] product lines up with x_rotated.
        return (_out.real.repeat_interleave(2, dim=-1).contiguous().to(device),
                _out.imag.repeat_interleave(2, dim=-1).contiguous().to(device))'''

OLD_BCAST = """        cos = cos[None, None]
        sin = sin[None, None]"""
NEW_BCAST = """        # [B, S, H, D] layout (not the flux [B, H, S, D]) -> broadcast on the
        # sequence axis, keep heads as a singleton
        cos = cos[None, :, None, :]
        sin = sin[None, :, None, :]"""

OLD_SLICE = "            rotary_emb = rotary_emb[prefix_len:]"
NEW_SLICE = ("            rotary_emb = (tuple(t[prefix_len:] for t in rotary_emb)\n"
             "                          if isinstance(rotary_emb, tuple) else rotary_emb[prefix_len:])")


def main():
    if not os.path.exists(TARGET):
        print("MISSING %s" % TARGET)
        return 2
    src = io.open(TARGET, encoding="utf-8").read()
    if "_freqs_cpu" in src and "[None, :, None, :]" in src and "isinstance(rotary_emb, tuple)" in src:
        print("already patched")
        return 0

    bak = TARGET + ".orig"
    if not os.path.exists(bak):
        shutil.copy2(TARGET, bak)

    applied = []
    if OLD_RET in src and "_freqs_cpu" not in src:
        src = src.replace(OLD_RET, NEW_RET)
        applied.append("pos_embed->real")
    elif "_freqs_cpu" not in src:
        print("FAIL: rotary return line not found (diffusers layout changed)")
        return 3

    n = 0
    for who in ("query", "key"):
        old = "apply_rotary_emb_qwen(%s, rotary_emb, use_real=False)" % who
        if old in src:
            src = src.replace(old, "apply_rotary_emb_qwen(%s, rotary_emb, use_real=True)" % who)
            n += 1
    if n:
        applied.append("use_real x%d" % n)

    if OLD_BCAST in src:
        src = src.replace(OLD_BCAST, NEW_BCAST)
        applied.append("broadcast")
    if OLD_SLICE in src:
        src = src.replace(OLD_SLICE, NEW_SLICE)
        applied.append("kv-slice")

    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(src)
    print("patched: %s" % (", ".join(applied) or "nothing new"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
