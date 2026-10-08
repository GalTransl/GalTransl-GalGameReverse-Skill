# HuneX / ArcMZP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MZP` / `GameRes.Formats.HuneX.MrgOpener` | `mzp` | `6d726764` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MrgOpener.TryOpen` | `if (!file.View.AsciiEqual(4, "00"))` |
| `MrgOpener.TryOpen` | `int count = file.View.ReadInt16(6);` |
| `MrgOpener.TryOpen` | `uint section_offset = file.View.ReadUInt16(offset);` |
| `MrgOpener.TryOpen` | `uint file_offset = file.View.ReadUInt16(offset + 2);` |
| `MrgOpener.TryOpen` | `uint size_boundary = file.View.ReadUInt16(offset + 4);` |
| `MrgOpener.TryOpen` | `uint size = file.View.ReadUInt16(offset + 6);` |
| `MrgOpener.ReadInfo` | `metadata.Width = file.View.ReadUInt16(entry.Offset);` |
| `MrgOpener.ReadInfo` | `metadata.Height = file.View.ReadUInt16(entry.Offset + 2);` |
| `MrgOpener.ReadInfo` | `metadata.TileWidth = file.View.ReadUInt16(entry.Offset + 4);` |
| `MrgOpener.ReadInfo` | `metadata.TileHeight = file.View.ReadUInt16(entry.Offset + 6);` |
| `MrgOpener.ReadInfo` | `metadata.TileXCount = file.View.ReadUInt16(entry.Offset + 8);` |
| `MrgOpener.ReadInfo` | `metadata.TileYCount = file.View.ReadUInt16(entry.Offset + 10);` |
| `MrgOpener.ReadInfo` | `ushort type = file.View.ReadUInt16(entry.Offset + 12);` |
| `MrgOpener.ReadInfo` | `byte depth = file.View.ReadByte(entry.Offset + 14);` |
| `MrgOpener.ReadInfo` | `metadata.TileCrop = file.View.ReadByte(entry.Offset + 15);` |
| `MzxImageReader.Unpack` | `ushort pq = BitConverter.ToUInt16(rgb565, i * 2);` |
| `MzxImageReader.UnpackHep` | `if (m_input.ReadUInt32() != 0x00504548)` |
| `MzxImageReader.UnpackHep` | `m_input.ReadBytes(0x10);` |
| `MzxImageReader.UnpackHep` | `m_width = m_input.ReadUInt32();` |
| `MzxImageReader.UnpackHep` | `m_height = m_input.ReadUInt32();` |
| `MzxImageReader.UnpackHep` | `m_input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.HuneX.MzpMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public uint TileWidth { get; set; }

public uint TileHeight { get; set; }

public uint TileXCount { get; set; }

public uint TileYCount { get; set; }

public uint Characteristics { get; set; }

public uint Depth { get; set; }

public uint TileCrop { get; set; }

public BitmapPalette Palette { get; set; }
```

### GameRes.Formats.HuneX.MzpArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public MzpMetaData MetaData { get; set; }
```

#### MzpArchive

```csharp
public MzpArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, MzpMetaData metadata) : base (arc, impl, dir) {
    MetaData = metadata;
}
```

### GameRes.Formats.HuneX.MzpEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int Index { get; set; }
```

### GameRes.Formats.HuneX.MrgOpener

继承/接口：`ArchiveFormat`。

#### MrgOpener

```csharp
public MrgOpener() {
    Extensions = new string[] { "mzp" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.View.AsciiEqual(4, "00"))
        return null;

    int count = file.View.ReadInt16(6);
    if (!IsSaneCount(count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension(file.Name);
    MzpMetaData metadata = null;

    var dir = new List<Entry>(count);
    uint offset = 8;
    for (int i = 0; i < count; i++) {
        uint section_offset = file.View.ReadUInt16(offset);
        uint file_offset = file.View.ReadUInt16(offset + 2);
        uint size_boundary = file.View.ReadUInt16(offset + 4);
        uint size = file.View.ReadUInt16(offset + 6);
        var entry = new MzpEntry {
            Offset = 8 * (count + 1) + section_offset * 0x800 + file_offset,
            Size = (size_boundary - 1) / 0x20 * 0x800 * 0x20 + size
        };
        if (!entry.CheckPlacement(file.MaxOffset))
            return null;
        if (i == 0)
            metadata = ReadInfo(file, entry);
        else {
            entry.Name = string.Format("{0}#{1:D3}", base_name, i);
            entry.Type = "image";
            entry.Index = i;
            dir.Add(entry);
        }
        offset += 8;
    }

    if (metadata == null)
        return null;
    return new MzpArchive(file, this, dir, metadata);
}
```

#### ReadInfo

```csharp
MzpMetaData ReadInfo(ArcView file, Entry entry) {
    if (entry.Size < 16)
        return null;

    MzpMetaData metadata = new MzpMetaData();
    metadata.Width = file.View.ReadUInt16(entry.Offset);
    metadata.Height = file.View.ReadUInt16(entry.Offset + 2);
    metadata.TileWidth = file.View.ReadUInt16(entry.Offset + 4);
    metadata.TileHeight = file.View.ReadUInt16(entry.Offset + 6);
    metadata.TileXCount = file.View.ReadUInt16(entry.Offset + 8);
    metadata.TileYCount = file.View.ReadUInt16(entry.Offset + 10);
    ushort type = file.View.ReadUInt16(entry.Offset + 12);
    metadata.Characteristics = type;
    byte depth = file.View.ReadByte(entry.Offset + 14);
    metadata.Depth = depth;
    metadata.TileCrop = file.View.ReadByte(entry.Offset + 15);

    if (type == 1 && (depth & 0xf) == 0)
        metadata.BPP = 4;
    else if (type == 1 && (depth & 0xf) == 1)
        metadata.BPP = 8;
    else if (type == 8 && depth == 0x14)
        metadata.BPP = 24;
    else if ((type == 0xb && depth == 0x14) || (type == 0xc && depth == 0x11))
        metadata.BPP = 32;
    else
        throw new NotImplementedException("[MZP] Unsupported BPP type");

    if (type == 1) {
        int palette_size = (depth & 0xf) == 1 ? 256 : 16;
        var raw_palette = new byte[0x400];
        file.View.Read(entry.Offset + 16, raw_palette, 0, (uint)palette_size * 4);
        if (depth == 0x11 || depth == 0x91) {
            for (int i = 0; i < palette_size; i += 32) {
                var block = new byte[32];
                Buffer.BlockCopy(raw_palette, (i + 8) * 4, block, 0, block.Length);
                Buffer.BlockCopy(raw_palette, (i + 16) * 4, raw_palette, (i + 8) * 4, block.Length);
                Buffer.BlockCopy(block, 0, raw_palette, (i + 16) * 4, block.Length);
            }
        }
        for (int i = palette_size; i < 256; i++)
            raw_palette[i * 4 + 3] = 0xFF;
        metadata.Palette = MzxImageReader.GetPaletteFromRaw(raw_palette);
    }
    else {
        metadata.Palette = null;
    }

    return metadata;
}
```

### GameRes.Formats.HuneX.MzxImageReader

继承/接口：`IImageDecoder`。

#### 状态与常量

```csharp
IBinaryStream m_input ;

byte[]        m_output ;

MzpMetaData   m_info ;

uint          m_height ;

uint          m_width ;

public byte[]           Data { get { return m_output; } }

public PixelFormat    Format { get; private set; }

public BitmapPalette Palette { get; private set; }

public Stream Source { get { m_input.Position = 0; return m_input.AsStream; } }

public ImageFormat SourceFormat { get { return null; } }

public ImageMetaData Info {
    get {
        return new ImageMetaData {
            Height = m_height,
            Width = m_width,
            BPP = Format.BitsPerPixel
        };
    }
}

public ImageData Image {
    get {
        if (null == m_output)
            Unpack();
        return ImageData.Create(Info, Format, Palette, Data);
    }
}

bool m_disposed = false ;
```

#### MzxImageReader

```csharp
public MzxImageReader(IBinaryStream input, MzpMetaData info) {
    m_input = input;
    m_info = info;
    m_height = m_info.TileHeight;
    m_width = m_info.TileWidth;
    Palette = m_info.Palette;
    switch (m_info.BPP) {
        case 4:
        case 8: Format = PixelFormats.Indexed8; break;
        case 24: Format = PixelFormats.Bgr24; break;
        case 32: Format = PixelFormats.Bgra32; break;
        default: throw new InvalidFormatException();
    }
}
```

#### Unpack

```csharp
public void Unpack() {
    if (m_info.Characteristics == 0xC) {
        UnpackHep();
        return;
    }
    uint tile_size = m_height * m_width;
    m_output = new byte[tile_size * (m_info.BPP + 4) / 8];

    uint index = 0;
    switch (m_info.BPP) {
        case 4:
            byte[] temp4 = new byte[(tile_size + 1) / 2];
            m_input.Read(temp4, 0, temp4.Length);
            for (int i = 0; i < temp4.Length; i++) {
                m_output[index++] = (byte)(temp4[i] & 0x0F);
                if (index < tile_size)
                    m_output[index++] = (byte)(temp4[i] >> 4);
            }
            break;

        case 8:
            m_input.Read(m_output, 0, m_output.Length);
            break;

        case 24:
        case 32:
            byte[] rgb565 = new byte[tile_size * 2];
            m_input.Read(rgb565, 0, rgb565.Length);
            byte[] offsets = new byte[tile_size];
            m_input.Read(offsets, 0, offsets.Length);
            byte[] alphas = null;
            if (m_info.BPP == 32) {
                alphas = new byte[tile_size];
                m_input.Read(alphas, 0, alphas.Length);
            }
            for (int i = 0; i < tile_size; i++) {
                ushort pq = BitConverter.ToUInt16(rgb565, i * 2);
                byte offset_byte = offsets[i];
                byte r = (byte)(((pq & 0xF800) >> 8) | ((offset_byte >> 5) & 7));
                byte g = (byte)(((pq & 0x07E0) >> 3) | ((offset_byte >> 3) & 3));
                byte b = (byte)(((pq & 0x001F) << 3) | (offset_byte & 7));
                m_output[index++] = b;
                m_output[index++] = g;
                m_output[index++] = r;
                if (alphas != null)
                    m_output[index++] = alphas[i];
            }
            break;
    }
}
```

#### UnpackHep

```csharp
void UnpackHep() {
    if (m_input.ReadUInt32() != 0x00504548)
        throw new InvalidFormatException();
    m_input.ReadBytes(0x10);
    m_width = m_input.ReadUInt32();
    m_height = m_input.ReadUInt32();
    m_input.ReadUInt32();
    Format = PixelFormats.Indexed8;
    m_output = new byte[m_height * m_width];
    m_input.Read(m_output, 0, m_output.Length);

    var raw_palette = new byte[0x400];
    m_input.Read(raw_palette, 0, raw_palette.Length);
    Palette = GetPaletteFromRaw(raw_palette);
}
```

#### GetPaletteFromRaw

```csharp
public static BitmapPalette GetPaletteFromRaw(byte[] raw_palette) {
    var colors = new Color[raw_palette.Length / 4];
    for (int i = 0; i < raw_palette.Length; i += 4) {
        byte r = raw_palette[i];
        byte g = raw_palette[i + 1];
        byte b = raw_palette[i + 2];
        byte a = raw_palette[i + 3];

        if ((a & 0x80) == 0)
            a = (byte)(((a << 1) | (a >> 6)) & 0xFF);
        else
            a = 0xFF;

        colors[i / 4] = Color.FromArgb(a, r, g, b);
    }
    return new BitmapPalette(colors);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/HuneX/ArcMZP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
