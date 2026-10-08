# FC01 / ArcSCXA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/SCXA` / `GameRes.Formats.FC01.SCXAOpener` | `arc` | `53435841` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SCXAOpener.TryOpen` | `uint datastart = file.View.ReadUInt32(4);` |
| `SCXAOpener.TryOpen` | `int count = file.View.ReadInt32(8);` |
| `SCXAOpener.TryOpen` | `uint namestart = file.View.ReadUInt32(i * 4 + 12);` |
| `SCXAOpener.TryOpen` | `uint fstart = file.View.ReadUInt32(tnstart + namestart);` |
| `SCXAOpener.TryOpen` | `uint flength = file.View.ReadUInt32(tnstart + namestart + 4);` |
| `SCXAOpener.TryOpen` | `c = file.View.ReadByte((long)index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FC01.SCXAOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    uint datastart = file.View.ReadUInt32(4);
    int count = file.View.ReadInt32(8);
    if (!IsSaneCount(count))
        return null;
    uint tnstart = (uint)count * 4 + 12;
    var dir = new List<Entry>(count);
    uint index_offset;
    for (int i = 0; i < count; ++i)
    {
        uint namestart = file.View.ReadUInt32(i * 4 + 12);
        uint fstart = file.View.ReadUInt32(tnstart + namestart);
        uint flength = file.View.ReadUInt32(tnstart + namestart + 4);
        index_offset = tnstart + namestart + 8;
        byte c;
        List<byte> namebyte = new List<byte>();
        while (true)
        {
            c = file.View.ReadByte((long)index_offset);
            if (c == 0 | index_offset > datastart) break;
            namebyte.Add(c);
            index_offset++;
        }
        var name = System.Text.Encoding.ASCII.GetString(namebyte.ToArray());
        var entry = Create<Entry>(name);
        entry.Offset = datastart + fstart;
        entry.Size = flength;
        if (!entry.CheckPlacement(file.MaxOffset))
            return null;
        dir.Add(entry);
    }
    return new ArcFile(file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/FC01/ArcSCXA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
