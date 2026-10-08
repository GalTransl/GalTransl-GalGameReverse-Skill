# Aoi / ArcBOX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AOIMY` / `GameRes.Formats.Aoi.AoiMyOpener` | `box` | `414f494d` | `False` |
| `AOIMY/UNICODE` / `GameRes.Formats.Aoi.AoiMyUnicodeOpener` | `box` | `41004f00` | `False` |
| `BOX` / `GameRes.Formats.Aoi.BoxOpener` | `box` | `414f4942` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BoxOpener.TryOpen` | `if (file.View.AsciiEqual (4, "X10"))` |
| `BoxOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "X12"))` |
| `BoxOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "OX7\0"))` |
| `BoxOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "OX6\0"))` |
| `BoxOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "OX5 "))` |
| `BoxOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "OX4 "))` |
| `BoxOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `BoxOpener.ReadIndexV6` | `Name = file.View.ReadString (index_offset, 0x10),` |
| `BoxOpener.ReadIndexV6` | `Offset = file.View.ReadUInt32 (index_offset+0x10),` |
| `BoxOpener.ReadIndexV6` | `Size = file.View.ReadUInt32 (index_offset+0x14),` |
| `BoxOpener.ReadIndexV5` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `BoxOpener.ReadIndexV5` | `next_offset = i+1 == count ? (uint)file.MaxOffset : file.View.ReadUInt32 (index_offset);` |
| `AoiMyOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "Y01\0"))` |
| `AoiMyOpener.TryOpen` | `int count = Binary.BigEndian (file.View.ReadInt32 (8));` |
| `AoiMyOpener.TryOpen` | `Name = file.View.ReadString (index_offset, 0x10),` |
| `AoiMyOpener.TryOpen` | `Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x10)),` |
| `AoiMyOpener.TryOpen` | `Size = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x14)),` |
| `AoiMyOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `AoiMyUnicodeOpener.TryOpen` | `int count = Binary.BigEndian (file.View.ReadInt32 (0x10));` |
| `AoiMyUnicodeOpener.TryOpen` | `Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x20)),` |
| `AoiMyUnicodeOpener.TryOpen` | `Size = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x24)),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aoi.BoxArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte Key ;
```

#### BoxArchive

```csharp
public BoxArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Aoi.BoxOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<int, byte> VersionKeyMap = new Dictionary<int, byte> {
    {  4, 0xAD },
    {  5, 0xAD },
    {  6, 0xB4 },
    {  7, 0xB4 },
    { 10, 0xB2 },
    { 12, 0xA5 },
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version;
    if (file.View.AsciiEqual (4, "X10"))
        version = 10;
    else if (file.View.AsciiEqual (4, "X12"))
        version = 12;
    else if (file.View.AsciiEqual (4, "OX7\0"))
        version = 7;
    else if (file.View.AsciiEqual (4, "OX6\0"))
        version = 6;
    else if (file.View.AsciiEqual (4, "OX5 "))
        version = 5;
    else if (file.View.AsciiEqual (4, "OX4 "))
        version = 4;
    else
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    List<Entry> dir;
    if (version > 5)
        dir = ReadIndexV6 (file, count);
    else
        dir = ReadIndexV5 (file, count);
    if (null == dir)
        return null;
    return new BoxArchive (file, this, dir, VersionKeyMap[version]);
}
```

#### ReadIndexV6

```csharp
List<Entry> ReadIndexV6 (ArcView file, int count) {
    int index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = file.View.ReadString (index_offset, 0x10),
            Type = "script",
            Offset = file.View.ReadUInt32 (index_offset+0x10),
            Size = file.View.ReadUInt32 (index_offset+0x14),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return dir;
}
```

#### ReadIndexV5

```csharp
List<Entry> ReadIndexV5 (ArcView file, int count) {
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    int index_offset = 0xC;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D2}.evt", base_name, i),
            Type = "script",
            Offset = next_offset,
        };
        next_offset = i+1 == count ? (uint)file.MaxOffset : file.View.ReadUInt32 (index_offset);
        entry.Size = next_offset - (uint)entry.Offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var barc = arc as BoxArchive;
    if (null == barc)
        return input;
    return new XoredStream (input, barc.Key);
}
```

### GameRes.Formats.Aoi.AoiMyOpener

继承/接口：`ArchiveFormat`。

#### AoiMyOpener

```csharp
public AoiMyOpener () {
    Extensions = new string[] { "box" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "Y01\0"))
        return null;
    int count = Binary.BigEndian (file.View.ReadInt32 (8));
    if (!IsSaneCount (count))
        return null;
    int index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = file.View.ReadString (index_offset, 0x10),
            Type = "script",
            Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x10)),
            Size = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x14)),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    uint offset = (uint)entry.Offset;
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] ^= KeyFromOffset (offset++);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### KeyFromOffset

```csharp
static byte KeyFromOffset (uint offset) {
    uint v1 = offset - 0x5CC8E9D7u + (0xA3371629u >> (int)((offset & 0xF) + 1)) - (0x5CC8E9D7u << (int)(31 - (offset & 0xF)));

    uint v3 = v1 << (int)(31 - ((offset >> 4) & 0xF));
    uint v4 = v1 >> (int)(((offset >> 4) & 0xF) + 1);
    uint v5 = offset - 0x5CC8E9D7
        + ((offset - 0x5CC8E9D7u + v3 + v4) << (int)(31 - ((offset >> 8) & 0xF)))
        + ((offset - 0x5CC8E9D7u + v3 + v4) >> (int)(((offset >> 8) & 0xF) + 1));
    uint v6 = offset - 0x5CC8E9D7u
        + (v5 << (int)(31 - ((offset >> 12) & 0xF))) + (v5 >> (int)(((offset >> 12) & 0xF) + 1));
    uint v7 = offset - 0x5CC8E9D7u
        + (v6 << (int)(31 - ((offset >> 16) & 0xF))) + (v6 >> (int)(((offset >> 16) & 0xF) + 1));
    int v8 = (int)(offset >> 20) & 0xF;
    uint v9 = offset - 0x5CC8E9D7u
        + ((offset - 0x5CC8E9D7u + (v7 << (31 - v8)) + (v7 >> (v8 + 1))) << (int)(31 - ((offset >> 24) & 0xF)))
        + ((offset - 0x5CC8E9D7u + (v7 << (31 - v8)) + (v7 >> (v8 + 1))) >> (int)(((offset >> 24) & 0xF) + 1));
    uint key = (offset - 0x5CC8E9D7 + (v9 << (int)(31 - (offset >> 28))) + (v9 >> (int)((offset >> 28) + 1))) >> (int)(offset & 0xF);
    return (byte)key;
}
```

### GameRes.Formats.Aoi.AoiMyUnicodeOpener

继承/接口：`AoiMyOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var name_buffer = new byte[0x20];
    file.View.Read (0, name_buffer, 0, 0x16);
    if ("AOIMY01\0" != Encoding.Unicode.GetString (name_buffer, 0, 0x10))
        return null;
    int count = Binary.BigEndian (file.View.ReadInt32 (0x10));
    if (!IsSaneCount (count))
        return null;
    int index_offset = 0x18;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (0x20 != file.View.Read (index_offset, name_buffer, 0, 0x20))
            return null;
        int n;
        for (n = 0; n < name_buffer.Length; n += 2)
            if (0 == name_buffer[n] && 0 == name_buffer[n+1])
                break;
        if (0 == n)
            return null;
        var entry = new Entry {
            Name = Encoding.Unicode.GetString (name_buffer, 0, n),
            Type = "script",
            Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x20)),
            Size = Binary.BigEndian (file.View.ReadUInt32 (index_offset+0x24)),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x28;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Aoi/ArcBOX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
