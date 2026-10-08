# CatSystem / ArcIRIS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/IRIS` / `GameRes.Formats.CatSystem.IrisPckOpener` | `dat` | `49524953` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IrisPckOpener.TryOpen` | `if (!file.View.AsciiEqual(4, "PCK"))` |
| `IrisPckOpener.TryOpen` | `uint name_length = file.View.ReadUInt32(offset);` |
| `IrisPckOpener.TryOpen` | `char c = (char)file.View.ReadUInt16(offset + i);` |
| `IrisPckOpener.TryOpen` | `int count = (int)file.View.ReadUInt32(offset);` |
| `IrisPckOpener.TryOpen` | `uint size = file.View.ReadUInt32(offset);` |
| `IrisPckOpener.TryOpen` | `uint padded_size = file.View.ReadUInt32(offset + 4);` |
| `IrisPckOpener.TryOpen` | `name_length = file.View.ReadUInt32(offset + 8);` |
| `IrisPckOpener.TryOpen` | `char c = (char)file.View.ReadUInt16(offset + j);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CatSystem.IrisPckOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.View.AsciiEqual(4, "PCK"))
        return null;

    uint offset = 0x18;
    var dir = new List<Entry>();
    var name_buffer = new StringBuilder();

    while (offset < file.MaxOffset) {
        offset += 8;
        uint name_length = file.View.ReadUInt32(offset);

        offset += 8;
        name_buffer.Clear();
        for (int i = 0; i < name_length; i += 2) {
            char c = (char)file.View.ReadUInt16(offset + i);
            if (c == 0)
                break;
            name_buffer.Append(c);
        }
        var dirname = name_buffer.ToString().Replace("/", "\\");
        offset += name_length;

        offset += 4;
        int count = (int)file.View.ReadUInt32(offset);
        var dir_inner = new List<Entry>(count);

        offset += 0xC;
        uint prev = 0;
        for (int i = 0; i < count; i++) {
            offset += 8;
            uint size = file.View.ReadUInt32(offset);
            uint padded_size = file.View.ReadUInt32(offset + 4);
            name_length = file.View.ReadUInt32(offset + 8);
            offset += 0x18;
            name_buffer.Clear();
            for (int j = 0; j < name_length; j += 2) {
                char c = (char)file.View.ReadUInt16(offset + j);
                if (c == 0)
                    break;
                name_buffer.Append(c);
            }
            var basename = name_buffer.ToString();
            var entry = Create<Entry>(Path.Combine(dirname, basename));
            entry.Offset = prev;
            entry.Size = size;
            prev += padded_size;
            offset += name_length;
            dir_inner.Add(entry);
        }

        for (int i = 0; i < count; i++) {
            dir_inner[i].Offset += offset;
        }
        offset += prev;
        dir.AddRange(dir_inner);
    }

    return new ArcFile(file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Experimental/CatSystem/ArcIRIS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
