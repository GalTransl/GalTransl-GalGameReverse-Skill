# Seraphim / ArcSeraph：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SERAPH/ARCH` / `GameRes.Formats.Seraphim.ArchPacOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArchPacOpener.TryOpen` | `uint first_offset = scnpac.View.ReadUInt32 (4);` |
| `ArchPacOpener.TryOpen` | `uint index_offset = scnpac.View.ReadUInt32 (first_offset-4);` |
| `ArchPacOpener.ReadIndex` | `int base_count = file.View.ReadInt32 (index_offset);` |
| `ArchPacOpener.ReadIndex` | `int file_count = file.View.ReadInt32 (index_offset + 4);` |
| `ArchPacOpener.ReadIndex` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `ArchPacOpener.ReadIndex` | `int count = file.View.ReadInt32 (index_offset+4);` |
| `ArchPacOpener.ReadIndex` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `ArchPacOpener.ReadIndex` | `next_offset = file.View.ReadUInt32 (index_offset);` |
| `ArchPacOpener.OpenEntry` | `if (1 == input.Signature && arc.File.View.ReadByte (entry.Offset+4) == 0x78)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Seraphim.ArchEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public short    DirIndex ;

public short    FileIndex ;
```

### GameRes.Formats.Seraphim.ArchPacScheme

#### 状态与常量

```csharp
public long     IndexOffset ;

public short    EventDir ;

public IDictionary<short, short> EventMap ;
```

### GameRes.Formats.Seraphim.SeraphArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly short                       EventDir ;

public readonly IDictionary<short, short>   EventMap ;
```

#### SeraphArchive

```csharp
public SeraphArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ArchPacScheme scheme)
    : base (arc, impl, dir) {
    EventDir = scheme.EventDir;
    EventMap = scheme.EventMap;
}
```

### GameRes.Formats.Seraphim.ArchPacOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public          bool   IsAmbiguous { get { return true; } }

internal static ResourceInstance<ImageFormat> CtFormat = new ResourceInstance<ImageFormat> ("CT") ;

SeraphScheme m_scheme = new SeraphScheme { KnownSchemes = new Dictionary<string, ArchPacScheme>() }
```

#### ArchPacOpener

```csharp
public ArchPacOpener () {
    Extensions = new string[] { "dat" };
    ContainedFormats = new[] { "CB" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset > uint.MaxValue
        || !VFS.IsPathEqualsToFileName (file.Name, "ArchPac.dat"))
        return null;
    foreach (var scheme in KnownSchemes.Values.Where (s => s.IndexOffset < file.MaxOffset).OrderBy (s => s.IndexOffset))
    {
        var dir = ReadIndex (file, scheme.IndexOffset, file.MaxOffset);
        if (dir != null)
        {
            if (scheme.EventMap != null)
                return new SeraphArchive (file, this, dir, scheme);
            else
                return new ArcFile (file, this, dir);
        }
    }
    var scnpac_name = VFS.ChangeFileName (file.Name, "ScnPac.dat");
    if (!VFS.FileExists (scnpac_name))
        return null;
    using (var scnpac = VFS.OpenView (scnpac_name))
    {
        uint first_offset = scnpac.View.ReadUInt32 (4);
        uint index_offset = scnpac.View.ReadUInt32 (first_offset-4);
        var dir = ReadIndex (scnpac, index_offset, file.MaxOffset);
        if (dir != null)
            return new ArcFile (file, this, dir);
    }
    return null;
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (ArcView file, long index_offset, long max_offset) {
    if (index_offset >= max_offset)
        return null;
    int base_count = file.View.ReadInt32 (index_offset);
    int file_count = file.View.ReadInt32 (index_offset + 4);
    index_offset += 8;
    if (base_count <= 0 || base_count > 0x40 || !IsSaneCount (file_count))
        return null;
    var base_offsets = new List<Tuple<uint, int>> (base_count);
    int total_count = 0;
    for (int i = 0; i < base_count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        int count = file.View.ReadInt32 (index_offset+4);
        if (count <= 0 || count > file_count || offset > max_offset)
            return null;
        total_count += count;
        if (total_count > file_count)
            return null;
        base_offsets.Add (Tuple.Create (offset, count));
        index_offset += 8;
    }
    if (total_count != file_count)
        return null;
    var dir = new List<Entry> (file_count);
    for (int j = base_count-1; j >= 0; --j)
    {
        uint next_offset = file.View.ReadUInt32 (index_offset);
        index_offset += 4;
        for (int i = 0; i < base_offsets[j].Item2; ++i)
        {
            var entry = new ArchEntry {
                Name = FormatEntryName (j, i),
                Type = "image",
                DirIndex = (short)j,
                FileIndex = (short)i,
                Offset = next_offset,
            };
            next_offset = file.View.ReadUInt32 (index_offset);
            index_offset += 4;
            if (next_offset < entry.Offset)
                return null;
            entry.Size = (uint)(next_offset - entry.Offset);
            entry.Offset += base_offsets[j].Item1;
            if (!entry.CheckPlacement (max_offset))
                return null;
            if (entry.Size > 0)
                dir.Add (entry);
        }
    }
    if (0 == dir.Count)
        return null;
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent)
        return input;
    if (0x9C78 == (input.Signature & 0xFFFF))
    {
        pent.IsPacked = true;
        return new ZLibStream (input, CompressionMode.Decompress);
    }
    if (1 == input.Signature && arc.File.View.ReadByte (entry.Offset+4) == 0x78)
    {
        pent.IsPacked = true;
        input.Position = 4;
        return new ZLibStream (input, CompressionMode.Decompress);
    }
    return input;
}
```

#### OpenCtImage

```csharp
SeraphReader OpenCtImage (ArcFile arc, Entry entry) {
    using (var input = arc.OpenBinaryEntry (entry))
    {
        if (input.Signature != CtFormat.Value.Signature)
            return null;
        var info = CtFormat.Value.ReadMetaData (input) as SeraphMetaData;
        if (null == info)
            return null;
        var reader = new SeraphReader (input.AsStream, info);
        reader.UnpackCt();
        return reader;
    }
}
```

#### FormatEntryName

```csharp
internal static string FormatEntryName (int dir_index, int file_index) {
    return string.Format ("{0}-{1:D5}.cts", dir_index, file_index);
}
```

## 配套算法与外部条件

- [ArcFormats/Seraphim/ImageSeraph.cs](ImageSeraph.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Seraphim/ArcSeraph.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
