# Peach / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/RQF` / `GameRes.Formats.Peach.RqfOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `RqfOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "Rqf"))` |
| `RqfOpener.TryOpen` | `int count = file.View.ReadUInt16 (4);` |
| `RqfOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `RqfOpener.OpenEntry` | `pcm_size = input.ReadUInt32();` |
| `RqfOpener.OpenEntry` | `input.ReadUInt32();` |
| `RqfBitmapDecoder.RqfBitmapDecoder` | `Width  = m_input.ReadUInt16(),` |
| `RqfBitmapDecoder.RqfBitmapDecoder` | `Height = m_input.ReadUInt16(),` |
| `RqfBitmapDecoder.UnpackRle` | `int v = ReadByte (input);` |
| `RqfBitmapDecoder.UnpackRle` | `v = ReadByte (input);` |
| `RqfBitmapDecoder.UnpackRle` | `output[dst++] = ReadByte (input);` |
| `RqfBitmapDecoder.UnpackRle` | `a[i] = ReadByte (input);` |
| `RqfBitmapDecoder.UnpackRle` | `byte b = ReadByte (input);` |
| `RqfBitmapDecoder.ReadByte` | `static byte ReadByte (IBinaryStream input) {` |
| `RqfBitmapDecoder.ReadByte` | `int b = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Peach.RqfOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "Rqf"))
        return null;

    int count = file.View.ReadUInt16 (4);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var parent_dir = new DirectoryInfo (VFS.Top.CurrentDirectory).Name.ToLowerInvariant();
    uint index_offset = 6;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Offset = file.View.ReadUInt32 (index_offset),
        };
        dir.Add (entry);
        index_offset += 4;
    }
    for (int i = 0; i < count; ++i)
    {
        long next_offset = (i == count - 1) ? file.MaxOffset : dir[i + 1].Offset;
        dir[i].Size = (uint)(next_offset - dir[i].Offset);
        if (!dir[i].CheckPlacement (file.MaxOffset))
            return null;
        if (parent_dir == "cg")
            dir[i].Type = "image";
        else if (parent_dir == "snd")
            dir[i].Type = "audio";
    }

    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Type != "audio")
        return base.OpenEntry (arc, entry);

    byte[] output;
    uint pcm_size;
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        pcm_size = input.ReadUInt32();
        input.ReadUInt32();
        output = new byte[pcm_size + 0x2C];
        RqfBitmapDecoder.UnpackRle (input, output, 2, 0x2C);
    }

    var format = new WaveFormat {
        FormatTag = 1,
        Channels = 1,
        SamplesPerSecond = 22050,
        BlockAlign = 2,
        BitsPerSample = 16,
    };
    format.SetBPS();
    using (var mem = new MemoryStream())
    {
        WaveAudio.WriteRiffHeader (mem, format, pcm_size);
        mem.Position = 0;
        mem.Read (output, 0, 0x2C);
    }

    return new BinMemoryStream (output);
}
```

### GameRes.Formats.Peach.RqfBitmapDecoder

继承/接口：`BinaryImageDecoder`。

#### RqfBitmapDecoder

```csharp
public RqfBitmapDecoder (IBinaryStream input) : base (input) {
    Info = new ImageMetaData {
        Width  = m_input.ReadUInt16(),
        Height = m_input.ReadUInt16(),
    };
}
```

#### UnpackRle

```csharp
internal static void UnpackRle (IBinaryStream input, byte[] output, int bytes_pp, int dst = 0) {
    while (dst < output.Length)
    {
        int v = ReadByte (input);
        if (v == 0)
        {
            v = ReadByte (input);
            for (int i = 0; i <= v; i++)
            {
                for (int j = 0; j < bytes_pp; j++)
                    output[dst++] = ReadByte (input);
            }
        }
        else if (bytes_pp != 2)
        {
            var a = new byte[bytes_pp];
            for (int i = 0; i < bytes_pp; i++)
            {
                a[i] = ReadByte (input);
            }
            for (int i = 0; i <= v; i++)
            {
                for (int j = 0; j < bytes_pp; j++)
                    output[dst++] = a[j];
            }
        }
        else
        {
            byte b = ReadByte (input);
            for (int i = 0; i < v; i++)
            {
                output[dst++] = ReadByte (input);
                output[dst++] = b;
            }
        }
    }
}
```

#### ReadByte

```csharp
static byte ReadByte (IBinaryStream input) {
    int b = input.ReadByte();
    if (b == -1)
        throw new EndOfStreamException();
    return (byte)b;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Peach/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
