# RealLive / ArcPCK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCK/FLIX` / `GameRes.Formats.RealLive.PckOpener` | `pck` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PckOpener.TryOpen` | `int version = file.View.ReadInt32 (0);` |
| `PckOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PckOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (8) + offset;` |
| `PckOpener.TryOpen` | `uint pos_offset = file.View.ReadUInt32 (0xC) + offset;` |
| `PckOpener.TryOpen` | `name_lengths[i] = file.View.ReadUInt32 (offset);` |
| `PckOpener.TryOpen` | `var name_buf = file.View.ReadBytes (offset, name_length);` |
| `PckOpener.TryOpen` | `dir[i].Offset = file.View.ReadUInt32 (offset);` |
| `PckOpener.TryOpen` | `dir[i].Size = file.View.ReadUInt32 (offset + 8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RealLive.PckOpener

继承/接口：`ArchiveFormat`。

#### PckOpener

```csharp
public PckOpener () {
    Extensions = new string[] { "pck" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (0);
    if (version != 1)
        return null;
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint offset = 0x20;
    uint data_offset = file.View.ReadUInt32 (8) + offset;
    uint pos_offset = file.View.ReadUInt32 (0xC) + offset;
    if (data_offset >= file.MaxOffset || pos_offset >= file.MaxOffset)
        return null;

    var dir = new List<Entry> (count);
    var name_lengths = new uint[count];
    for (int i = 0; i < count; i++)
    {
        name_lengths[i] = file.View.ReadUInt32 (offset);
        offset += 4;
    }
    for (int i = 0; i < count; i++)
    {
        uint name_length = name_lengths[i];
        var name_buf = file.View.ReadBytes (offset, name_length);
        var entry = Create<Entry> (Encoding.Unicode.GetString (name_buf, 0, (int)name_length));
        dir.Add (entry);
        offset += name_length;
    }
    offset = pos_offset;
    for (int i = 0; i < count; i++)
    {
        dir[i].Offset = file.View.ReadUInt32 (offset);
        dir[i].Size = file.View.ReadUInt32 (offset + 8);
        if (!dir[i].CheckPlacement (file.MaxOffset))
            return null;
        offset += 0x10;
    }

    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RealLive/ArcPCK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
