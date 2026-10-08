# Youkai / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/SAKURA` / `GameRes.Formats.Youkai.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `DAT/YOUKAI/1` / `GameRes.Formats.Youkai.GrpDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `DAT/YOUKAI/2` / `GameRes.Formats.Youkai.SoundDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `DAT/YOUKAI/3` / `GameRes.Formats.Youkai.VoiceDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GrpDatOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `GrpDatOpener.TryOpen` | `if (!IsSaneCount (count) \|\| 0 != file.View.ReadInt32 (4))` |
| `GrpDatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x100);` |
| `GrpDatOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset);` |
| `GrpDatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `GrpDatOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "ACMPRS03") &&` |
| `GrpDatOpener.OpenEntry` | `!arc.File.View.AsciiEqual (entry.Offset, "PRS06X"))` |
| `GrpDatOpener.OpenEntry` | `entry.Size = arc.File.View.ReadUInt32 (entry.Offset+0x14);` |
| `GrpDatOpener.OpenEntry` | `if ((arc.File.View.ReadUInt32 (entry.Offset+0x18) & 1) == 0)` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `DatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x100);` |
| `DatOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x100);` |
| `DatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x104);` |
| `SoundDatOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `SoundDatOpener.TryOpen` | `var name = file.View.ReadString (current_offset, 0x100);` |
| `SoundDatOpener.TryOpen` | `uint size = file.View.ReadUInt32 (current_offset+0x100);` |
| `VoiceDatOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (0);` |
| `VoiceDatOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `VoiceDatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x100);` |
| `VoiceDatOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset);` |
| `VoiceDatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Youkai.GrpDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count) || 0 != file.View.ReadInt32 (4))
        return null;
    uint index_offset = 0x20;
    uint data_offset = index_offset + (uint)count * 0x110;
    if (data_offset >= file.MaxOffset)
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x100);
        if (0 == name.Length)
            return null;
        index_offset += 0x100;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        if (entry.Offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x10;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!arc.File.View.AsciiEqual (entry.Offset, "ACMPRS03") &&
        !arc.File.View.AsciiEqual (entry.Offset, "PRS06X"))
        return base.OpenEntry (arc, entry);
    entry.Size = arc.File.View.ReadUInt32 (entry.Offset+0x14);
    var input = arc.File.CreateStream (entry.Offset+0x24, entry.Size);
    if ((arc.File.View.ReadUInt32 (entry.Offset+0x18) & 1) == 0)
        return new LzssStream (input);
    return input;
}
```

### GameRes.Formats.Youkai.DatOpener

继承/接口：`GrpDatOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x20;
    long data_offset  = index_offset + count * 0x110;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x100);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = new PackedEntry();
        entry.IsPacked = name.HasExtension (".pr3");
        if (entry.IsPacked)
            name = name.Substring (0, name.Length-4);
        entry.Name   = name;
        entry.Type   = FormatCatalog.Instance.GetTypeFromName (name);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x100);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x104);
        entry.UnpackedSize = entry.Size;
        if (entry.Offset < data_offset || entry.Offset > file.MaxOffset)
            return null;
        dir.Add (entry);
        index_offset += 0x110;
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Youkai.SoundDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint current_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (current_offset >= file.MaxOffset-0x104)
            return null;
        var name = file.View.ReadString (current_offset, 0x100);
        if (0 == name.Length)
            return null;
        uint size = file.View.ReadUInt32 (current_offset+0x100);
        current_offset += 0x104;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = current_offset;
        entry.Size = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        current_offset += size;
    }
    if (current_offset != file.MaxOffset)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Youkai.VoiceDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    uint data_offset = file.View.ReadUInt32 (0);
    int count = file.View.ReadInt32 (4);
    uint index_offset = 8;
    uint index_size = (uint)count * 0x108;
    if (!IsSaneCount (count) || index_offset + index_size > data_offset)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x100);
        if (0 == name.Length)
            return null;
        index_offset += 0x100;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Youkai/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
