# Sas5 / ArcGAR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GAR/SAS5` / `GameRes.Formats.Sas5.GarOpener` | `gar` | `47415220` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GarOpener.TryOpen` | `int version = file.View.ReadInt32 (4);` |
| `GarOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `GarOpener.TryOpen` | `int block_start = file.View.ReadInt32 (0x14);` |
| `GarOpener.TryOpen` | `int count = file.View.ReadInt32 (index_offset) - 1;` |
| `GarOpener.TryOpen` | `int block = file.View.ReadInt32 (index_offset);` |
| `GarOpener.TryOpen` | `Offset  = file.View.ReadUInt32 (index_offset + 4),` |
| `GarOpener.TryOpen` | `Size    = file.View.ReadUInt32 (index_offset + 12),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sas5.GarOpener

继承/接口：`ArchiveFormat`。

#### GarOpener

```csharp
public GarOpener () {
    Extensions = new string[] { "gar" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (4);
    if (version != 1)
        return null;

    uint index_offset = file.View.ReadUInt32 (8);
    int block_start = file.View.ReadInt32 (0x14);
    int count = file.View.ReadInt32 (index_offset) - 1;
    if (!IsSaneCount (count))
        return null;
    var GetEntryName = CreateEntryNameDelegate (file.Name);

    index_offset += 0x20;
    var dir = new List<Entry> ();
    for (int i = 0; i < count; ++i)
    {
        int block = file.View.ReadInt32 (index_offset);
        if (block == block_start)
            continue;
        var entry = new Entry {
            Name    = GetEntryName (i, block - block_start - 1),
            Offset  = file.View.ReadUInt32 (index_offset + 4),
            Size    = file.View.ReadUInt32 (index_offset + 12),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (block > block_start)
        {
            entry.Type = "video";
        }
        dir.Add (entry);
        index_offset += 0x14;
    }
    return new ArcFile (file, this, dir);
}
```

#### CreateEntryNameDelegate

```csharp
internal Func<int, int, string> CreateEntryNameDelegate (string arc_name) {
    var index = Sec5Opener.LookupIndex (arc_name);
    string base_name = Path.GetFileNameWithoutExtension (arc_name);
    if (null == index)
        return (n, m) => GetDefaultName (base_name, n);
    else
        return (n, m) => {
            Entry entry;
            if (index.TryGetValue (m, out entry))
                return entry.Name.Substring (1);
            return GetDefaultName (base_name, n);
        };
}
```

#### GetDefaultName

```csharp
internal static string GetDefaultName (string base_name, int n) {
    return string.Format ("{0}#{1:D5}", base_name, n);
}
```

## 配套算法与外部条件

- [ArcFormats/Sas5/ArcSec5.cs](ArcSec5.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Sas5/ArcGAR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
