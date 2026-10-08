# DMotion / ArcDM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `256/DMOTION` / `GameRes.Formats.DMotion.PakOpener` | `256` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "FILE100DATA"))` |
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (0x10, @".\\\"))` |
| `PakOpener.TryOpen` | `int ext_count = file.View.ReadUInt16 (0x16);` |
| `PakOpener.TryOpen` | `long index_pos = file.View.ReadUInt32 (0x18);` |
| `PakOpener.TryOpen` | `Name   = file.View.ReadString (index_pos, 4),` |
| `PakOpener.TryOpen` | `Count  = file.View.ReadUInt16 (index_pos+6),` |
| `PakOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_pos+8),` |
| `PakOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_pos+12),` |
| `PakOpener.TryOpen` | `var name = file.View.ReadString (index_pos, 8).TrimEnd() + ext.Name;` |
| `PakOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_pos+8);` |
| `PakOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_pos+12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DMotion.ExtEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int Count ;
```

### GameRes.Formats.DMotion.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "FILE100DATA"))
        return null;
    if (!file.View.AsciiEqual (0x10, @".\\\"))
        return null;
    int ext_count = file.View.ReadUInt16 (0x16);
    long index_pos = file.View.ReadUInt32 (0x18);
    int total_count = 0;
    var ext_dir = new List<ExtEntry> (ext_count);
    for (int i = 0; i < ext_count; ++i)
    {
        var ext = new ExtEntry {
            Name   = file.View.ReadString (index_pos, 4),
            Count  = file.View.ReadUInt16 (index_pos+6),
            Offset = file.View.ReadUInt32 (index_pos+8),
            Size   = file.View.ReadUInt32 (index_pos+12),
        };
        ext_dir.Add (ext);
        total_count += ext.Count;
        index_pos += 0x10;
    }
    if (!IsSaneCount (total_count))
        return null;

    var dir = new List<Entry> (total_count);
    foreach (var ext in ext_dir)
    {
        index_pos = ext.Offset;
        for (int i = 0; i < ext.Count; ++i)
        {
            var name = file.View.ReadString (index_pos, 8).TrimEnd() + ext.Name;
            var entry = Create<Entry> (name);
            entry.Offset = file.View.ReadUInt32 (index_pos+8);
            entry.Size   = file.View.ReadUInt32 (index_pos+12);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_pos += 0x10;
        }
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/DMotion/ArcDM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
