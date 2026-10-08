# Pinpai / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/arcx` / `GameRes.Formats.Pinpai.ArcOpener` | `arc` | `61726378` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `ArcOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x10);` |
| `ArcOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x14);` |
| `ArcOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Pinpai.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var arc_name = Path.GetFileNameWithoutExtension (file.Name).ToLowerInvariant();
    bool is_compressed = arc_name != "wav";
    uint index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Size   = file.View.ReadUInt32 (index_offset+0x10);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".b"))
            entry.Type = "image";
        entry.IsPacked = is_compressed;
        dir.Add (entry);
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    if (0 == pent.UnpackedSize)
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
    var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
    return new LzssStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Pinpai/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
