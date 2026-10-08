# Tanaka / ArcBMX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BMX` / `GameRes.Formats.Will.BmxOpener` | `bmx` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BmxOpener.TryOpen` | `uint total_size = file.View.ReadUInt32 (0);` |
| `BmxOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `BmxOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x1C);` |
| `BmxOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x1C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.BmxOpener

继承/接口：`ArchiveFormat`。

#### BmxOpener

```csharp
public BmxOpener () {
    ContainedFormats = new[] { "BC" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint total_size = file.View.ReadUInt32 (0);
    if (total_size != file.MaxOffset)
        return null;
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    uint index_offset = 0x10;
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x1C);
        if (0 == name.Length)
            break;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x1C);
        if (string.IsNullOrEmpty (entry.Type))
            entry.Type = "image";
        dir.Add (entry);
        index_offset += 0x20;
    }
    if (0 == dir.Count)
        return null;
    long last_offset = file.MaxOffset;
    for (int i = dir.Count - 1; i >= 0; --i)
    {
        var entry = dir[i];
        entry.Size = (uint)(last_offset - entry.Offset);
        last_offset = entry.Offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Tanaka/ArcBMX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
