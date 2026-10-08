# Nug / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/FWA` / `GameRes.Formats.Nug.FwaOpener` | `dat` | `31415746` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `FwaOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `FwaOpener.TryOpen` | `long index_offset = file.View.ReadUInt32 (0x10) + count * 4;` |
| `FwaOpener.TryOpen` | `uint entry_size = file.View.ReadUInt32 (index_offset);` |
| `FwaOpener.TryOpen` | `var name = file.View.ReadString (index_offset+0x10, 0x30);` |
| `FwaOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `FwaOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+8);` |
| `FwaOpener.OpenEntry` | `uint signature = arc.File.View.ReadUInt32 (offset);` |
| `FwaOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (offset+0x10);` |
| `FwaOpener.OpenEntry` | `entry.Size = arc.File.View.ReadUInt32 (offset+0x10);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nug.FwaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    long index_offset = file.View.ReadUInt32 (0x10) + count * 4;
    uint index_size = (uint)count * 0x40u;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> ();
    for (int i = 0; i < count; ++i)
    {
        uint entry_size = file.View.ReadUInt32 (index_offset);
        if (entry_size < 0x40)
            break;
        var name = file.View.ReadString (index_offset+0x10, 0x30);
        var entry = Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        entry.Size   = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.UnpackedSize = entry.Size;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    var offset = entry.Offset;
    uint signature = arc.File.View.ReadUInt32 (offset);
    if (!pent.IsPacked && entry.Size > 0x20)
    {
        if (signature == 0x46574353)
        {
            pent.IsPacked = true;
            pent.UnpackedSize = arc.File.View.ReadUInt32 (offset+0x10);
            entry.Offset += 0x20;
            entry.Size -= 0x20;
        }
        else if (signature == 0x46574343)
        {
            entry.Offset += 0x20;
            entry.Size = arc.File.View.ReadUInt32 (offset+0x10);
        }
    }
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (pent.IsPacked)
        input = new LzssStream (input);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Nug/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
