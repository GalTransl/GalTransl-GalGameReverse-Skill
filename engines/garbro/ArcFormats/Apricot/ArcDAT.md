# Apricot / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/MPF2` / `GameRes.Formats.Apricot.Mpf2Opener` | `dat` | `4d504632` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Mpf2Opener.TryOpen` | `uint index_length = file.View.ReadUInt32 (8);` |
| `Mpf2Opener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (0x10);` |
| `Mpf2Opener.TryOpen` | `int entry_length = index.ReadInt32();` |
| `Mpf2Opener.TryOpen` | `bool is_deleted = index.ReadUInt32() != 0;` |
| `Mpf2Opener.TryOpen` | `entry.Offset = index.ReadInt64() + data_offset;` |
| `Mpf2Opener.TryOpen` | `index.ReadUInt32();` |
| `Mpf2Opener.TryOpen` | `entry.Size = index.ReadUInt32();` |
| `Mpf2Opener.TryOpen` | `entry.UnpackedSize = index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Apricot.Mpf2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_list = new List<Entry>();
    long max_offset = file.MaxOffset;
    for (int i = 1; i < 100; ++i)
    {
        var part_name = Path.ChangeExtension (file.Name, string.Format ("a{0:D02}", i));
        if (!VFS.FileExists (part_name))
            break;
        var part = VFS.FindFile (part_name);
        arc_list.Add (part);
        max_offset += part.Size;
    }
    uint index_length = file.View.ReadUInt32 (8);
    uint data_offset = file.View.ReadUInt32 (0x10);
    using (var zindex = file.CreateStream (0x20, index_length))
    using (var uindex = new ZLibStream (zindex, CompressionMode.Decompress))
    using (var index = new BinaryStream (uindex, file.Name))
    {
        var buffer = new byte[500];
        var dir = new List<Entry>();
        while (index.PeekByte() != -1)
        {
            int entry_length = index.ReadInt32();
            if (entry_length <= 528)
                return null;
            bool is_deleted = index.ReadUInt32() != 0;
            var entry = new PackedEntry();
            entry.Offset = index.ReadInt64() + data_offset;
            index.ReadUInt32();
            entry.Size = index.ReadUInt32();
            entry.UnpackedSize = index.ReadUInt32();
            entry.IsPacked = entry.Size != entry.UnpackedSize;
            index.Read (buffer, 0, 500);
            int name_length = index.Read (buffer, 0, entry_length - 528);
            if (!is_deleted && entry.CheckPlacement (max_offset))
            {
                entry.Name = Encoding.Unicode.GetString (buffer, 0, name_length);
                entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
                dir.Add (entry);
            }
        }
        var parts = new List<ArcView> (arc_list.Count);
        try
        {
            foreach (var arc_entry in arc_list)
            {
                var arc_file = VFS.OpenView (arc_entry);
                parts.Add (arc_file);
            }
        }
        catch
        {
            foreach (var part in parts)
                part.Dispose();
            throw;
        }
        return new MultiFileArchive (file, this, dir, parts);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var mpf = (MultiFileArchive)arc;
    var input = mpf.OpenStream (entry);
    var pent = entry as PackedEntry;
    if (pent != null && pent.IsPacked)
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/MultiFileArchive.cs](../MultiFileArchive.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Apricot/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
