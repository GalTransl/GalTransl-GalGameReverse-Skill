# PenguinWorks / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/PENGUIN` / `GameRes.Formats.PenguinWorks.PacOpener` | `pac` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `PacOpener.TryOpen` | `uint id = file.View.ReadUInt32 (index_offset);` |
| `PacOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `PacOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+8);` |
| `PacOpener.OpenEntry` | `var header = input.ReadHeader (13);` |
| `PacOpener.OpenEntry` | `if (!header.AsciiEqual (2, "ike"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.PenguinWorks.PacOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<string, string> ContentFormats = new Dictionary<string, string> {
    { "TAK", "BIN" },
    { "VIS", "BMP" },
    { "EFT", "WAV" },
    { "BGM", "STR" },
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".pac"))
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name).ToUpperInvariant();
    var name_format = base_name + "{0:D4}";
    if (ContentFormats.ContainsKey (base_name))
        name_format += '.' + ContentFormats[base_name];

    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint id = file.View.ReadUInt32 (index_offset);
        var name = string.Format (name_format, id);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        entry.Size   = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 12;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (!pent.IsPacked)
    {
        var header = input.ReadHeader (13);
        if (!header.AsciiEqual (2, "ike"))
        {
            input.Position = 0;
            return input;
        }
        pent.IsPacked = true;
        pent.UnpackedSize = (uint)IkeReader.DecodeSize (header[10], header[11], header[12]);
    }
    using (input)
    {
        input.Position = 13;
        var reader = new IkeReader (input, (int)pent.UnpackedSize);
        var data = reader.Unpack();
        return new BinMemoryStream (data, entry.Name);
    }
}
```

## 配套算法与外部条件

- [Legacy/UMeSoft/ArcBIN.cs](../UMeSoft/ArcBIN.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/PenguinWorks/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
