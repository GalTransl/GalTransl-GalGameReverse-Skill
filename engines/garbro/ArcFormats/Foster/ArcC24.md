# Foster / ArcC24：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `C24` / `GameRes.Formats.Foster.C24Opener` | `c24` | `43323400` | `False` |
| `C25` / `GameRes.Formats.Foster.C25Opener` | `c25` | `43323500` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `C24Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `C24Opener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `C24Opener.ReadImageInfo` | `Width   = file.View.ReadUInt32 (offset),` |
| `C24Opener.ReadImageInfo` | `Height  = file.View.ReadUInt32 (offset+4),` |
| `C24Opener.ReadImageInfo` | `OffsetX = file.View.ReadInt32 (offset+8),` |
| `C24Opener.ReadImageInfo` | `OffsetY = file.View.ReadInt32 (offset+12),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Foster.C24Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    uint index_offset = 8;
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        index_offset += 4;
        if (offset > 0 && offset <= file.MaxOffset)
        {
            var entry = new Entry
            {
                Name = string.Format ("{0}@{1:D4}", base_name, i),
                Type = "image",
                Offset = offset,
            };
            dir.Add (entry);
        }
    }
    dir.Sort ((a, b) => (int)(a.Offset - b.Offset));
    for (int i = 1; i < dir.Count; ++i)
    {
        dir[i-1].Size = (uint)(dir[i].Offset - dir[i-1].Offset);
    }
    var last_entry = dir[dir.Count-1];
    last_entry.Size = (uint)(file.MaxOffset - last_entry.Offset);
    return new ArcFile (file, this, dir);
}
```

#### ReadImageInfo

```csharp
internal C24MetaData ReadImageInfo (ArcView file, long offset, int bpp) {
    return new C24MetaData
    {
        Width   = file.View.ReadUInt32 (offset),
        Height  = file.View.ReadUInt32 (offset+4),
        OffsetX = file.View.ReadInt32 (offset+8),
        OffsetY = file.View.ReadInt32 (offset+12),
        BPP     = bpp,
        DataOffset = (uint)(offset + 0x10),
    };
}
```

## 配套算法与外部条件

- [ArcFormats/Foster/ImageC24.cs](ImageC24.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Foster/ArcC24.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
