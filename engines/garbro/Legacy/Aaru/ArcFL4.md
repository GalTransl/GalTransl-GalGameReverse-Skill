# Aaru / ArcFL4：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FL4/AARU` / `GameRes.Formats.Aaru.Fl4Opener` | `fl4` | `464c342e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Fl4Opener.TryOpen` | `if (file.View.ReadByte (4) != '0')` |
| `Fl4Opener.TryOpen` | `uint data_offset  = file.View.ReadUInt16 (8);` |
| `Fl4Opener.TryOpen` | `uint index_size   = file.View.ReadUInt32 (0xA);` |
| `Fl4Opener.TryOpen` | `long index_offset = file.View.ReadUInt32 (0xE);` |
| `Fl4Opener.TryOpen` | `ushort key   = file.View.ReadUInt16 (0x16);` |
| `Fl4Opener.TryOpen` | `ushort flags = file.View.ReadUInt16 (0x18);` |
| `Fl4Opener.TryOpen` | `var index = file.View.ReadBytes (index_offset, index_size);` |
| `Fl4Opener.TryOpen` | `int pos = index.ToInt32 (0);` |
| `Fl4Opener.TryOpen` | `uint offset = index.ToUInt32 (pos);` |
| `Fl4Opener.TryOpen` | `uint size = index.ToUInt32 (pos+4);` |
| `Fl4Opener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset, "PD2A"))` |
| `Fl4Opener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+12);` |
| `Fl4Opener.OpenEntry` | `else if (arc.File.View.AsciiEqual (entry.Offset, "PD"))` |
| `Fl4Opener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+6);` |
| `Fl4Opener.OpenEntry` | `else if (arc.File.View.AsciiEqual (entry.Offset, "RD1.0"))` |
| `Fl4Opener.OpenEntry` | `uint offset = arc.File.View.ReadUInt16 (entry.Offset+6);` |
| `Fl4Opener.OpenEntry` | `int rle_chunks = arc.File.View.ReadInt32 (entry.Offset+0xA);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aaru.Fl4Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadByte (4) != '0')
        return null;
    uint data_offset  = file.View.ReadUInt16 (8);
    uint index_size   = file.View.ReadUInt32 (0xA);
    long index_offset = file.View.ReadUInt32 (0xE);
    if (index_offset + index_size > file.MaxOffset)
        return null;
    ushort key   = file.View.ReadUInt16 (0x16);
    ushort flags = file.View.ReadUInt16 (0x18);
    var index = file.View.ReadBytes (index_offset, index_size);
    int pos = index.ToInt32 (0);
    if (pos <= 0)
        return null;
    var dir = new List<Entry>();
    while (pos < index.Length)
    {
        uint offset = index.ToUInt32 (pos);
        if (uint.MaxValue == offset)
            break;
        uint size = index.ToUInt32 (pos+4);
        int name_length = index[pos+8];
        pos += 9;
        var name = Encodings.cp932.GetString (index, pos, name_length);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = offset + data_offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        pos += name_length;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
    {
        if (arc.File.View.AsciiEqual (entry.Offset, "PD2A"))
        {
            pent.IsPacked = true;
            pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+12);
        }
        else if (arc.File.View.AsciiEqual (entry.Offset, "PD"))
        {
            pent.IsPacked = true;
            pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+6);
        }
        else if (arc.File.View.AsciiEqual (entry.Offset, "RD1.0"))
        {
            pent.IsPacked = true;
        }
        if (!pent.IsPacked)
            return base.OpenEntry (arc, entry);
    }
    if (arc.File.View.AsciiEqual (entry.Offset, "PD2A"))
    {
        var input = arc.File.CreateStream (entry.Offset+16, entry.Size-16);
        return new LzssStream (input);
    }
    else if (arc.File.View.AsciiEqual (entry.Offset, "PD"))
    {
        var input = arc.File.CreateStream (entry.Offset+10, entry.Size-10);
        return new LzssStream (input);
    }
    else
    {
        uint offset = arc.File.View.ReadUInt16 (entry.Offset+6);
        var input = arc.File.CreateStream (entry.Offset+offset, entry.Size-offset);
        int rle_chunks = arc.File.View.ReadInt32 (entry.Offset+0xA);
        return new RlePackedStream (input, rle_chunks);
    }
}
```

### GameRes.Formats.Aaru.RlePackedStream

继承/接口：`PackedStream<RleDecompressor>`。

#### RlePackedStream

```csharp
public RlePackedStream (Stream input, int rle_chunks) : base (input) {
    Reader.Chunks = rle_chunks;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Aaru/ArcFL4.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
