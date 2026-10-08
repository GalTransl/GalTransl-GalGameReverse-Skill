# Sas5 / ArcIAR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IAR` / `GameRes.Formats.Sas5.IarOpener` | `iar` | `69617220` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IarOpener.TryOpen` | `int version = file.View.ReadInt16 (4);` |
| `IarOpener.TryOpen` | `int file_count = file.View.ReadInt32 (0x18);` |
| `IarOpener.TryOpen` | `int count = file.View.ReadInt32 (0x1C);` |
| `IarOpener.TryOpen` | `ReadOffset = x => file.View.ReadUInt32 (x);` |
| `IarOpener.TryOpen` | `ReadOffset = x => file.View.ReadInt64 (x);` |
| `IarOpener.OpenEntry` | `int flags = arc.File.View.ReadUInt16 (entry.Offset);` |
| `IarOpener.CombineImage` | `int base_index = input.ReadInt32();` |
| `IarOpener.CombineImage` | `int diff_y      = input.ReadInt32();` |
| `IarOpener.CombineImage` | `int diff_count  = input.ReadInt32();` |
| `IarOpener.CombineImage` | `int chunk_count = input.ReadUInt16();` |
| `IarOpener.CombineImage` | `int skip_count = pixel_size * input.ReadUInt16();` |
| `IarOpener.CombineImage` | `int copy_count = pixel_size * input.ReadUInt16();` |
| `IarOpener.CombineLayers` | `int cmd = input.ReadUInt8();` |
| `IarOpener.CombineLayers` | `offset_x += input.ReadInt16();` |
| `IarOpener.CombineLayers` | `offset_y += input.ReadInt16();` |
| `IarOpener.CombineLayers` | `int index = input.ReadInt32();` |
| `IarImage.IarImage` | `int flags = iarc.File.View.ReadUInt16 (entry.Offset);` |
| `IarImage.IarImage` | `Compressed = iarc.File.View.ReadByte (offset+3) != 0,` |
| `IarImage.IarImage` | `Width   = iarc.File.View.ReadUInt32 (offset+0x20),` |
| `IarImage.IarImage` | `Height  = iarc.File.View.ReadUInt32 (offset+0x24),` |
| `IarImage.IarImage` | `Stride  = iarc.File.View.ReadInt32 (offset+0x28),` |
| `IarImage.IarImage` | `OffsetX = iarc.File.View.ReadInt32 (offset+0x18),` |
| `IarImage.IarImage` | `OffsetY = iarc.File.View.ReadInt32 (offset+0x1C),` |
| `IarImage.IarImage` | `UnpackedSize = iarc.File.View.ReadInt32 (offset+8),` |
| `IarImage.IarImage` | `PaletteSize = iarc.File.View.ReadUInt32 (offset+0xC),` |
| `IarImage.IarImage` | `PackedSize = iarc.File.View.ReadInt32 (offset+0x10),` |
| `IarDecompressor.Unpack` | `output[dst++] = m_input.ReadUInt8();` |
| `IarDecompressor.Unpack` | `offset += (tmp << 8) \| m_input.ReadUInt8();` |
| `IarDecompressor.Unpack` | `count = 17 + m_input.ReadUInt8();` |
| `IarDecompressor.Unpack` | `offset = (offset \| m_input.ReadUInt8()) + 0x100;` |
| `IarDecompressor.Unpack` | `offset = 1 + m_input.ReadUInt8();` |
| `IarDecompressor.GetNextBit` | `m_bits = m_input.ReadUInt16() \| 0x10000;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sas5.IarArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly int Version ;
```

#### IarArchive

```csharp
public IarArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version)
    : base (arc, impl, dir) {
    Version = version;
}
```

### GameRes.Formats.Sas5.IarImageInfo

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int  Flags ;

public bool Compressed ;

public uint PaletteSize ;

public int  PackedSize ;

public int  UnpackedSize ;

public int  Stride ;
```

### GameRes.Formats.Sas5.IarOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt16 (4);
    if (version < 1 || version > 4)
        return null;
    int file_count = file.View.ReadInt32 (0x18);
    int count = file.View.ReadInt32 (0x1C);
    if (count < file_count || !IsSaneCount (count))
        return null;

    var index = Sec5Opener.LookupIndex (file.Name);
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    Func<int, Entry> CreateEntry;
    if (null == index)
        CreateEntry = n => GetDefaultEntry (base_name, n);
    else
        CreateEntry = (n) => {
            Entry entry;
            if (index.TryGetValue (n, out entry))
                return new Entry { Name = entry.Name, Type = entry.Type };
            return GetDefaultEntry (base_name, n);
        };

    uint offset_size = version < 3 ? 4u : 8u;
    Func<uint, long> ReadOffset;
    if (version < 3)
        ReadOffset = x => file.View.ReadUInt32 (x);
    else
        ReadOffset = x => file.View.ReadInt64 (x);

    uint index_offset = 0x20;
    var dir = new List<Entry> (count);
    var next_offset = ReadOffset (index_offset);
    for (int i = 0; i < count; ++i)
    {
        var entry = CreateEntry (i);
        entry.Offset = next_offset;
        index_offset += offset_size;
        next_offset = (i + 1) == count ? file.MaxOffset : ReadOffset (index_offset);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new IarArchive (file, this, dir, version);
}
```

#### GetDefaultEntry

```csharp
static Entry GetDefaultEntry (string base_name, int n) {
    return new Entry {
        Name = string.Format ("{0}#{1:D5}", base_name, n),
        Type = "image",
    };
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var iarc = arc as IarArchive;
    if (null == iarc)
        return base.OpenEntry (arc, entry);
    try
    {
        int flags = arc.File.View.ReadUInt16 (entry.Offset);

        var image = new IarImage (iarc, entry);
        if (0 != (flags & 0x1000))
            image = CombineLayers (image, iarc);
        else if (0 != (flags & 0x800))
            image = CombineImage (image, iarc);
        if (null == image)
            return base.OpenEntry (arc, entry);

        var header = new byte[0x28+image.Info.PaletteSize];
        using (var mem = new MemoryStream (header))
        using (var writer = new BinaryWriter (mem))
        {
            writer.Write (0x00524149);
            writer.Write (0x35534153);
            writer.Write (image.Info.Width);
            writer.Write (image.Info.Height);
            writer.Write (image.Info.OffsetX);
            writer.Write (image.Info.OffsetY);
            writer.Write (image.Info.BPP);
            writer.Write (image.Info.Stride);
            writer.Write (image.Info.PaletteSize);
            writer.Write (image.Data.Length);
            if (null != image.Palette)
                writer.Write (image.Palette, 0, image.Palette.Length);
            return new PrefixStream (header, new MemoryStream (image.Data));
        }
    }
    catch (Exception X)
    {
        Trace.WriteLine (X.Message, entry.Name);
        return base.OpenEntry (arc, entry);
    }
}
```

#### CombineImage

```csharp
IarImage CombineImage (IarImage overlay, IarArchive iarc) {
    using (var input = new BinMemoryStream (overlay.Data))
    {
        var dir = (List<Entry>)iarc.Dir;
        int base_index = input.ReadInt32();
        if (base_index >= dir.Count)
            throw new InvalidFormatException ("Invalid base image index");
        int diff_y      = input.ReadInt32();
        int diff_count  = input.ReadInt32();

        var overlay_info = overlay.Info;
        int pixel_size = overlay_info.BPP / 8;
        var base_image = new IarImage (iarc, dir[base_index]);
        byte[] output = base_image.Data;
        if (overlay_info.Height != base_image.Info.Height || overlay_info.Stride != base_image.Info.Stride)
        {
            int src_height = (int)Math.Min (overlay_info.Height, base_image.Info.Height);
            int src_stride = Math.Min (overlay_info.Stride, base_image.Info.Stride);
            byte[] src = base_image.Data;
            output = new byte[overlay_info.Height * overlay_info.Stride];
            int dst_pos = 0;
            if (base_image.Info.OffsetY < overlay_info.OffsetY)
                dst_pos += (-base_image.Info.OffsetY + overlay_info.OffsetY) * overlay_info.Stride;
            if (base_image.Info.OffsetX < overlay_info.OffsetX)
                dst_pos += (-base_image.Info.OffsetX + overlay_info.OffsetX) * pixel_size;
            for (int y = 0; y < src_height; ++y)
            {
                Buffer.BlockCopy (src, y * base_image.Info.Stride, output, dst_pos, src_stride);
                dst_pos += overlay_info.Stride;
            }
        }
        int dst = diff_y * overlay_info.Stride;
        for (int i = 0; i < diff_count; ++i)
        {
            int chunk_count = input.ReadUInt16();
            int x = 0;
            for (int j = 0; j < chunk_count; ++j)
            {
                int skip_count = pixel_size * input.ReadUInt16();
                int copy_count = pixel_size * input.ReadUInt16();

                x += skip_count;
                input.Read (output, dst+x, copy_count);
                x += copy_count;
            }
            dst += overlay_info.Stride;
        }
        return new IarImage (overlay_info, output, overlay.Palette);
    }
}
```

#### CombineLayers

```csharp
IarImage CombineLayers (IarImage layers, IarArchive iarc) {
    layers.Info.Stride = (int)layers.Info.Width * 4;
    layers.Info.BPP = 32;
    var pixels = new byte[layers.Info.Stride * (int)layers.Info.Height];
    var output = new IarImage (layers.Info, pixels);
    using (var input = new BinMemoryStream (layers.Data))
    {
        int offset_x = 0, offset_y = 0;
        var dir = (List<Entry>)iarc.Dir;
        while (input.Position < input.Length)
        {
            int cmd = input.ReadUInt8();
            switch (cmd)
            {
            case 0x21:
                offset_x += input.ReadInt16();
                offset_y += input.ReadInt16();
                break;

            case 0x00:
            case 0x20:
                {
                    int index = input.ReadInt32();
                    if (index < 0 || index >= dir.Count)
                        throw new InvalidFormatException ("Invalid image layer index");
                    var layer = new IarImage (iarc, dir[index]);
                    layer.Info.OffsetX -= offset_x;
                    layer.Info.OffsetY -= offset_y;
                    if (0x20 == cmd)
                        output.ApplyMask (layer);
                    else
                        output.Blend (layer);
                }
                break;

            default:
                Trace.WriteLine (string.Format ("Unknown layer type 0x{0:X2}", cmd), "IAR");
                break;
            }
        }
        return output;
    }
}
```

### GameRes.Formats.Sas5.IarImage

#### 状态与常量

```csharp
IarImageInfo    m_info ;

byte[]          m_palette ;

byte[]          m_output ;

public IarImageInfo Info { get { return m_info; } }

public byte[]    Palette { get { return m_palette; } }

public byte[]       Data { get { return m_output; } }
```

#### IarImage

```csharp
public IarImage (IarArchive iarc, Entry entry) {
    int flags = iarc.File.View.ReadUInt16 (entry.Offset);
    int bpp;
    switch (flags & 0x3E)
    {
    case 0x02:  bpp = 8; break;
    case 0x1C:  bpp = 24; break;
    case 0x3C:  bpp = 32; break;
    default:    throw new NotSupportedException ("Not supported IAR image format");
    }
    var offset = entry.Offset;
    m_info = new IarImageInfo
    {
        Flags   = flags,
        BPP     = bpp,
        Compressed = iarc.File.View.ReadByte (offset+3) != 0,
        Width   = iarc.File.View.ReadUInt32 (offset+0x20),
        Height  = iarc.File.View.ReadUInt32 (offset+0x24),
        Stride  = iarc.File.View.ReadInt32 (offset+0x28),
        OffsetX = iarc.File.View.ReadInt32 (offset+0x18),
        OffsetY = iarc.File.View.ReadInt32 (offset+0x1C),
        UnpackedSize = iarc.File.View.ReadInt32 (offset+8),
        PaletteSize = iarc.File.View.ReadUInt32 (offset+0xC),
        PackedSize = iarc.File.View.ReadInt32 (offset+0x10),
    };
    uint header_size = 1 == iarc.Version ? 0x30u : iarc.Version < 4 ? 0x40u : 0x48u;
    offset += header_size;
    uint input_size = entry.Size - header_size;

    if (m_info.PaletteSize > 0)
    {
        m_palette = new byte[m_info.PaletteSize];
        iarc.File.View.Read (offset, m_palette, 0, m_info.PaletteSize);
        offset += m_info.PaletteSize;
        input_size -= m_info.PaletteSize;
    }
    m_output = new byte[m_info.UnpackedSize];
    using (var input = iarc.File.CreateStream (offset, input_size))
    {
        if (m_info.Compressed)
        {
            using (var reader = new IarDecompressor (input))
                reader.Unpack (m_output);
        }
        else
            input.Read (m_output, 0, m_output.Length);
    }
}
```

#### IarImage

```csharp
public IarImage (IarImageInfo info, byte[] pixels, byte[] palette = null) {
    m_info = info;
    m_output = pixels;
    m_palette = palette;
}
```

#### Blend

```csharp
public void Blend (IarImage overlay) {
    int pixel_size = Info.Stride / (int)Info.Width;
    if (pixel_size < 4)
        return;
    var self = new Rectangle (-Info.OffsetX, -Info.OffsetY, (int)Info.Width, (int)Info.Height);
    var src = new Rectangle (-overlay.Info.OffsetX, -overlay.Info.OffsetY,
                             (int)overlay.Info.Width, (int)overlay.Info.Height);
    var blend = Rectangle.Intersect (self, src);
    if (blend.IsEmpty)
        return;
    src.X = blend.Left - src.Left;
    src.Y = blend.Top - src.Top;
    src.Width = blend.Width;
    src.Height= blend.Height;
    if (src.Width <= 0 || src.Height <= 0)
        return;

    int x = blend.Left - self.Left;
    int y = blend.Top - self.Top;
    int dst = y * Info.Stride + x * pixel_size;
    int ov = src.Top * overlay.Info.Stride + src.Left * pixel_size;
    for (int row = 0; row < src.Height; ++row)
    {
        for (int col = 0; col < src.Width; ++col)
        {
            int src_pixel = ov + col*pixel_size;
            int src_alpha = overlay.Data[src_pixel+3];
            if (src_alpha > 0)
            {
                int dst_pixel = dst + col*pixel_size;
                if (0xFF == src_alpha || 0 == m_output[dst_pixel+3])
                {
                    Buffer.BlockCopy (overlay.Data, src_pixel, m_output, dst_pixel, pixel_size);
                }
                else
                {
                    m_output[dst_pixel+0] = (byte)((overlay.Data[src_pixel+0] * src_alpha
                                             + m_output[dst_pixel+0] * (0xFF - src_alpha)) / 0xFF);
                    m_output[dst_pixel+1] = (byte)((overlay.Data[src_pixel+1] * src_alpha
                                             + m_output[dst_pixel+1] * (0xFF - src_alpha)) / 0xFF);
                    m_output[dst_pixel+2] = (byte)((overlay.Data[src_pixel+2] * src_alpha
                                             + m_output[dst_pixel+2] * (0xFF - src_alpha)) / 0xFF);
                    m_output[dst_pixel+3] = (byte)Math.Max (src_alpha, m_output[dst_pixel+3]);
                }
            }
        }
        dst += Info.Stride;
        ov  += overlay.Info.Stride;
    }
}
```

#### ApplyMask

```csharp
public void ApplyMask (IarImage mask) {
    int pixel_size = Info.Stride / (int)Info.Width;
    if (pixel_size < 4 || mask.Info.BPP != 8)
        return;
    var self = new Rectangle (-Info.OffsetX, -Info.OffsetY, (int)Info.Width, (int)Info.Height);
    var mask_region = new Rectangle (-mask.Info.OffsetX, -mask.Info.OffsetY,
                                     (int)mask.Info.Width, (int)mask.Info.Height);
    var masked = Rectangle.Intersect (self, mask_region);
    if (masked.IsEmpty)
        return;
    mask_region.X = masked.Left - mask_region.Left;
    mask_region.Y = masked.Top - mask_region.Top;
    mask_region.Width = masked.Width;
    mask_region.Height= masked.Height;
    if (mask_region.Width <= 0 || mask_region.Height <= 0)
        return;

    int x = masked.Left - self.Left;
    int y = masked.Top - self.Top;
    int dst = y * Info.Stride + x * pixel_size;
    int src = mask_region.Top * mask.Info.Stride + mask_region.Left;
    for (int row = 0; row < mask_region.Height; ++row)
    {
        int dst_pixel = dst+3;
        for (int col = 0; col < mask_region.Width; ++col)
        {
            m_output[dst_pixel] = mask.Data[src+col];
            dst_pixel += pixel_size;
        }
        dst += Info.Stride;
        src += mask.Info.Stride;
    }
}
```

### GameRes.Formats.Sas5.IarDecompressor

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

int m_bits = 1 ;
```

#### IarDecompressor

```csharp
public IarDecompressor (IBinaryStream input) {
    m_input = input;
}
```

#### Unpack

```csharp
public void Unpack (byte[] output) {
    m_bits = 1;
    int dst = 0;
    while (dst < output.Length)
    {
        if (1 == GetNextBit())
        {
            output[dst++] = m_input.ReadUInt8();
            continue;
        }
        int offset, count;
        if (1 == GetNextBit())
        {
            int tmp = GetNextBit();
            if (1 == GetNextBit())
                offset = 1;
            else if (1 == GetNextBit())
                offset = 0x201;
            else
            {
                tmp = (tmp << 1) | GetNextBit();
                if (1 == GetNextBit())
                    offset = 0x401;
                else
                {
                    tmp = (tmp << 1) | GetNextBit();
                    if (1 == GetNextBit())
                        offset = 0x801;
                    else
                    {
                        offset = 0x1001;
                        tmp = (tmp << 1) | GetNextBit();
                    }
                }
            }
            offset += (tmp << 8) | m_input.ReadUInt8();
            if (1 == GetNextBit())
                count = 3;
            else if (1 == GetNextBit())
                count = 4;
            else if (1 == GetNextBit())
                count = 5;
            else if (1 == GetNextBit())
                count = 6;
            else if (1 == GetNextBit())
                count = 7 + GetNextBit();
            else if (1 == GetNextBit())
                count = 17 + m_input.ReadUInt8();
            else
            {
                count = GetNextBit() << 2;
                count |= GetNextBit() << 1;
                count |= GetNextBit();
                count += 9;
            }
        }
        else
        {
            count = 2;
            if (1 == GetNextBit())
            {
                offset = GetNextBit() << 10;
                offset |= GetNextBit() << 9;
                offset |= GetNextBit() << 8;
                offset = (offset | m_input.ReadUInt8()) + 0x100;
            }
            else
            {
                offset = 1 + m_input.ReadUInt8();
                if (0x100 == offset)
                    break;
            }
        }
        Binary.CopyOverlapped (output, dst - offset, dst, count);
        dst += count;
    }
}
```

#### GetNextBit

```csharp
int GetNextBit () {
    if (1 == m_bits)
    {
        m_bits = m_input.ReadUInt16() | 0x10000;
    }
    int b = m_bits & 1;
    m_bits >>= 1;
    return b;
}
```

## 配套算法与外部条件

- [ArcFormats/Sas5/ArcSec5.cs](ArcSec5.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Sas5/ArcIAR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
