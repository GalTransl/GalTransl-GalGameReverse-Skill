# SystemAqua / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/CATF` / `GameRes.Formats.SystemAqua.DatOpener` | `dat`, `cat` | `43415446` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `DatOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `DatOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset),` |
| `DatOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+4),` |
| `DatOpener.DetectFileTypes` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `DatOpener.DetectFileTypes` | `entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+8);` |
| `DatOpener.DetectFileTypes` | `if (type.AsciiEqual ("000"))` |
| `DatOpener.DetectFileTypes` | `if (type.AsciiEqual ("BMP"))` |
| `DatOpener.DetectFileTypes` | `else if (type.AsciiEqual ("WAV"))` |
| `DatOpener.DetectFileTypes` | `else if (type.AsciiEqual ("MID"))` |
| `DatOpener.OpenEntry` | `var type = arc.File.View.ReadBytes (entry.Offset+0xC, 3);` |
| `DatOpener.OpenEntry` | `if (type.AsciiEqual ("BMP"))` |
| `DatOpener.PrepareBmpHeader` | `input.ReadInt32();` |
| `DatOpener.PrepareBmpHeader` | `uint h1 = ~input.ReadUInt32();` |
| `DatOpener.PrepareBmpHeader` | `uint h2 = ~input.ReadUInt32();` |
| `DatOpener.PrepareBmpHeader` | `uint h3 = ~input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SystemAqua.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat", "cat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (8);
    if (index_offset >= file.MaxOffset)
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new PackedEntry {
            Name   = string.Format ("{0}#{1:D4}", base_name, i),
            Size   = file.View.ReadUInt32 (index_offset),
            Offset = file.View.ReadUInt32 (index_offset+4),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    DetectFileTypes (dir, file);
    return new ArcFile (file, this, dir);
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (List<Entry> dir, ArcView file) {
    var type = new byte[3];
    foreach (PackedEntry entry in dir)
    {
        uint signature = file.View.ReadUInt32 (entry.Offset);
        if (signature != 0x34655A4C)
        {
            entry.ChangeType (AutoEntry.DetectFileType (signature));
        }
        else if (entry.Size > 0x40)
        {
            entry.IsPacked = true;
            entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+8);
            file.View.Read (entry.Offset+0xC, type, 0, 3);
            if (type.AsciiEqual ("000"))
            {
                entry.Type = "audio";
            }
            else
            {
                DecryptType (type);
                if (type.AsciiEqual ("BMP"))
                    entry.ChangeType (ImageFormat.Bmp);
                else if (type.AsciiEqual ("WAV"))
                    entry.ChangeType (AudioFormat.Wav);
                else if (type.AsciiEqual ("MID"))
                    entry.Name = Path.ChangeExtension (entry.Name, "mid");
            }
        }
    }
}
```

#### DecryptType

```csharp
void DecryptType (byte[] type) {
    type[0] = Binary.RotByteL ((byte)~type[0], 4);
    type[1] = Binary.RotByteL ((byte)~type[1], 4);
    type[2] = Binary.RotByteL ((byte)~type[2], 4);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var type = arc.File.View.ReadBytes (entry.Offset+0xC, 3);
    DecryptType (type);
    using (var input = arc.File.CreateStream (entry.Offset+0x40, entry.Size-0x40))
    {
        var data = new byte[pent.UnpackedSize];
        int output_pos = 0;
        if (type.AsciiEqual ("BMP"))
            output_pos = PrepareBmpHeader (input, data);
        LzUnpack (input, data, output_pos);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### LzUnpack

```csharp
void LzUnpack (Stream input, byte[] output, int dst) {
    var frame = new byte[0x4000];
    int frame_pos = 1;
    using (var bits = new MsbBitStream (input, true))
    {
        while (dst < output.Length)
        {
            int ctl = bits.GetNextBit();
            if (-1 == ctl)
                break;
            if (ctl != 0)
            {
                int v = bits.GetBits (8);
                output[dst++] = frame[frame_pos++ & 0x3FFF] = (byte)v;
            }
            else
            {
                int offset = bits.GetBits (14);
                int count = bits.GetBits (4) + 3;
                while (count --> 0)
                {
                    byte v = frame[offset++ & 0x3FFF];
                    output[dst++] = frame[frame_pos++ & 0x3FFF] = v;
                }
            }
        }
    }
}
```

#### PrepareBmpHeader

```csharp
int PrepareBmpHeader (IBinaryStream input, byte[] output) {
    input.ReadInt32();
    uint h1 = ~input.ReadUInt32();
    uint h2 = ~input.ReadUInt32();
    uint h3 = ~input.ReadUInt32();
    uint width = Binary.BigEndian ((ushort)h1);
    uint height = Binary.BigEndian ((ushort)(h1 >> 16));
    output[0] = (byte)'B';
    output[1] = (byte)'M';
    LittleEndian.Pack (output.Length, output, 2);
    output[10] = 54;
    output[14] = 40;
    LittleEndian.Pack (width,  output, 18);
    LittleEndian.Pack (height, output, 22);
    output[26] = 1;
    output[28] = Binary.RotByteL ((byte)h2, 4);
    LittleEndian.Pack (Binary.RotL (h3, 16), output, 34);
    LittleEndian.Pack (0xB12, output, 38);
    LittleEndian.Pack (0xB12, output, 42);
    LittleEndian.Pack ((uint)Binary.RotByteL ((byte)(h2 >> 16), 4), output, 46);
    LittleEndian.Pack ((uint)Binary.RotByteL ((byte)(h2 >> 24), 4), output, 50);
    return 54;
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../../ArcFormats/BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/SystemAqua/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
