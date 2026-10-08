# Otemoto / ArcTLZ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `TLZ` / `GameRes.Formats.Otemoto.TlzOpener` | `tlz` | `544c5a31` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `TlzOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `TlzOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (4);` |
| `TlzOpener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset),` |
| `TlzOpener.TryOpen` | `Size         = file.View.ReadUInt32 (index_offset+4),` |
| `TlzOpener.TryOpen` | `Offset       = file.View.ReadUInt32 (index_offset+8),` |
| `TlzOpener.TryOpen` | `uint name_length = file.View.ReadUInt32 (index_offset+0xC);` |
| `TlzOpener.TryOpen` | `entry.Name = file.View.ReadString (index_offset+0x10, name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Otemoto.TlzOpener

继承/接口：`ArchiveFormat`。

#### TlzOpener

```csharp
public TlzOpener () {
    ContainedFormats = new[] { "BMP", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (4);
    if (index_offset >= file.MaxOffset)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new PackedEntry {
            UnpackedSize = file.View.ReadUInt32 (index_offset),
            Size         = file.View.ReadUInt32 (index_offset+4),
            Offset       = file.View.ReadUInt32 (index_offset+8),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        uint name_length = file.View.ReadUInt32 (index_offset+0xC);
        if (0 == name_length || name_length > 0x100)
            return null;
        entry.Name = file.View.ReadString (index_offset+0x10, name_length);
        entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name, ContainedFormats);
        entry.IsPacked = entry.UnpackedSize != entry.Size;
        dir.Add (entry);
        index_offset += 0x10 + name_length;
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

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Otemoto/ArcTLZ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
