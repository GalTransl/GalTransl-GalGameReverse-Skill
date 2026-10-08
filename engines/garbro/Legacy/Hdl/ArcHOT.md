# Hdl / ArcHOT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/HOT` / `GameRes.Formats.Hdl.HotOpener` | `dat` | `484f5400` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `HotOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != 0)` |
| `HotOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `HotOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `HotOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset) + 0x20,` |
| `HotOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `HotOpener.TryOpen` | `if (0x21 == (file.View.ReadByte (entry.Offset+7) & 0x21))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Hdl.HotOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (4) != 0)
        return null;
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (8);
    if (index_offset >= file.MaxOffset || index_offset + count * 4 > file.MaxOffset)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D5}", base_name, i),
            Offset = file.View.ReadUInt32 (index_offset) + 0x20,
        };
        if (entry.Offset > index_offset)
            return null;
        dir.Add (entry);
        index_offset += 4;
    }
    for (int i = 1; i < count; ++i)
    {
        dir[i-1].Size = (uint)(dir[i].Offset - dir[i-1].Offset);
    }
    dir[count-1].Size = (uint)(index_offset - dir[count-1].Offset);
    foreach (var entry in dir)
    {
        uint signature = file.View.ReadUInt32 (entry.Offset);
        if (0x544F48 == signature)
        {
            if (0x21 == (file.View.ReadByte (entry.Offset+7) & 0x21))
                entry.Type = "image";
        }
        else
            entry.ChangeType (AutoEntry.DetectFileType (signature));
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Hdl/ArcHOT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
