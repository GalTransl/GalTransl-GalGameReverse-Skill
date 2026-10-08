# Triangle / ArcBMX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BMX/TRIANGLE` / `GameRes.Formats.Triangle.BmxOpener` | `bmx`, `wax`, `fx`, `gx` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BmxOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `BmxOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `BmxOpener.TryOpen` | `uint last_offset = file.View.ReadUInt32 (index_size - 4);` |
| `BmxOpener.TryOpen` | `offset = file.View.ReadUInt32 (index_offset);` |
| `BmxOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `BmxOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "fACE"))` |
| `BmxOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4) ^ 0x65641538;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Triangle.BmxOpener

继承/接口：`ArchiveFormat`。

#### BmxOpener

```csharp
public BmxOpener () {
    Extensions = new string[] { "bmx", "wax", "fx", "gx" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_size = (uint)count * 4 + 8;
    if (index_size > file.View.Reserve (0, index_size))
        return null;
    uint index_offset = 4;
    uint offset = file.View.ReadUInt32 (index_offset);
    if (offset != index_size)
        return null;
    uint last_offset = file.View.ReadUInt32 (index_size - 4);
    if (last_offset != file.MaxOffset)
        return null;
    string default_type = "";
    if (file.Name.HasExtension ("fx"))
        default_type = "audio";
    else if (file.Name.HasExtension ("gx"))
        default_type = "image";
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new PackedEntry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Type = default_type,
            Offset = offset,
        };
        offset = file.View.ReadUInt32 (index_offset);
        entry.Size = (uint)(offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    if (string.IsNullOrEmpty (default_type))
    {
        foreach (var entry in dir)
        {
            uint signature = file.View.ReadUInt32 (entry.Offset);
            entry.ChangeType (AutoEntry.DetectFileType (signature));
        }
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
        if (!arc.File.View.AsciiEqual (entry.Offset, "fACE"))
            return base.OpenEntry (arc, entry);
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4) ^ 0x65641538;
    }
    using (var input = arc.File.CreateStream (entry.Offset+8, entry.Size-8))
    {
        var data = new byte[pent.UnpackedSize];
        TriFormat.Unpack (input, data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Triangle/ImageTRI.cs](ImageTRI.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Triangle/ArcBMX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
