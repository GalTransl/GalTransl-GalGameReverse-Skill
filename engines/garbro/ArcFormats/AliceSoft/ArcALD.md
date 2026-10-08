# AliceSoft / ArcALD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ALD` / `GameRes.Formats.AliceSoft.AldOpener` | `ald` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AldOpener.TryOpen` | `uint version = file.View.ReadUInt32 (index_offset);` |
| `AldOpener.TryOpen` | `\|\| 0x10 != file.View.ReadUInt32 (index_offset+4))` |
| `AldOpener.TryOpen` | `int count = file.View.ReadUInt16 (index_offset+9);` |
| `AldOpener.TryOpen` | `uint index_length = (file.View.ReadUInt32 (0) & 0xffffff) << 8;` |
| `AldOpener.TryOpen` | `uint offset = (file.View.ReadUInt32 (index_offset) & 0xffffff) << 8;` |
| `AldOpener.TryOpen` | `uint header_size = file.View.ReadUInt32 (offset);` |
| `AldOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (offset+4);` |
| `AldOpener.TryOpen` | `entry.Name = file.View.ReadString (offset+0x10, header_size-0x10);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AliceSoft.AldOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long index_offset = file.MaxOffset - 0x10;
    if (index_offset <= 0)
        return null;
    uint version = file.View.ReadUInt32 (index_offset);
    if (0x014C4E != version && 0x012020 != version
        || 0x10 != file.View.ReadUInt32 (index_offset+4))
        return null;
    int count = file.View.ReadUInt16 (index_offset+9);
    if (0 == count)
        return null;
    uint index_length = (file.View.ReadUInt32 (0) & 0xffffff) << 8;
    if (index_length > file.View.Reserve (0, index_length))
        return null;
    var dir = new List<Entry> (count);
    index_offset = 3;
    for (int i = 0; i < count; ++i)
    {
        uint offset = (file.View.ReadUInt32 (index_offset) & 0xffffff) << 8;
        if (0 == offset)
            break;
        if (offset >= file.MaxOffset)
            return null;
        dir.Add (new Entry { Offset = offset });
        index_offset += 3;
    }
    foreach (var entry in dir)
    {
        var offset = entry.Offset;
        uint header_size = file.View.ReadUInt32 (offset);
        if (header_size <= 0x10)
            return null;
        entry.Size = file.View.ReadUInt32 (offset+4);
        entry.Name = file.View.ReadString (offset+0x10, header_size-0x10);
        entry.Offset = offset + header_size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AliceSoft/ArcALD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
