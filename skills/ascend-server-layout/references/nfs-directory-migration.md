# 把本地目录整体搬到 NFS 共享盘（实测流程）

场景：共享存储换盘/换目录，需要把个人目录搬到新位置，同时保证老绝对路径继续可用。

## 1. 先测瓶颈，再选策略

```bash
# 裸带宽（通常很快，不是瓶颈）
dd if=/dev/zero of=$TARGET/.bench bs=1M count=1024
# 单文件创建速率（真正的瓶颈）
t0=$(date +%s); for i in $(seq 1 3000); do : > $TARGET/.b/f$i; done; t1=$(date +%s)
echo "$(( 3000 / (t1 - t0 + 1) )) files/s"
```

实测（A3 190 写入 `suzblue.server:/group/MindSpeed`）：

| 指标 | 数值 |
|---|---|
| NFS 裸写 / 裸读 1 GB | 1.9 GB/s / 1.8 GB/s |
| NFS 空文件创建（串行 shell loop） | 333 /s |
| 本地 ext4 空文件创建 | 3000 /s |
| 单条 `rsync -aH` | ~100 条目/s、~2 MB/s |
| 18 路并行（按顶层目录） | ~700 条目/s |

57.6 GB / 69.6 万条目：串行 ETA 447 min，并行约 15 min。**先跑 90 秒量一下再决定**，别直接开串行。

## 2. 并行切分：按顶层目录，不按文件

```bash
SRC=/home/USER; DST=/mnt/newdisk/USER; W=/root/mig; mkdir -p "$W"
find "$SRC" -mindepth 1 -maxdepth 1 -printf '%P\0' > "$W/entries.bin"
i=0
while IFS= read -r -d '' e; do
  i=$((i + 1))
  ( rsync -aH --numeric-ids "$SRC/$e" "$DST/" > "$W/w$i.log" 2>&1; echo "rc=$? entry=$e" >> "$W/w$i.log" ) &
done < "$W/entries.bin"
wait
echo "ALLDONE $(date -Is)"
```

要点：

- `-printf '%P\0'` + `read -d ''` 才能处理带空格/特殊字符的名字；不要用 `for e in $(ls)`。
- 用**顶层目录**切而不是按文件切：硬链接只可能在同一子树内被保住；跨顶层目录的硬链接会变成独立副本（本轮 +83 MB，可接受，`-H` 只保证 worker 内部）。
- 别给每个 worker 加 `--info=stats2`（日志爆），收尾用 `du`/`find` 看总量。

## 3. 选项：`-aHA`，不要 `-X`

```bash
rsync -aHA --numeric-ids "$SRC/" "$DST/"
```

NFS 导出普遍不支持 xattr：

```
$ setfattr -n user.test -v 1 /mnt/group/MindSpeed/.probe
setfattr: /mnt/group/MindSpeed/.probe: Operation not supported
```

源带 SELinux 标签时 `-X` 会逐文件报错。`setfacl` 实测可用，所以 `-A` 可以留。

## 4. 校验（三层，别只信 rsync 的退出码）

1. **条目数逐项相等**：每个顶层目录 `find SRC/e | wc -l` vs `find DST/e | wc -l`。
2. **结构零差异**：`rsync -aHn --itemize-changes SRC/e DST/ | grep -c '^[<>ch*.dL]'` 应为 0。
3. **抽样校验和**：`find ... | shuf -n 30` 取跨尺寸样本，两侧 `md5sum` 比对。

**坑：NFS 属性缓存造成瞬时假差异。** 刚拷完第一遍能报 34 处差异，隔几分钟复测全归零（`actimeo` 缓存里的 mtime 还没回填）。差异里出现 `.d..t......` 只是目录 mtime，重跑一次该子树即可修掉；不要据此推断丢数据。

字节数用 `du -sb` 比对会因硬链接被复制而不等（本轮差 83 MB），以 rsync 结构比对为准。

## 5. 切换：改名 → 软链 → 验环境 → 删旧树

```bash
mv "$SRC" /home/.USER.OLD          # 同文件系统内瞬间完成，留退路
ln -s "$DST" "$SRC"
ls -ld "$SRC"; find "$SRC/" | wc -l     # 注意末尾斜杠
setsid nohup bash -c "rm -rf /home/.USER.OLD; echo done-\$(date -Is) > /root/rm_old.log" >/dev/null 2>&1 </dev/null &
```

- **`find <软链>` 只输出 1 行**（它不会跟进去），校验时必须写 `find <path>/` 或 `find -L`。
- 删 69.6 万文件的旧树要几分钟，放后台并落日志。
- 原有 `-> SRC` 的二级软链（如 `/home/vllm/USER -> /home/USER`）不用改，链条自动继续成立。

## 6. 切换后必须验环境

路径虽没变，但文件系统从 ext4 变成 NFS，要确认动态库、venv、CANN 还能用：

```bash
cd $SRC/env/../run && source $SRC/ascend-26.2.0/env/activate.sh
python3 -c "import torch, torch_npu, numpy; print(torch.__version__, torch_npu.__version__, numpy.__version__)"
```

本轮实测输出 `torch 2.10.0+cpu / npu 2.10.0.post7 / numpy 1.26.4`，exit 0。

## 7. 边界：为什么有些机器搬不了

机器不能直接以 NFS 客户端身份挂载时，搬到 `/mnt/...` 只是写进**本机空目录**，不是共享盘。开搬前核对：

- `findmnt -n -T <目标路径> -o SOURCE,FSTYPE` 必须是 `nfs`，不是 `/dev/nvme...`。
- 导出允许网段：目标机不在导出白名单时 `showmount -e <server>` 返回空、`mount` 必失败（`MOUNT FAILED`），只能绕跳板或先修网络。
- 镜像/数据没法从这类机器直接落到共享盘时，要么经挂了 NFS 的邻机中转（受它自己的网口带宽限制），要么先修网络。
