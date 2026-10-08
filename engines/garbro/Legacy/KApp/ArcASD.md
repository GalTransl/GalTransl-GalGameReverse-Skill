# KApp / ArcASD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ASD/SPIEL` / `GameRes.Formats.KApp.AsdAudioOpener` | `asd` | 无固定签名或来源表达式未解析 | `False` |
| `ASD/KTOOL` / `GameRes.Formats.KApp.AsdKToolOpener` | `asd` | `6b746f6f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AsdKToolOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `AsdKToolOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_pos);` |
| `AsdKToolOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_pos);` |
| `AsdKToolOpener.DetectFileTypes` | `var type = file.View.ReadUInt32 (entry.Offset+0xC);` |
| `AsdKToolOpener.OpenEntry` | `uint id = arc.File.View.ReadUInt32 (entry.Offset+0xC);` |
| `AsdKToolOpener.OpenAudio` | `var header = input.ReadHeader (0x20);` |
| `AsdKToolOpener.OpenAudio` | `int header_size = header.ToUInt16 (10);` |
| `AsdKToolOpener.OpenAudio` | `FormatTag = header.ToUInt16 (0x10),` |
| `AsdKToolOpener.OpenAudio` | `Channels = header.ToUInt16 (0x12),` |
| `AsdKToolOpener.OpenAudio` | `SamplesPerSecond = header.ToUInt32 (0x14),` |
| `AsdKToolOpener.OpenAudio` | `AverageBytesPerSecond = header.ToUInt32 (0x18),` |
| `AsdKToolOpener.OpenAudio` | `BlockAlign = header.ToUInt16 (0x1C),` |
| `AsdKToolOpener.OpenAudio` | `BitsPerSample  = header.ToUInt16 (0x1E),` |
| `AsdKToolOpener.OpenAudio` | `var data = new byte[header.ToInt32 (0)];` |
| `AsdAudioOpener.TryOpen` | `byte format = file.View.ReadByte (0);` |
| `AsdAudioOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_pos);` |
| `AsdAudioOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_pos);` |
| `AsdAudioOpener.OpenEntry` | `uint data_size = view.ReadUInt32 (entry.Offset);` |
| `AsdAudioOpener.OpenEntry` | `FormatTag           = view.ReadUInt16 (entry.Offset+8),` |
| `AsdAudioOpener.OpenEntry` | `Channels            = view.ReadUInt16 (entry.Offset+0xA),` |
| `AsdAudioOpener.OpenEntry` | `SamplesPerSecond    = view.ReadUInt32 (entry.Offset+0xC),` |
| `AsdAudioOpener.OpenEntry` | `AverageBytesPerSecond = view.ReadUInt32 (entry.Offset+0x10),` |
| `AsdAudioOpener.OpenEntry` | `BlockAlign          = view.ReadUInt16 (entry.Offset+0x14),` |
| `AsdAudioOpener.OpenEntry` | `BitsPerSample       = view.ReadUInt16 (entry.Offset+0x16),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KApp.AsdKToolOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_pos = 0x10;
    uint next_offset = file.View.ReadUInt32 (index_pos);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_pos += 4;
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Offset = next_offset,
        };
        next_offset = file.View.ReadUInt32 (index_pos);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (ArcView file, List<Entry> dir) {
    foreach (var entry in dir)
    {
        var type = file.View.ReadUInt32 (entry.Offset+0xC);
        switch (type)
        {
        case 0xB713E4: entry.Type = "audio"; break;
        case 0xB29EA4:
        case 0x973768: entry.Type = "image"; break;
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    uint id = arc.File.View.ReadUInt32 (entry.Offset+0xC);
    if (id != 0xB713E4)
        return base.OpenEntry (arc, entry);
    return OpenAudio (arc, entry);
}
```

#### OpenAudio

```csharp
Stream OpenAudio (ArcFile arc, Entry entry) {
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var header = input.ReadHeader (0x20);
        int header_size = header.ToUInt16 (10);
        var format = new WaveFormat {
            FormatTag = header.ToUInt16 (0x10),
            Channels = header.ToUInt16 (0x12),
            SamplesPerSecond = header.ToUInt32 (0x14),
            AverageBytesPerSecond = header.ToUInt32 (0x18),
            BlockAlign = header.ToUInt16 (0x1C),
            BitsPerSample  = header.ToUInt16 (0x1E),
        };
        input.Position = header_size + 0x10;
        var data = new byte[header.ToInt32 (0)];
        KTool.Unpack (input, data, header[8]);
        var output = new MemoryStream (data.Length);
        WaveAudio.WriteRiffHeader (output, format, (uint)data.Length);
        output.Write (data, 0, data.Length);
        output.Position = 0;
        return output;
    }
}
```

### GameRes.Formats.KApp.AsdArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public byte     Format ;
```

### GameRes.Formats.KApp.AsdAudioOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".asd"))
        return null;
    byte format = file.View.ReadByte (0);
    if (format != 1 && format != 2)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_pos = 0x10;
    uint next_offset = file.View.ReadUInt32 (index_pos);
    var dir = new List<Entry>();
    while (next_offset != 0xFFFFFFFF)
    {
        index_pos += 4;
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D4}", base_name, dir.Count),
            Type = "audio",
            Offset = next_offset,
        };
        next_offset = file.View.ReadUInt32 (index_pos);
        if (next_offset != 0xFFFFFFFF)
            entry.Size = (uint)(next_offset - entry.Offset);
        else
            entry.Size = (uint)(file.MaxOffset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    return new AsdArchive (file, this, dir) { Format = format };
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile a, Entry entry) {
    var arc = (AsdArchive)a;
    var view = arc.File.View;
    uint data_size = view.ReadUInt32 (entry.Offset);
    if (2 == arc.Format)
        return arc.File.CreateStream (entry.Offset+0x10, data_size);

    var format = new WaveFormat {
        FormatTag           = view.ReadUInt16 (entry.Offset+8),
        Channels            = view.ReadUInt16 (entry.Offset+0xA),
        SamplesPerSecond    = view.ReadUInt32 (entry.Offset+0xC),
        AverageBytesPerSecond = view.ReadUInt32 (entry.Offset+0x10),
        BlockAlign          = view.ReadUInt16 (entry.Offset+0x14),
        BitsPerSample       = view.ReadUInt16 (entry.Offset+0x16),
    };
    byte[] header;
    using (var riff = new MemoryStream())
    {
        WaveAudio.WriteRiffHeader (riff, format, data_size);
        header = riff.ToArray();
    }
    var input = arc.File.CreateStream (entry.Offset+0x20, entry.Size-0x20);
    return new PrefixStream (header, input);
}
```

## 配套算法与外部条件

- [Legacy/KApp/ImageCGD.cs](ImageCGD.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/KApp/ArcASD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
