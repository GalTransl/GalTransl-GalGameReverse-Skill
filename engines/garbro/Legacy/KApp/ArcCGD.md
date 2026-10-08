# KApp / ArcCGD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CGD/SPIEL` / `GameRes.Formats.KApp.CgdOpener` | `cgd` | `73706965` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CgdOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "spiel100"))` |
| `CgdOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `CgdOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_pos),` |
| `CgdOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_pos+4),` |
| `CgdOpener.TryOpen` | `Width  = file.View.ReadUInt16 (index_pos+8),` |
| `CgdOpener.TryOpen` | `Height = file.View.ReadUInt16 (index_pos+0xA),` |
| `CgdOpener.TryOpen` | `BPP    = file.View.ReadByte (index_pos+0xE),` |
| `CgdOpener.TryOpen` | `Compression = file.View.ReadByte (index_pos+0xF),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KApp.CgdEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public CgdMetaData Info ;
```

### GameRes.Formats.KApp.CgdOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "spiel100"))
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_pos = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new CgdEntry {
            Name   = string.Format ("{0}#{1:D4}", base_name, i),
            Type   = "image",
            Offset = file.View.ReadUInt32 (index_pos),
            Size   = file.View.ReadUInt32 (index_pos+4),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        var info = entry.Info = new CgdMetaData {
            Width  = file.View.ReadUInt16 (index_pos+8),
            Height = file.View.ReadUInt16 (index_pos+0xA),
            BPP    = file.View.ReadByte (index_pos+0xE),
            DataOffset = 0,
            Compression = file.View.ReadByte (index_pos+0xF),
            RgbOrder = false,
        };
        info.UnpackedSize = info.iWidth * info.iHeight * info.BPP / 8;
        dir.Add (entry);
        index_pos += 0x10;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [Legacy/KApp/ImageCGD.cs](ImageCGD.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/KApp/ArcCGD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
