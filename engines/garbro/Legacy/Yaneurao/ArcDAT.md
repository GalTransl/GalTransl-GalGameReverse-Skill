# Yaneurao / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/yanepkEx` / `GameRes.Formats.Yaneurao.PackExOpener` | `dat` | `79616e65` | `False` |
| `DAT/yanepkDx` / `GameRes.Formats.Yaneurao.PackOpener` | `dat` | `0a14090c`, `79616e65` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `if (file.View.AsciiEqual (0, "yane"))` |
| `PackOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "pkDx"))` |
| `PackOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0x10C);` |
| `PackOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x100);` |
| `PackOpener.TryOpen` | `entry.Offset       = file.View.ReadUInt32 (index_offset);` |
| `PackOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);` |
| `PackOpener.TryOpen` | `entry.Size         = file.View.ReadUInt32 (index_offset+8);` |
| `PackExOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "pkEx"))` |
| `PackExOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `PackExOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x20);` |
| `PackExOpener.TryOpen` | `entry.Offset       = file.View.ReadUInt32 (index_offset);` |
| `PackExOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);` |
| `PackExOpener.TryOpen` | `entry.Size         = file.View.ReadUInt32 (index_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Yaneurao.PackOpener

继承/接口：`ArchiveFormat`。

#### PackOpener

```csharp
public PackOpener () {
    Signatures = new uint[] { 0x0C09140A, 0x656E6179 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.AsciiEqual (0, "yane"))
    {
        if (!file.View.AsciiEqual (4, "pkDx"))
            return null;
    }
    uint first_offset = file.View.ReadUInt32 (0x10C);
    if (first_offset < 0x118 || first_offset >= file.MaxOffset)
        return null;
    int count = (int)((first_offset - 0xC) / 0x10C);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x100);
        index_offset += 0x100;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset       = file.View.ReadUInt32 (index_offset);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);
        entry.Size         = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        dir.Add (entry);
        index_offset += 0xC;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new LzssStream (input);
}
```

### GameRes.Formats.Yaneurao.PackExOpener

继承/接口：`PackOpener`。

#### PackExOpener

```csharp
public PackExOpener () {
    Signatures = new uint[] { 0x656E6179 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "pkEx"))
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x20);
        index_offset += 0x20;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset       = file.View.ReadUInt32 (index_offset);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);
        entry.Size         = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        dir.Add (entry);
        index_offset += 0xC;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Yaneurao/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
