# Seraphim / ArcSCN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SCN/ARCH` / `GameRes.Formats.Seraphim.Scn95Opener` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `SERAPH/SCN` / `GameRes.Formats.Seraphim.ScnOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ScnOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `ScnOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `ScnOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_offset);` |
| `ScnOpener.OpenEntry` | `uint signature = arc.File.View.ReadUInt32 (entry.Offset);` |
| `ScnOpener.OpenEntry` | `if (1 == signature && 0x78 == arc.File.View.ReadByte (entry.Offset+4))` |
| `ScnOpener.LzDecompress` | `int unpacked_size = input.ReadInt32();` |
| `ScnOpener.LzDecompress` | `int ctl = input.ReadByte();` |
| `ScnOpener.LzDecompress` | `byte lo = input.ReadUInt8();` |
| `Scn95Opener.TryOpen` | `uint offset = file.View.ReadUInt32 (0);` |
| `Scn95Opener.TryOpen` | `uint size = file.View.ReadUInt32 (index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Seraphim.ScnOpener

继承/接口：`ArchiveFormat`。

#### ScnOpener

```csharp
public ScnOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "SCNPAC.DAT"))
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_size = 4 * (uint)count;
    if (index_size > file.View.Reserve (4, index_size))
        return null;

    int index_offset = 4;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    if (next_offset < index_offset + index_size)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new Entry { Name = i.ToString ("D5"), Type = "script" };
        entry.Offset = next_offset;
        next_offset = file.View.ReadUInt32 (index_offset);
        if (next_offset < entry.Offset || next_offset > file.MaxOffset)
            return null;
        entry.Size = next_offset - (uint)entry.Offset;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    uint signature = arc.File.View.ReadUInt32 (entry.Offset);
    IBinaryStream input;
    if (1 == signature && 0x78 == arc.File.View.ReadByte (entry.Offset+4))
    {
        input = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
        return new ZLibStream (input.AsStream, CompressionMode.Decompress);

    }
    input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (signature < 4 || 0 != (signature & 0xFF000000))
    {
        if (0x78 == (signature & 0xFF))
        {
            var compr = new ZLibStream (input.AsStream, CompressionMode.Decompress);
            input = new BinaryStream (compr, entry.Name);
        }
        else
            return input.AsStream;
    }
    try
    {
        var data = LzDecompress (input);
        return new BinMemoryStream (data, entry.Name);
    }
    catch
    {
        return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    finally
    {
        input.Dispose();
    }
}
```

#### LzDecompress

```csharp
internal static byte[] LzDecompress (IBinaryStream input) {
    int unpacked_size = input.ReadInt32();
    var data = new byte[unpacked_size];
    int dst = 0;
    while (dst < unpacked_size)
    {
        int ctl = input.ReadByte();
        if (-1 == ctl)
            throw new EndOfStreamException();
        if (0 != (ctl & 0x80))
        {
            byte lo = input.ReadUInt8();
            int offset = ((ctl << 3 | lo >> 5) & 0x3FF) + 1;
            int count = (lo & 0x1F) + 1;
            Binary.CopyOverlapped (data, dst-offset, dst, count);
            dst += count;
        }
        else
        {
            int count = ctl + 1;
            if (input.Read (data, dst, count) != count)
                throw new EndOfStreamException();
            dst += count;
        }
    }
    return data;
}
```

### GameRes.Formats.Seraphim.Scn95Opener

继承/接口：`ArchiveFormat`。

#### Scn95Opener

```csharp
public Scn95Opener () {
    Extensions = new[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "SCNPAC.DAT"))
        return null;
    uint offset = file.View.ReadUInt32 (0);
    int count = (int)offset / 4;
    if (offset >= file.MaxOffset || !IsSaneCount (count))
        return null;

    int index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint size = file.View.ReadUInt32 (index_offset);
        if (0 == size)
            return null;
        var entry = new Entry {
            Name = i.ToString ("D5"),
            Type = "script",
            Offset = offset + 4,
            Size = size,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        offset += size;
        index_offset += 4;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    IBinaryStream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (input.Signature < 4 || 0 != (input.Signature & 0xFF000000))
    {
        return input.AsStream;
    }
    try
    {
        var data = ScnOpener.LzDecompress (input);
        return new BinMemoryStream (data, entry.Name);
    }
    catch
    {
        return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    finally
    {
        input.Dispose();
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Seraphim/ArcSCN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
