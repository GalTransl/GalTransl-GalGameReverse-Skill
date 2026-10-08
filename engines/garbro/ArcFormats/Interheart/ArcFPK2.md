# Interheart / ArcFPK2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FPK/2.00` / `GameRes.Formats.CandySoft.Fpk2Opener` | `fpk` | `01000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Fpk2Opener.TryOpen` | `if (!file.View.AsciiEqual (4, "2.00"))` |
| `Fpk2Opener.TryOpen` | `int count = file.View.ReadInt32 (0x1C);` |
| `Fpk2Opener.TryOpen` | `var name = file.View.ReadString (index_offset+8, 0x18);` |
| `Fpk2Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `Fpk2Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CandySoft.Fpk2Opener

继承/接口：`FpkOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "2.00"))
        return null;
    int count = file.View.ReadInt32 (0x1C);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 0x20;
    uint index_size = (uint)count * 0x20u;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset+8, 0x18);
        if (!name.StartsWith ("/"))
        {
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = file.View.ReadUInt32 (index_offset);
            entry.Size   = file.View.ReadUInt32 (index_offset+4);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/Interheart/ArcFPK.cs](ArcFPK.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Interheart/ArcFPK2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
