# Triangle / ArcSUD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SUD` / `GameRes.Formats.Triangle.SudOpener` | `sud` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SudOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "OggS"))` |
| `SudOpener.TryOpen` | `uint first_size = file.View.ReadUInt32 (current_offset);` |
| `SudOpener.TryOpen` | `uint size = file.View.ReadUInt32 (current_offset);` |
| `SudOpener.TryOpen` | `if (file.View.AsciiEqual (current_offset+4, "OggS"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Triangle.SudOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "OggS"))
        return null;

    uint current_offset = 0;
    uint first_size = file.View.ReadUInt32 (current_offset);
    if (first_size >= file.MaxOffset)
        return null;

    var dir = new List<Entry>();
    int n = 0;
    while (current_offset < file.MaxOffset)
    {
        uint size = file.View.ReadUInt32 (current_offset);
        if (current_offset + 4 + (long)size > file.MaxOffset)
            return null;
        if (file.View.AsciiEqual (current_offset+4, "OggS"))
        {
            var entry = new Entry {
                Name    = string.Format ("{0:D5}.ogg", n++),
                Type    = "audio",
                Offset  = current_offset + 4,
                Size    = size,
            };
            dir.Add (entry);
        }
        current_offset += 4+size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Triangle/ArcSUD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
