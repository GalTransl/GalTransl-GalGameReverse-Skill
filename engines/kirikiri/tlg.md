# Kirikiri TLG5：有界解码与 PNG 转换

## 支持的入口

| 条件 | 处理 |
|---|---|
| 头为 `TLG5.0\0raw\x1a`，颜色通道 3 或 4 | 使用 [kirikiri_tlg.py](../../python/engines/kirikiri_tlg.py) 解码 |
| 需要回写 TLG5 | 支持无损 raw 块编码；不生成 LZSS，文件通常明显大于原图 |
| 头为 `TLG6.0...` | 明确拒绝；未实现 Golomb/中值滤波 |
| `TLG0.0\0sds`、`TLG5.0\0idx`、`TLGqoi`、`TLGmux`、`TLGref` | 明确拒绝，不按 TLG5 raw 猜测 |

`.tlg` 扩展名和 `TLG` 签名只证明候选格式，不能跳过块表、通道数和 LZSS 长度校验。

## 布局

```text
11 bytes  "TLG5.0\0raw\x1a"
u8        colours：3 = BGR，4 = BGRA
u32le     width
u32le     height
u32le     block height
u32le[]   block_count 个压缩块大小（跳过；以流内长度为准）
blocks    每个行块、每个通道：
            u8    mark：0 = TLG5 LZSS，1 = 原始字节
            u32le size
            size 字节 payload
```

每个通道的块解压后是该行块的差分平面；还原顺序：

- 第一行：通道 1 为 G，通道 0 加 G 得 B，通道 2 加 G 得 R，通道 3 为 A；逐像素累加。
- 后续行：先按行内累加，再加前一行同位置像素。
- 3 通道输出的 alpha 固定 `0xff`；4 通道保留解码出的 alpha。

LZSS 使用 4096 字节环形字典，字典状态跨通道、跨行块保留；不能每块重置。输出必须恰好等于 `行数 × 宽度`，越界、截断或长度不符均报错。

## API

```python
from python.engines.kirikiri_tlg import (decode, encode, encode_png,
                                         from_rgba_png, info)

fields = info(data)                 # version/width/height/channels/data_offset
image = decode(data)                # TlgImage(width, height, channels, pixels)
png = encode_png(image)             # RGBA PNG bytes，标准库 zlib
data2 = encode(image, block_height=16)   # TLG5 raw，块表按实际字节数写回
image2 = from_rgba_png("edited.png")     # 需要 Pillow，RGBA -> BGRA
```

`pixels` 是 BGRA（4 通道）或 BGR + `0xff`（3 通道），stride 为 `width * 4`。`encode_png` 在写出时转换为 RGBA，不改变解码缓冲；`encode` 只写 raw 块（mark 1），逐字节无损，不生成 LZSS。

## 命令行

```text
python -m python.engines.kirikiri_tlg info <文件.tlg>
python -m python.engines.kirikiri_tlg convert <文件.tlg> <输出.png>
python -m python.engines.kirikiri_tlg convert <目录> <新的输出目录>
python -m python.engines.kirikiri_tlg encode <编辑后.png> <输出.tlg>
```

目录模式递归查找 `*.tlg`，按相对路径写出同名 `.png`；输出目录必须不存在，不会覆盖已有文件。单文件与 `encode` 模式同样拒绝已存在的输出路径。`encode` 需要 Pillow 读取 PNG；解码路径只用标准库。

## 预算与失败处理

- 输入上限 `256 MiB`；单图像素数上限 `64,000,000`；目录累计像素上限 `500,000,000`，文件数上限 `10,000`。
- LZSS 解码缓冲区按“期望像素数”分配，输出超出或不足都拒绝。
- 块表、通道 payload、`mark` 和尾随字节都做边界校验；尾随字节当前视为错误，不静默忽略。
- 解码只读内存，不执行游戏代码，不加载 DLL/EXE。

## 验证

- 合成回归：[test_kirikiri_tlg.py](../../tests/test_kirikiri_tlg.py) 覆盖 3/4 通道、原始块、LZSS 字面量、LZSS 匹配、跨行块、PNG 扫描线、PNG→TLG5 编码往返和错误拒绝。
- `encode` 只验证“解码→编码→再解码”的像素一致性与块表长度，未验证游戏加载器接受 raw 块。
- 未验证项：TLG6、TLG0/idx/qoi/mux/ref、LZSS 编码、游戏内显示。
- 本页不记录具体游戏的验证流水账；样本运行结果只放对应游戏结果目录。

## 出处与许可

TLG5 解码布局、LZSS 与差分还原移植自 GARbro-Mod
`ArcFormats/KiriKiri/ImageTLG.cs`（MIT，Copyright (c) 2014-2020 morkt）；
该实现本身是 W.Dee TLG5/6 解码器的 C# 移植（Copyright (C) 2000-2005 W.Dee）。
完整 MIT 文本见 [provenance/licenses/MIT-GARbro.txt](../../provenance/licenses/MIT-GARbro.txt)，
来源清单见 [provenance/kirikiri-sources.json](../../provenance/kirikiri-sources.json)。
