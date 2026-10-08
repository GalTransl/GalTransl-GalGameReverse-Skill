# ShapeShifter / ArcBND：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BND` / `GameRes.Formats.ShapeShifter.BndOpener` | `bnd` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BndOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `BndOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (4);` |
| `BndOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `BndOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `BndOpener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset+4),` |
| `BndOpener.TryOpen` | `Size = file.View.ReadUInt32 (index_offset+8),` |
| `BndOpener.DetectFileTypes` | `var signature = file.View.ReadUInt32 (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ShapeShifter.BndOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    uint first_offset = file.View.ReadUInt32 (4);
    if (first_offset != 4 +(uint)count * 12)
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name).ToUpperInvariant();
    string default_type = base_name == "SCR" ? "script" :
                          base_name == "VOICE" || base_name == "SE" ? "audio" :
                          base_name == "PICT" ? "image" : "";
    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        var entry = new PackedEntry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Type = default_type,
            Offset = file.View.ReadUInt32 (index_offset),
            UnpackedSize = file.View.ReadUInt32 (index_offset+4),
            Size = file.View.ReadUInt32 (index_offset+8),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.UnpackedSize != entry.Size;
        dir.Add (entry);
        index_offset += 12;
    }
    if (string.IsNullOrEmpty (default_type))
        DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size, entry.Name);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    using (var mem = new MemoryStream())
    using (var lz = new LzssStream (input, LzssMode.Decompress, true))
    {
        lz.CopyTo (mem);
        if (mem.Length == pent.UnpackedSize)
            return mem;
    }
    input.Position = 0;
    var compr = new Kurumi.MpkCompression (input, (int)pent.UnpackedSize);
    var data = compr.Unpack();
    return new BinMemoryStream (data);
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (ArcView file, List<Entry> dir) {
    foreach (PackedEntry entry in dir)
    {
        var offset = entry.Offset;
        var signature = file.View.ReadUInt32 (offset);
        if (entry.IsPacked  && (0x4D42   == (signature & 0xFFFF)) ||
            !entry.IsPacked && (0x4D4207 == (signature & 0xFFFF07)))
        {
            entry.Type = "image";
            entry.Name = Path.ChangeExtension (entry.Name, "bmp");
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/ShapeShifter/ArcBND.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
