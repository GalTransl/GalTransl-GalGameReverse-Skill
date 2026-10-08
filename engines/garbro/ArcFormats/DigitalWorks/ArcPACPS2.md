# DigitalWorks / ArcPACPS2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/PS2` / `GameRes.Formats.DigitalWorks.PacPS2Opener` | `pac` | `50414300` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacPS2Opener.TryOpen` | `uint filename_index = file.View.ReadUInt32(4);` |
| `PacPS2Opener.TryOpen` | `int count = file.View.ReadInt32(8);` |
| `PacPS2Opener.TryOpen` | `var name = file.View.ReadString (filename_index + i * 0x40, 0x40);` |
| `PacPS2Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset + i * 8);` |
| `PacPS2Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset + i * 8 + 4);` |
| `PacPS2Opener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "LZS\0"))` |
| `PacPS2Opener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `PacPS2Opener.OpenEntry` | `pent.UnpackedSize = header.ToUInt32 (4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DigitalWorks.PacPS2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint filename_index = file.View.ReadUInt32(4);
    int count = file.View.ReadInt32(8);
    uint index_offset = 0x0C;

    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    int i = 0;
    while (i < count)
    {
        var name = file.View.ReadString (filename_index + i * 0x40, 0x40);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset + i * 8);
        entry.Size   = file.View.ReadUInt32 (index_offset + i * 8 + 4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        i++;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent)
        return base.OpenEntry (arc, entry);
    if (!pent.IsPacked)
    {
        if (!arc.File.View.AsciiEqual (entry.Offset, "LZS\0"))
            return base.OpenEntry (arc, entry);
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);
    }
    var input = arc.File.CreateStream (entry.Offset+8, entry.Size-8);
    bool embedded_lzs = (input.Signature & ~0xF0u) == 0x535A4C0F;
    var lzs = new LzssStream (input);
    if (embedded_lzs)
    {
        var header = new byte[8];
        lzs.Read (header, 0, 8);
        pent.UnpackedSize = header.ToUInt32 (4);
        lzs = new LzssStream (lzs);
    }
    return lzs;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DigitalWorks/ArcPACPS2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
