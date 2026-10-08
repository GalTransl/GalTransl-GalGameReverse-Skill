# Hexenhaus / ArcODIO：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/ODIO` / `GameRes.Formats.Hexenhaus.BinOpener` | `bin` | `4f44494f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `if (0 != file.View.ReadUInt32 (4) \|\| 0xCCAE01FF != file.View.ReadUInt32 (0xA))` |
| `BinOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0x12);` |
| `BinOpener.TryOpen` | `next_offset = i+1 == count ? (uint)file.MaxOffset : file.View.ReadUInt32 (index_offset);` |
| `BinOpener.OpenEntry` | `if (entry.Size < 0x2C \|\| !arc.File.View.AsciiEqual (entry.Offset, "ONCE"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Hexenhaus.BinOpener

继承/接口：`ArchiveFormat`。

#### BinOpener

```csharp
public BinOpener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0 != file.View.ReadUInt32 (4) || 0xCCAE01FF != file.View.ReadUInt32 (0xA))
        return null;
    uint first_offset = file.View.ReadUInt32 (0x12);
    int count = (int)(first_offset - 0x12) / 6;
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);

    uint next_offset = first_offset;
    uint index_offset = 0x12;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D4}.ogg", base_name, i),
            Type = "audio",
            Offset = next_offset,
        };
        index_offset += 6;
        next_offset = i+1 == count ? (uint)file.MaxOffset : file.View.ReadUInt32 (index_offset);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size < 0x2C || !arc.File.View.AsciiEqual (entry.Offset, "ONCE"))
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset+0x2C, entry.Size-0x2C);
    return new Ror4EncryptedStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/Hexenhaus/ArcWAG.cs](ArcWAG.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Hexenhaus/ArcODIO.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
