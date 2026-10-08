# Desire / ArcDSV：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `000/DESIRE` / `GameRes.Formats.Desire.D000Opener` | `000` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `D000Opener.TryOpen` | `if (!IsAscii (file.View.ReadByte (0)))` |
| `D000Opener.TryOpen` | `byte b = file.View.ReadByte (index_pos);` |
| `D000Opener.TryOpen` | `var name = file.View.ReadString (index_pos, 0xC);` |
| `D000Opener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_pos+0xC);` |
| `D000Opener.TryOpen` | `if (index_pos >= file.MaxOffset \|\| file.View.ReadUInt32 (index_pos+0xC) != 0)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Desire.D000Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasAnyOfExtensions (".000", ".001", ".002", ".003"))
        return null;
    if (!IsAscii (file.View.ReadByte (0)))
        return null;
    uint index_pos = 0;
    var dir = new List<Entry>();
    while (index_pos < file.MaxOffset)
    {
        byte b = file.View.ReadByte (index_pos);
        if (0 == b)
            break;
        if (!IsAscii (b))
            return null;
        var name = file.View.ReadString (index_pos, 0xC);
        var entry = Create<Entry> (name);
        entry.Size = file.View.ReadUInt32 (index_pos+0xC);
        if (entry.Size >= file.MaxOffset || 0 == entry.Size)
            return null;
        dir.Add (entry);
        index_pos += 0x10;
    }
    if (index_pos >= file.MaxOffset || file.View.ReadUInt32 (index_pos+0xC) != 0)
        return null;
    uint offset = index_pos + 0x10;
    foreach (var entry in dir)
    {
        entry.Offset = offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        offset += entry.Size;
    }
    if (offset != file.MaxOffset)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### IsAscii

```csharp
static internal bool IsAscii (byte b) {
    return b >= 0x20 && b < 0x7F;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Desire/ArcDSV.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
