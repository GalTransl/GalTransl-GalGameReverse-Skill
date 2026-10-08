# DigitalWorks / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/HED` / `GameRes.Formats.DigitalWorks.PacOpener` | `pac` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "PPAC-PAC") && !file.View.AsciiEqual(0, "FANA_V1.0.0.0"))` |
| `PacOpener.TryOpen` | `if (!hed.View.AsciiEqual (0, "PPAC-HED") && !hed.View.AsciiEqual(0, "FANA_V1.0.0.0"))` |
| `PacOpener.TryOpen` | `var name = hed.View.ReadString (index_offset, 0x10);` |
| `PacOpener.TryOpen` | `entry.Offset = hed.View.ReadUInt32 (index_offset+0x10) + data_offset;` |
| `PacOpener.TryOpen` | `entry.Size   = hed.View.ReadUInt32 (index_offset+0x14);` |
| `PacOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "LZS\0"))` |
| `PacOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `PacOpener.OpenEntry` | `pent.UnpackedSize = header.ToUInt32 (4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DigitalWorks.PacOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "PPAC-PAC") && !file.View.AsciiEqual(0, "FANA_V1.0.0.0"))
        return null;
    var hed_name = Path.ChangeExtension (file.Name, "hed");
    if (!VFS.FileExists (hed_name))
        return null;
    using (var hed = VFS.OpenView (hed_name))
    {
        if (!hed.View.AsciiEqual (0, "PPAC-HED") && !hed.View.AsciiEqual(0, "FANA_V1.0.0.0"))
            return null;
        uint index_offset = 0x10;
        const uint data_offset = 0x10;
        int count = (int)(hed.MaxOffset - index_offset) / 0x20;
        if (!IsSaneCount (count))
            return null;
        var dir = new List<Entry> (count);
        while (index_offset+0x20 <= hed.MaxOffset)
        {
            var name = hed.View.ReadString (index_offset, 0x10);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = hed.View.ReadUInt32 (index_offset+0x10) + data_offset;
            entry.Size   = hed.View.ReadUInt32 (index_offset+0x14);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += 0x20;
        }
        return new ArcFile (file, this, dir);
    }
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

来源文件标识 `ArcFormats/DigitalWorks/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
