# Sas5 / ArcWAR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WAR2/SAS5` / `GameRes.Formats.Sas5.War2Opener` | `war` | `77617232` | `False` |
| `WAR/SAS5` / `GameRes.Formats.Sas5.WarOpener` | `war` | `77617220` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WarOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `WarOpener.TryOpen` | `uint entry_size = file.View.ReadUInt32 (12);` |
| `WarOpener.TryOpen` | `Offset  = file.View.ReadUInt32 (index_offset),` |
| `WarOpener.TryOpen` | `Size    = file.View.ReadUInt32 (index_offset+4),` |
| `WarOpener.TryOpen` | `Format  = file.View.ReadByte (index_offset+0x14),` |
| `WarOpener.OpenWavEntry` | `uint fmt_size = file.View.ReadUInt32 (offset);` |
| `WarOpener.OpenWavEntry` | `uint data_size = file.View.ReadUInt32 (offset+4);` |
| `War2Opener.TryOpen` | `uint header_size = file.View.ReadUInt32 (4);` |
| `War2Opener.TryOpen` | `int count = file.View.ReadInt32 (12);` |
| `War2Opener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `War2Opener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_offset);` |
| `War2Opener.OpenEntry` | `byte id = arc.File.View.ReadByte (offset++);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sas5.WarEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  Format ;
```

### GameRes.Formats.Sas5.WarOpener

继承/接口：`ArchiveFormat`。

#### WarOpener

```csharp
public WarOpener () {
    Extensions = new string[] { "war" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint entry_size = file.View.ReadUInt32 (12);
    if (entry_size < 0x18)
        return null;
    var GetEntryName = CreateEntryNameDelegate (file.Name);

    uint index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new WarEntry {
            Name    = GetEntryName (i),
            Offset  = file.View.ReadUInt32 (index_offset),
            Size    = file.View.ReadUInt32 (index_offset+4),
            Format  = file.View.ReadByte (index_offset+0x14),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (0 == entry.Format)
        {
            entry.Name = Path.ChangeExtension (entry.Name, "wav");
            entry.Type = "audio";
        }
        else if (2 == entry.Format)
        {
            entry.Name = Path.ChangeExtension (entry.Name, "ogg");
            entry.Type = "audio";
        }
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var went = entry as WarEntry;
    if (null == went || 0 != went.Format)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    return OpenWavEntry (arc.File, entry.Offset, entry.Size);
}
```

#### CreateEntryNameDelegate

```csharp
internal Func<int, string> CreateEntryNameDelegate (string arc_name) {
    var index = Sec5Opener.LookupIndex (arc_name);
    string base_name = Path.GetFileNameWithoutExtension (arc_name);
    if (null == index)
        return n => GetDefaultName (base_name, n);
    else
        return (n) => {
            Entry entry;
            if (index.TryGetValue (n, out entry))
                return entry.Name;
            return GetDefaultName (base_name, n);
        };
}
```

#### GetDefaultName

```csharp
internal static string GetDefaultName (string base_name, int n) {
    return string.Format ("{0}#{1:D5}", base_name, n);
}
```

#### OpenWavEntry

```csharp
internal Stream OpenWavEntry (ArcView file, long offset, uint size) {
    uint fmt_size = file.View.ReadUInt32 (offset);
    uint data_size = file.View.ReadUInt32 (offset+4);
    var wav_header = new byte[8+12+fmt_size+8];
    uint total_size = (uint)wav_header.Length + data_size - 8;
    file.View.Read (offset+8, wav_header, 0x14, fmt_size);
    using (var mem = new MemoryStream (wav_header))
    using (var buffer = new BinaryWriter (mem))
    {
        buffer.Write (AudioFormat.Wav.Signature);
        buffer.Write (total_size);
        buffer.Write (0x45564157);
        buffer.Write (0x20746d66);
        buffer.Write (fmt_size);
        buffer.BaseStream.Seek (fmt_size, SeekOrigin.Current);
        buffer.Write (0x61746164);
        buffer.Write (data_size);
    }
    var pcm_data = file.CreateStream (offset+8+fmt_size, size-8-fmt_size);
    return new PrefixStream (wav_header, pcm_data);
}
```

### GameRes.Formats.Sas5.War2Opener

继承/接口：`WarOpener`。

#### War2Opener

```csharp
public War2Opener () {
    Extensions = new string[] { "war" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint header_size = file.View.ReadUInt32 (4);
    if (header_size >= file.MaxOffset)
        return null;
    int count = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;
    var GetEntryName = CreateEntryNameDelegate (file.Name);

    uint index_offset = header_size+8;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new Entry {
            Name    = GetEntryName (i),
            Offset  = next_offset,
            Type    = "audio",
        };
        next_offset = file.View.ReadUInt32 (index_offset);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var offset = entry.Offset;
    var end_offset = entry.Offset + entry.Size;
    byte id = arc.File.View.ReadByte (offset++);
    if (0 != (id & 0x40))
        offset += 12;
    if (offset >= end_offset)
        return Stream.Null;
    uint size = (uint)(end_offset - offset);
    int format = id & 0xF;
    if (0 == format)
        return OpenWavEntry (arc.File, offset, size);
    return arc.File.CreateStream (offset, size);
}
```

## 配套算法与外部条件

- [ArcFormats/Sas5/ArcSec5.cs](ArcSec5.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Sas5/ArcWAR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
