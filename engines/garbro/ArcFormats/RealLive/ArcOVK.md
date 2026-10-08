# RealLive / ArcOVK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `OVK` / `GameRes.Formats.RealLive.OvkOpener` | `ovk`, `nwk` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `OvkOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `OvkOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index_offset);` |
| `OvkOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset+4);` |
| `OvkOpener.TryOpen` | `uint id     = file.View.ReadUInt32 (index_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RealLive.OvkOpener

继承/接口：`ArchiveFormat`。

#### OvkOpener

```csharp
public OvkOpener () {
    Extensions = new string[] { "ovk", "nwk" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint entry_size;
    string entry_ext;
    if (file.Name.HasExtension (".ovk"))
    {
        entry_size = 0x10;
        entry_ext = "ogg";
    }
    else if (file.Name.HasExtension (".nwk"))
    {
        entry_size = 0xC;
        entry_ext = "nwa";
    }
    else
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint data_offset = 4 + (uint)count * entry_size;
    if (data_offset >= file.MaxOffset)
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint size   = file.View.ReadUInt32 (index_offset);
        uint offset = file.View.ReadUInt32 (index_offset+4);
        uint id     = file.View.ReadUInt32 (index_offset+8);
        if (offset < data_offset)
            return null;
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D5}.{2}", base_name, id, entry_ext),
            Type = "audio",
            Offset = offset,
            Size   = size,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RealLive/ArcOVK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
