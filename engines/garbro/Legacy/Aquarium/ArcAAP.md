# Aquarium / ArcAAP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AAP` / `GameRes.Formats.Aquarium.AapOpener` | `aap` | `46504152` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AapOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "FPARC10\0"))` |
| `AapOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0x10);` |
| `AapOpener.TryOpen` | `int count = file.View.ReadInt32 (0x14);` |
| `AapOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `AapOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x10) + data_offset;` |
| `AapOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x14);` |
| `AapOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+0x18);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aquarium.AapOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "FPARC10\0"))
        return null;
    uint index_offset = file.View.ReadUInt32 (0x10);
    int count = file.View.ReadInt32 (0x14);
    if (index_offset >= file.MaxOffset || !IsSaneCount (count))
        return null;
    uint data_offset = index_offset + (uint)count * 0x30;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x10) + data_offset;
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x14);
        entry.Size = file.View.ReadUInt32 (index_offset+0x18);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.UnpackedSize != 0;
        dir.Add (entry);
        index_offset += 0x30;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var data = new byte[pent.UnpackedSize];
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
        Cp2Reader.DecompressLz (input, data);
    return new BinMemoryStream (data, entry.Name);
}
```

## 配套算法与外部条件

- [Legacy/Aquarium/ImageCP2.cs](ImageCP2.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Aquarium/ArcAAP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
