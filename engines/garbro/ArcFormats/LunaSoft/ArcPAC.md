# LunaSoft / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/LUNA` / `GameRes.Formats.LunaSoft.PacOpener` | `pac` | `82cf82ad` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PacOpener.TryOpen` | `long base_offset = file.View.ReadUInt32 (8);` |
| `PacOpener.ReadIndex` | `read_offset = idx_off => file.View.ReadInt64 (idx_off);` |
| `PacOpener.ReadIndex` | `read_offset = idx_off => file.View.ReadUInt32 (idx_off);` |
| `PacOpener.ReadIndex` | `uint name_length = file.View.ReadUInt32 (current_offset+size_pos+4);` |
| `PacOpener.ReadIndex` | `var name = file.View.ReadString (current_offset, name_length);` |
| `PacOpener.ReadIndex` | `entry.Size = file.View.ReadUInt32 (current_offset+size_pos);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.LunaSoft.PacOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    long base_offset = file.View.ReadUInt32 (8);
    var dir = new List<Entry> (count);
    if (!ReadIndex (file, dir, count, base_offset) &&
        !ReadIndex (file, dir, count, base_offset, true))
        return null;
    return new ArcFile (file, this, dir);
}
```

#### ReadIndex

```csharp
bool ReadIndex (ArcView file, List<Entry> dir, int count, long base_offset, bool long_offsets = false) {
    Func<uint, long> read_offset;
    uint size_pos;
    if (long_offsets)
    {
        read_offset = idx_off => file.View.ReadInt64 (idx_off);
        size_pos = 0x108;
    }
    else
    {
        read_offset = idx_off => file.View.ReadUInt32 (idx_off);
        size_pos = 0x104;
    }
    dir.Clear();
    uint current_offset = 0x10;
    for (int i = 0; i < count; ++i)
    {
        uint name_length = file.View.ReadUInt32 (current_offset+size_pos+4);
        if (name_length > 0x100 || 0 == name_length)
            return false;
        var name = file.View.ReadString (current_offset, name_length);
        var entry = Create<Entry> (name);
        entry.Offset = base_offset + read_offset (current_offset+0x100);
        entry.Size = file.View.ReadUInt32 (current_offset+size_pos);
        if (!entry.CheckPlacement (file.MaxOffset))
            return false;
        dir.Add (entry);
        current_offset += size_pos+8;
    }
    return true;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/LunaSoft/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
