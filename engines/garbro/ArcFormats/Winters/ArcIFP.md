# Winters / ArcIFP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IFP` / `GameRes.Formats.Winters.IfpOpener` | `ifp` | `49414753` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IfpOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "_IFP_01     ")` |
| `IfpOpener.TryOpen` | `\|\| file.View.ReadInt32 (0x10) != 1)` |
| `IfpOpener.TryOpen` | `int count = file.View.ReadInt32 (0x18) / 0x10 - 1;` |
| `IfpOpener.TryOpen` | `int type = file.View.ReadUInt16 (index_offset);` |
| `IfpOpener.TryOpen` | `int mask_type = file.View.ReadUInt16 (index_offset+2);` |
| `IfpOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+4),` |
| `IfpOpener.TryOpen` | `Size = file.View.ReadUInt32 (index_offset+8),` |
| `IfpOpener.TryOpen` | `uint mask_size = file.View.ReadUInt32 (index_offset+12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Winters.IfpOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "_IFP_01     ")
        || file.View.ReadInt32 (0x10) != 1)
        return null;
    int count = file.View.ReadInt32 (0x18) / 0x10 - 1;
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry>();
    for (int i = 0, index_offset = 0x20; i < count; ++i, index_offset += 0x10)
    {
        int type = file.View.ReadUInt16 (index_offset);
        if (0 == type)
            continue;
        int mask_type = file.View.ReadUInt16 (index_offset+2);
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D5}", base_name, i),
            Offset = file.View.ReadUInt32 (index_offset+4),
            Size = file.View.ReadUInt32 (index_offset+8),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        switch (type)
        {
        case 0x0B: entry.ChangeType (ImageFormat.Bmp); break;
        case 0x0C: entry.ChangeType (ImageFormat.Png); break;
        case 0x0D: entry.ChangeType (ImageFormat.Jpeg); break;
        case 0x15: entry.Type = "script"; break;
        }
        dir.Add (entry);
        uint mask_size = file.View.ReadUInt32 (index_offset+12);
        if (0x0B == mask_type && 0 != mask_size)
        {
            entry = new Entry {
                Name = string.Format ("{0}#{1:D5}M.bmp", base_name, i),
                Type = "image",
                Offset = entry.Offset + entry.Size,
                Size = mask_size,
            };
            dir.Add (entry);
        }
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Winters/ArcIFP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
