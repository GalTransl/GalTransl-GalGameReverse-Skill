# Lilim / ArcFGA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FGA` / `GameRes.Formats.Lilim.FgaOpener` | `fga` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `FgaOpener.TryOpen` | `var index_buffer = file.View.ReadBytes (index_offset, 0x318);` |
| `FgaOpener.TryOpen` | `uint next_offset = index_buffer.ToUInt32 (pos+0xC);` |
| `FgaOpener.TryOpen` | `entry.Offset = index_buffer.ToUInt32 (pos+0xC);` |
| `FgaOpener.TryOpen` | `entry.Size   = index_buffer.ToUInt32 (pos+0x10);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lilim.FgaOpener

继承/接口：`AosOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".fga"))
        return null;
    uint index_offset = 0;
    var index_buffer = file.View.ReadBytes (index_offset, 0x318);
    if (0x318 != index_buffer.Length)
        return null;
    var dir = new List<Entry> (0x20);
    int pos = 0;
    while (pos < index_buffer.Length)
    {
        if (0 == index_buffer[pos])
            break;
        if (0xFF == index_buffer[pos])
        {
            uint next_offset = index_buffer.ToUInt32 (pos+0xC);
            if (next_offset <= index_offset || next_offset >= file.MaxOffset)
                return null;
            index_offset = next_offset;
            if (0x318 != file.View.Read (index_offset, index_buffer, 0, 0x318))
                return null;
            pos = 0;
        }
        else
        {
            var name = Binary.GetCString (index_buffer, pos, 0xC);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = index_buffer.ToUInt32 (pos+0xC);
            entry.Size   = index_buffer.ToUInt32 (pos+0x10);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = name.HasExtension (".scr");
            dir.Add (entry);
            pos += 0x18;
        }
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/Lilim/ArcAOS.cs](ArcAOS.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Lilim/ArcFGA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
