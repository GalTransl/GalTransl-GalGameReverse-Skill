# Crowd / ArcPCK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCK` / `GameRes.Formats.Crowd.PckOpener` | `pck` | 无固定签名或来源表达式未解析 | `False` |
| `PKWV` / `GameRes.Formats.Crowd.PkwOpener` | `PCK` | `504b5756` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PckOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `PckOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+4),` |
| `PckOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+8)` |
| `PckOpener.TryOpen` | `byte b = file.View.ReadByte (index_offset+n);` |
| `PkwOpener.TryOpen` | `int format_count = file.View.ReadUInt16 (4);` |
| `PkwOpener.TryOpen` | `int count = file.View.ReadUInt16 (6);` |
| `PkwOpener.TryOpen` | `FormatTag               = file.View.ReadUInt16 (index_offset),` |
| `PkwOpener.TryOpen` | `Channels                = file.View.ReadUInt16 (index_offset+2),` |
| `PkwOpener.TryOpen` | `SamplesPerSecond        = file.View.ReadUInt32 (index_offset+4),` |
| `PkwOpener.TryOpen` | `AverageBytesPerSecond   = file.View.ReadUInt32 (index_offset+8),` |
| `PkwOpener.TryOpen` | `BitsPerSample           = file.View.ReadUInt16 (index_offset+12),` |
| `PkwOpener.TryOpen` | `BlockAlign              = file.View.ReadUInt16 (index_offset+14),` |
| `PkwOpener.TryOpen` | `int fmt_index = file.View.ReadUInt16 (index_offset);` |
| `PkwOpener.TryOpen` | `string name = file.View.ReadString (index_offset+2, 0x0A);` |
| `PkwOpener.TryOpen` | `Offset = base_offset + file.View.ReadInt64 (index_offset+0x10),` |
| `PkwOpener.TryOpen` | `Size = file.View.ReadUInt32 (index_offset+0x0C),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Crowd.PckOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (count <= 0 || count > 0xfffff)
        return null;
    long index_offset = 4;
    uint index_size = (uint)(0xc * count);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry>();
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Offset = file.View.ReadUInt32 (index_offset+4),
            Size   = file.View.ReadUInt32 (index_offset+8)
        };
        if (entry.Offset < index_size || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 12;
    }
    byte[] name_buf = new byte[260];
    foreach (var entry in dir)
    {
        uint max_len = Math.Min (260u, file.View.Reserve (index_offset, 260));
        uint n;
        for (n = 0; n < max_len; ++n)
        {
            byte b = file.View.ReadByte (index_offset+n);
            if (0 == b)
                break;
            name_buf[n] = b;
        }
        if (0 == n || max_len == n)
            return null;
        entry.Name = Encodings.cp932.GetString (name_buf, 0, (int)n);
        entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
        index_offset += n+1;
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Crowd.PkwEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public WaveFormat   Format ;
```

### GameRes.Formats.Crowd.PkwOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const uint WaveHeaderSize = 8 + 12 + 0x10 + 8 ;
```

#### PkwOpener

```csharp
public PkwOpener () {
    Extensions = new string[] { "PCK" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int format_count = file.View.ReadUInt16 (4);
    int count = file.View.ReadUInt16 (6);
    if (0 == format_count || 0 == count)
        return null;
    uint index_offset = 8;
    long base_offset = index_offset + format_count*0x14 + count*0x18;
    if (base_offset >= file.MaxOffset)
        return null;
    var formats = new List<WaveFormat> (format_count);
    for (int i = 0; i < format_count; ++i)
    {
        var format = new WaveFormat
        {
            FormatTag               = file.View.ReadUInt16 (index_offset),
            Channels                = file.View.ReadUInt16 (index_offset+2),
            SamplesPerSecond        = file.View.ReadUInt32 (index_offset+4),
            AverageBytesPerSecond   = file.View.ReadUInt32 (index_offset+8),
            BitsPerSample           = file.View.ReadUInt16 (index_offset+12),
            BlockAlign              = file.View.ReadUInt16 (index_offset+14),
        };
        index_offset += 0x14;
        formats.Add (format);
    }
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int fmt_index = file.View.ReadUInt16 (index_offset);
        if (fmt_index > formats.Count)
            return null;
        string name = file.View.ReadString (index_offset+2, 0x0A);
        var entry = new PkwEntry
        {
            Name = name + ".wav",
            Type = "audio",
            Offset = base_offset + file.View.ReadInt64 (index_offset+0x10),
            Size = file.View.ReadUInt32 (index_offset+0x0C),
            IsPacked = true,
            Format = formats[fmt_index],
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.UnpackedSize = entry.Size + WaveHeaderSize;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var went = entry as PkwEntry;
    if (null == went)
        return input;
    using (var riff = new MemoryStream (0x2C))
    {
        WaveAudio.WriteRiffHeader (riff, went.Format, went.Size);
        return new PrefixStream (riff.ToArray(), input);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Crowd/ArcPCK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
