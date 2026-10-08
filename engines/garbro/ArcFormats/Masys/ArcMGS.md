# Masys / ArcMGS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MGS` / `GameRes.Formats.Megu.MgsOpener` | `mgs` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MgsOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "MGS"))` |
| `MgsOpener.TryOpen` | `int count = file.View.ReadInt16 (0x20);` |
| `MgsOpener.TryOpen` | `int flag = file.View.ReadUInt16 (3);` |
| `MgsOpener.TryOpen` | `byte format = file.View.ReadByte (index_offset);` |
| `MgsOpener.TryOpen` | `int name_size = file.View.ReadByte (index_offset+9);` |
| `MgsOpener.TryOpen` | `entry.Channels = file.View.ReadUInt16 (index_offset+1);` |
| `MgsOpener.TryOpen` | `entry.SamplesPerSecond = file.View.ReadUInt32 (index_offset+3);` |
| `MgsOpener.TryOpen` | `entry.BitsPerSample = file.View.ReadUInt16 (index_offset+7);` |
| `MgsOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset);` |
| `MgsOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset + 4);` |
| `PcmDecoder.Decode` | `short sample = input.ReadInt16();` |
| `PcmDecoder.Decode` | `int quant_idx = input.ReadUInt16() & 0xFF;` |
| `PcmDecoder.Decode` | `byte octet = input.ReadUInt8();` |
| `PcmDecoder.Decode` | `sample = input.ReadInt16();` |
| `PcmDecoder.Decode` | `quant_idx = input.ReadUInt16() & 0xFF;` |
| `PcmDecoder.Decode` | `uint first_code = input.ReadUInt32();` |
| `PcmDecoder.Decode` | `uint second_code = input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Megu.MgsEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public ushort  Channels ;

public uint    SamplesPerSecond ;

public ushort  BitsPerSample ;

public byte    Format ;
```

### GameRes.Formats.Megu.MgsOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "MGS"))
        return null;
    int count = file.View.ReadInt16 (0x20);
    if (!IsSaneCount (count))
        return null;
    int flag = file.View.ReadUInt16 (3);
    var dir = new List<Entry> (count);
    int index_offset = 0x22;
    byte[] name_buf = new byte[16];
    for (int i = 0; i < count; ++i)
    {
        byte format = file.View.ReadByte (index_offset);
        int name_size = file.View.ReadByte (index_offset+9);
        if (0 == name_size)
            return null;
        if (name_size > name_buf.Length)
            Array.Resize (ref name_buf, name_size);
        file.View.Read (index_offset+10, name_buf, 0, (uint)name_size);
        if (100 == flag)
            MgdOpener.Decrypt (name_buf, 0, name_size);
        var name = Encodings.cp932.GetString (name_buf, 0, name_size);
        name = Path.ChangeExtension (name, GetExtFromFormatId (format));

        var entry = FormatCatalog.Instance.Create<MgsEntry> (name);
        entry.Format = format;
        if (0 == format)
        {
            entry.Channels = file.View.ReadUInt16 (index_offset+1);
            entry.SamplesPerSecond = file.View.ReadUInt32 (index_offset+3);
            entry.BitsPerSample = file.View.ReadUInt16 (index_offset+7);
        }
        index_offset += 10 + name_size;
        entry.Size = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset + 4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var went = entry as MgsEntry;
    if (null == went || went.Format != 0)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var format = new WaveFormat {
        FormatTag = 1,
        Channels = (ushort)(went.Channels & 0x7FFF),
        SamplesPerSecond = went.SamplesPerSecond,
    };
    Stream pcm;
    uint pcm_size;
    if (0 != (went.Channels & 0x8000))
    {
        format.BitsPerSample = 0x10;
        var decoder = new PcmDecoder (went);
        using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
        {
            var data = decoder.Decode (input);
            pcm = new MemoryStream (data);
            pcm_size = (uint)data.Length;
        }
    }
    else
    {
        format.BitsPerSample = went.BitsPerSample;
        pcm = arc.File.CreateStream (entry.Offset, entry.Size);
        pcm_size = entry.Size;
    }
    using (var riff = new MemoryStream (0x2C))
    {
        ushort align = (ushort)(format.Channels * format.BitsPerSample / 8);
        format.AverageBytesPerSecond = went.SamplesPerSecond * align;
        format.BlockAlign = align;
        WaveAudio.WriteRiffHeader (riff, format, pcm_size);
        return new PrefixStream (riff.ToArray(), pcm);
    }
}
```

#### GetExtFromFormatId

```csharp
internal static string GetExtFromFormatId (int id) {
    switch (id)
    {
    case 0: return "wav";
    case 1: return "mid";
    default: return null;
    }
}
```

### GameRes.Formats.Megu.PcmDecoder

#### 状态与常量

```csharp
int     Channels ;

int     BytesPerChunk ;

byte[]  m_output ;

int     m_dst ;
```

#### PcmDecoder

```csharp
public PcmDecoder (MgsEntry went) {
    Channels = went.Channels & 0x7FFF;
    BytesPerChunk = went.BitsPerSample;
    int output_size;
    if (1 == Channels)
        output_size = (int)went.Size / BytesPerChunk * ((BytesPerChunk - 4) * 4 + 2);
    else
        output_size = (int)went.Size / BytesPerChunk * ((BytesPerChunk - 8) * 4 + 4);
    m_output = new byte[output_size];
}
```

#### PutSample

```csharp
void PutSample (short sample) {
    LittleEndian.Pack (sample, m_output, m_dst);
    m_dst += 2;
}
```

#### Decode

```csharp
public byte[] Decode (IBinaryStream input) {
    m_dst = 0;
    if (1 == Channels)
    {
        var adp = new AdpDecoder();
        while (input.PeekByte() != -1)
        {
            short sample = input.ReadInt16();
            PutSample (sample);
            int quant_idx = input.ReadUInt16() & 0xFF;
            adp.Reset (sample, quant_idx);

            for (int j = 0; j < BytesPerChunk - 4; ++j)
            {
                byte octet = input.ReadUInt8();
                PutSample (adp.DecodeSample (octet));
                PutSample (adp.DecodeSample (octet >> 4));
            }
        }

    }
    else
    {
        var first = new AdpDecoder();
        var second = new AdpDecoder();
        int samples_per_chunk = (BytesPerChunk - 8) / 8;
        while (input.PeekByte() != -1)
        {
            short sample = input.ReadInt16();
            PutSample (sample);
            int quant_idx = input.ReadUInt16() & 0xFF;
            first.Reset (sample, quant_idx);

            sample = input.ReadInt16();
            PutSample (sample);
            quant_idx = input.ReadUInt16() & 0xFF;
            second.Reset (sample, quant_idx);

            for (int j = 0; j < samples_per_chunk; ++j)
            {
                uint first_code = input.ReadUInt32();
                uint second_code = input.ReadUInt32();
                for (int i = 0; i < 8; ++i)
                {
                    PutSample (first.DecodeSample ((byte)first_code));
                    PutSample (second.DecodeSample ((byte)second_code));
                    first_code >>= 4;
                    second_code >>= 4;
                }
            }
        }
    }
    return m_output;
}
```

## 配套算法与外部条件

- [ArcFormats/Abogado/AudioADP.cs](../Abogado/AudioADP.md)：本页引用的随包算法资料。
- [ArcFormats/Masys/ArcMGD.cs](ArcMGD.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Masys/ArcMGS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
