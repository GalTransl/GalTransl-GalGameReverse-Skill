# Xuse / ArcXuse：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/Xuse` / `GameRes.Formats.Xuse.ArcOpener` | `arc`, `xarc` | `4d494b4f`, `58415243` | `False` |
| `KOTORI/Xuse` / `GameRes.Formats.Xuse.KotoriOpener` | `bin` | `4b4f544f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `if (0x1001 != file.View.ReadInt16 (0xA))` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `ArcOpener.TryOpen` | `int mode = file.View.ReadInt32 (0xC);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (0x16, "DFNM"))` |
| `ArcOpener.TryOpen` | `cadr_offset = file.View.ReadInt64 (0x1A);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (ndix_offset, "NDIX"))` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (filenames_offset, "CTIF"))` |
| `ArcOpener.TryOpen` | `\|\| !cadr_view.AsciiEqual (cadr_offset, "CADR"))` |
| `ArcOpener.TryOpen` | `uint entry_offset = file.View.ReadUInt32 (ndix_offset);` |
| `ArcOpener.TryOpen` | `if (0x1001 != file.View.ReadUInt16 (entry_offset))` |
| `ArcOpener.TryOpen` | `var name_length = file.View.ReadUInt16 (entry_offset+6);` |
| `ArcOpener.TryOpen` | `entry.Offset = cadr_view.ReadInt64 (cadr_offset);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (entry.Offset, "DATA"))` |
| `ArcOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (entry.Offset+0x18);` |
| `KotoriOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "KOTORI") \|\| 0x1A1A00 != file.View.ReadInt32 (6))` |
| `KotoriOpener.TryOpen` | `int count = file.View.ReadUInt16 (0x14);` |
| `KotoriOpener.TryOpen` | `if (0x0100A618 != file.View.ReadInt32 (0x10) \|\| !IsSaneCount (count))` |
| `KotoriOpener.TryOpen` | `long next_offset = file.View.ReadUInt32 (current_offset);` |
| `KotoriOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (current_offset);` |
| `KotoriOpener.OpenEntry` | `if (entry.Size < 0x32 \|\| !arc.File.View.AsciiEqual (entry.Offset, "KOTORi")` |
| `KotoriOpener.OpenEntry` | `\|\| 0x001A1A00 != arc.File.View.ReadInt32 (entry.Offset+6)` |
| `KotoriOpener.OpenEntry` | `\|\| 0x0100A618 != arc.File.View.ReadInt32 (entry.Offset+0x10))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Xuse.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Signatures = new uint[] { 0x4F4B494D, 0x43524158 };
    Extensions = new string[] { "arc", "xarc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0x1001 != file.View.ReadInt16 (0xA))
        return null;
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;
    int mode = file.View.ReadInt32 (0xC);
    long cadr_offset;
    if (0 == (mode & 0xF))
    {
        if (!file.View.AsciiEqual (0x16, "DFNM"))
            return null;
        cadr_offset = file.View.ReadInt64 (0x1A);
    }
    else
        throw new NotSupportedException ("Not supported Xuse archive version");

    int ndix_offset = 0x24;
    if (!file.View.AsciiEqual (ndix_offset, "NDIX"))
        return null;
    if (cadr_offset > file.View.Reserve (0, (uint)cadr_offset))
        return null;
    int index_length = 8 * count;
    int filenames_offset = ndix_offset + 8 + 2 * index_length;
    if (!file.View.AsciiEqual (filenames_offset, "CTIF"))
        return null;

    var dir = new List<Entry> (count);
    using (var cadr_view = file.CreateFrame())
    {
        uint cadr_size = 4 + 12 * (uint)count;
        if (cadr_size > cadr_view.Reserve (cadr_offset, cadr_size)
            || !cadr_view.AsciiEqual (cadr_offset, "CADR"))
            return null;
        ndix_offset += 6;
        cadr_offset += 6;
        var name_buf = new byte[0x40];
        for (int i = 0; i < count; ++i)
        {
            uint entry_offset = file.View.ReadUInt32 (ndix_offset);
            if (0x1001 != file.View.ReadUInt16 (entry_offset))
                return null;
            var name_length = file.View.ReadUInt16 (entry_offset+6);
            if (name_length > name_buf.Length)
                name_buf = new byte[name_length];
            file.View.Read (entry_offset+0xA, name_buf, 0, name_length);
            for (int n = 0; n < name_length; ++n)
                name_buf[n] ^= 0x56;

            var name = Encodings.cp932.GetString (name_buf, 0, name_length);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = cadr_view.ReadInt64 (cadr_offset);
            if (entry.Offset >= file.MaxOffset)
                return null;
            dir.Add (entry);

            ndix_offset += 8;
            cadr_offset += 12;
        }
    }
    foreach (var entry in dir)
    {
        if (!file.View.AsciiEqual (entry.Offset, "DATA"))
            return null;
        entry.Size = file.View.ReadUInt32 (entry.Offset+0x18);
        entry.Offset += 0x1E;
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Xuse.KotoriOpener

继承/接口：`ArchiveFormat`。

#### KotoriOpener

```csharp
public KotoriOpener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "KOTORI") || 0x1A1A00 != file.View.ReadInt32 (6))
        return null;
    int count = file.View.ReadUInt16 (0x14);
    if (0x0100A618 != file.View.ReadInt32 (0x10) || !IsSaneCount (count))
        return null;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint current_offset = 0x18;
    long next_offset = file.View.ReadUInt32 (current_offset);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new PackedEntry {
            Name = string.Format ("{0}#{1:D4}.ogg", base_name, i),
            Type = "audio",
            Offset = next_offset,
        };
        if (i+1 != count)
        {
            current_offset += 6;
            next_offset = file.View.ReadUInt32 (current_offset);
        }
        else
            next_offset = file.MaxOffset;
        entry.Size = (uint)(next_offset - entry.Offset);
        if (entry.Size >= 0x32)
        {
            entry.IsPacked = true;
            entry.UnpackedSize = entry.Size - 0x32;
        }
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
    if (entry.Size < 0x32 || !arc.File.View.AsciiEqual (entry.Offset, "KOTORi")
        || 0x001A1A00 != arc.File.View.ReadInt32 (entry.Offset+6)
        || 0x0100A618 != arc.File.View.ReadInt32 (entry.Offset+0x10))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var key = new byte[0x10];
    arc.File.View.Read (entry.Offset+0x20, key, 0, 0x10);
    uint length = entry.Size - 0x32;
    var data = new byte[length];
    length = (uint)arc.File.View.Read (entry.Offset+0x32, data, 0, length);
    for (uint i = 0; i < length; ++i)
    {
        data[i] ^= key[i&0xF];
    }
    return new BinMemoryStream (data, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Xuse/ArcXuse.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
