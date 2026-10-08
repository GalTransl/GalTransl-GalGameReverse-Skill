# Leaf / ArcLAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LAC` / `GameRes.Formats.Leaf.LacOpener` | `lac` | `4c414300` | `False` |
| `PAK/LAC` / `GameRes.Formats.Leaf.PakOpener` | `pak` | `4c414300` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LacOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `LacOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x3E);` |
| `LacOpener.TryOpen` | `entry.IsPacked = 0 != file.View.ReadByte (index_offset);` |
| `LacOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset);` |
| `LacOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);` |
| `LacOpener.TryOpen` | `entry.Offset = file.View.ReadInt64 (index_offset+0xC);` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PakOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset);` |
| `PakOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `PakOpener.OpenEntry` | `uint size = arc.File.View.ReadUInt32 (entry.Offset);` |
| `PakOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Leaf.LacOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 8;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x3E);
        if (string.IsNullOrEmpty (name))
            return null;
        index_offset += 0x3E;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.IsPacked = 0 != file.View.ReadByte (index_offset);
        index_offset += 0xE;
        entry.Size = file.View.ReadUInt32 (index_offset);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);
        entry.Offset = file.View.ReadInt64 (index_offset+0xC);
        index_offset += 0x2C;
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
    var input = base.OpenEntry (arc, entry);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    var lzs = new LzssStream (input);
    lzs.Config.FrameFill = 0x20;
    return lzs;
}
```

### GameRes.Formats.Leaf.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 8;
    var dir = new List<Entry> (count);
    var name_buf = new byte[0x20];
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_offset, name_buf, 0, 0x20);
        index_offset += 0x20;
        int l;
        for (l = 0; l < 0x1F && name_buf[l] != 0; ++l)
        {
            name_buf[l] ^= 0xFF;
        }
        if (0 == l)
            return null;
        var name = Encodings.cp932.GetString (name_buf, 0, l);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.IsPacked = 0 != name_buf[0x1F];
        entry.Size = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        index_offset += 8;
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
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked || entry.Size <= 4)
        return base.OpenEntry (arc, entry);
    if (0 == pent.UnpackedSize)
    {
        uint size = arc.File.View.ReadUInt32 (entry.Offset);
        if (size == pent.Size)
        {
            pent.Offset += 4;
            pent.Size -= 4;
        }
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
        pent.Offset += 4;
        pent.Size -= 4;
        if (0 == pent.UnpackedSize)
            ++pent.UnpackedSize;
    }
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new LzssStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Leaf/ArcLAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
