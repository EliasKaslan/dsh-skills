#!/usr/bin/env python3
"""Bounded, read-only safetensors header/index audit. Does not hash payloads."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
from pathlib import Path, PurePosixPath
import struct
import sys

BITS = {"BOOL": 8, "U8": 8, "I8": 8, "I16": 16, "U16": 16,
        "I32": 32, "U32": 32, "I64": 64, "U64": 64, "F16": 16,
        "BF16": 16, "F32": 32, "F64": 64, "F8_E4M3": 8,
        "F8_E4M3FN": 8, "F8_E5M2": 8, "F8_E8M0": 8}

def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj

def load_json(text):
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite JSON")))

def integer(value):
    return type(value) is int and value >= 0

def shard(path, max_header):
    size = path.stat().st_size  # follows valid model-cache symlinks
    with path.open("rb") as stream:
        prefix = stream.read(200)
        if prefix.startswith(b"version https://git-lfs.github.com/spec/"):
            raise ValueError("Git LFS pointer, not tensor payload")
        if size < 8:
            raise ValueError("truncated length prefix")
        length = struct.unpack("<Q", prefix[:8])[0]
        if length < 2 or length > max_header or length > size-8:
            raise ValueError(f"invalid/oversized header: {length} bytes (limit {max_header})")
        stream.seek(8)
        raw = stream.read(length)
        if len(raw) != length:
            raise ValueError("truncated header")
    if raw[:1] != b"{":
        raise ValueError("header must start with JSON object")
    header = load_json(raw.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("header must be an object")
    payload = size-8-length
    ranges, types, tensors, unknown = [], Counter(), {}, set()
    meta = header.get("__metadata__", {})
    if not isinstance(meta, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in meta.items()):
        raise ValueError("metadata must contain string values")
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"invalid tensor descriptor: {name}")
        dtype, shape, offsets = entry.get("dtype"), entry.get("shape"), entry.get("data_offsets")
        if not isinstance(dtype, str) or not isinstance(shape, list) or not all(integer(x) for x in shape):
            raise ValueError(f"invalid dtype/shape: {name}")
        if not isinstance(offsets, list) or len(offsets) != 2 or not all(integer(x) for x in offsets):
            raise ValueError(f"invalid offsets: {name}")
        start, end = offsets
        if start > end or end > payload:
            raise ValueError(f"out-of-bounds tensor: {name}")
        if dtype in BITS:
            expected = math.prod(shape)*BITS[dtype]//8
            if expected != end-start:
                raise ValueError(f"shape/size mismatch: {name}")
        else:
            unknown.add(dtype)
        ranges.append((start, end, name))
        types[dtype] += 1
        tensors[name] = {"dtype": dtype, "shape": shape, "bytes": end-start}
    cursor = 0
    for start, end, name in sorted(ranges):
        if start != cursor:
            raise ValueError(f"overlap or hole before tensor: {name}")
        cursor = end
    if cursor != payload:
        raise ValueError("unindexed trailing payload")
    return {"file_bytes": size, "payload_bytes": payload, "header_bytes": length,
            "dtype_counts": dict(types), "unknown_dtypes": sorted(unknown), "tensors": tensors}

def inspect(root, max_header=16*1024**2):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("model directory does not exist")
    result = {"model_dir": str(root.resolve()), "scope": "headers/index only; payload checksums and model loading NOT VERIFIED",
              "errors": [], "warnings": [], "shards": {}, "dtype_counts": {}}
    errors = result["errors"]
    index_path = root / "model.safetensors.index.json"
    mapping, declared_total = None, None
    files = {p.name for p in root.glob("*.safetensors")}
    if index_path.exists():
        index = load_json(index_path.read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            raise ValueError("index must be an object")
        mapping = index.get("weight_map")
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("index weight_map must be nonempty")
        for tensor, rel in mapping.items():
            if not isinstance(tensor, str) or not isinstance(rel, str):
                raise ValueError("invalid index mapping")
            parts = PurePosixPath(rel)
            if parts.is_absolute() or ".." in parts.parts or "\\" in rel or ":" in rel or not rel.endswith(".safetensors"):
                raise ValueError("unsafe/unsupported index shard path")
        indexed = set(mapping.values())
        if files-indexed:
            result["warnings"].append("unreferenced top-level shards also inspected: "+", ".join(sorted(files-indexed)))
        files |= indexed
        metadata = index.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("index metadata must be an object")
        declared_total = metadata.get("total_size")
        if declared_total is not None and not integer(declared_total):
            raise ValueError("invalid index total_size")
        result["indexed_shard_count"] = len(indexed)
    elif len(files) > 1:
        result["warnings"].append("multiple shards without index: model coverage cannot be verified")
    config_path = root / "config.json"
    if config_path.exists():
        config = load_json(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config must be an object")
        text = config.get("text_config")
        if text is None:
            text = config
        if not isinstance(text, dict):
            raise ValueError("text_config must be an object")
        result["config"] = {"architectures": config.get("architectures"),
                            "declared_dtype": text.get("dtype", text.get("torch_dtype")),
                            "has_quantization_config": bool(config.get("quantization_config") or text.get("quantization_config"))}
    else:
        result["warnings"].append("config.json missing: architecture/loadability NOT VERIFIED")
    if not files:
        errors.append("no safetensors files")
    locations, counts, unknown = {}, Counter(), set()
    for name in sorted(files):
        try:
            info = shard(root / name, max_header)
            for tensor in info["tensors"]:
                locations.setdefault(tensor, []).append(name)
            counts.update(info["dtype_counts"])
            unknown.update(info["unknown_dtypes"])
            result["shards"][name] = {key:value for key,value in info.items() if key != "tensors"}
        except (OSError, ValueError, UnicodeError, struct.error) as exc:
            errors.append(f"{name}: {exc}")
    if mapping is not None:
        for tensor, name in mapping.items():
            if name not in locations.get(tensor, []):
                errors.append(f"index tensor missing from assigned shard: {tensor} -> {name}")
        for tensor, names in locations.items():
            if len(names) > 1:
                errors.append(f"duplicate tensor across shards: {tensor}")
            if tensor not in mapping:
                errors.append(f"tensor absent from weight_map: {tensor}")
        indexed_bytes = sum(result["shards"].get(name, {}).get("payload_bytes", 0) for name in set(mapping.values()))
        if declared_total is not None and declared_total != indexed_bytes:
            errors.append("index total_size differs from indexed tensor payload bytes")
    elif any(len(names) > 1 for names in locations.values()):
        errors.append("duplicate tensors across unindexed shards")
    if not locations:
        errors.append("no tensor descriptors found")
    result.update(shard_count=len(result["shards"]), dtype_counts=dict(counts), tensor_count=len(locations),
                  file_bytes=sum(info["file_bytes"] for info in result["shards"].values()), unknown_dtypes=sorted(unknown))
    if unknown:
        result["warnings"].append("unknown dtype sizes; shape-byte validation incomplete")
    result["verdict"] = "FAIL" if errors else "INCONCLUSIVE" if result["warnings"] else "STRUCTURE_PASS"
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model_dir")
    ap.add_argument("--max-header-mib", type=int, default=16)
    args = ap.parse_args(argv)
    if args.max_header_mib <= 0:
        ap.error("max-header-mib must be positive")
    try:
        result = inspect(args.model_dir, args.max_header_mib*1024**2)
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"verdict": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["verdict"] == "FAIL" else 2 if result["verdict"] == "INCONCLUSIVE" else 0

if __name__ == "__main__":
    sys.exit(main())
