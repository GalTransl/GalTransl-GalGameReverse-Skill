# Nexas / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC` / `GameRes.Formats.NeXAS.PacOpener` | `pac` | `50414300` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "PAC"))` |
| `IndexReaderV1.IndexReaderV1` | `m_count = file.View.ReadInt32 (4);` |
| `IndexReaderV1.IndexReaderV1` | `m_pack_type = file.View.ReadInt32 (8);` |
| `IndexReaderV1.ReadV1` | `uint index_size = m_file.View.ReadUInt32 (m_file.MaxOffset-4);` |
| `IndexReaderV1.ReadV1` | `var index_packed = m_file.View.ReadBytes (m_file.MaxOffset-4-index_size, index_size);` |
| `IndexReaderV1.ReadFromStream` | `var name = index.ReadCString (name_length, m_encoding);` |
| `IndexReaderV1.ReadFromStream` | `entry.Offset        = index.ReadUInt32 ();` |
| `IndexReaderV1.ReadFromStream` | `entry.UnpackedSize  = index.ReadUInt32 ();` |
| `IndexReaderV1.ReadFromStream` | `entry.Size          = index.ReadUInt32 ();` |
| `IndexReaderV0.IndexReaderV0` | `m_header_size = file.View.ReadUInt32 (3);` |
| `IndexReaderV0.Read` | `c = (byte)input.ReadByte ();` |
| `IndexReaderV0.Read` | `entry.Offset = input.ReadUInt32 () + m_header_size;` |
| `IndexReaderV0.Read` | `entry.Size   = input.ReadUInt32 ();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum Compression
    {
        None,
        Lzss,
        Huffman,
        Deflate,
        DeflateOrNone,
        None2,
        Zstd,
        ZstdOrNone,
        NeedDecryptionOnly = 0xFDFD,
    }
```

### GameRes.Formats.NeXAS.PacArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Compression PackType ;
```

#### PacArchive

```csharp
public PacArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Compression type)
    : base (arc, impl, dir) {
    PackType = type;
}
```

### GameRes.Formats.NeXAS.PacOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
readonly EncodingSetting PacEncoding = new EncodingSetting ("NexasEncodingCP", "DefaultEncoding") ;
```

#### PacOpener

```csharp
public PacOpener () {
    Signatures = new uint[] { 0x00434150, 0 };
    Settings = new[] { PacEncoding };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "PAC"))
        return null;

    List<Entry> dir = null;
    INexasIndexReader reader = new IndexReaderV1 (file, PacEncoding.Get<Encoding> ());
    try
    {
        dir = reader.Read ();
    }
    catch {}

    if (null == dir)
    {
        reader = new IndexReaderV0 (file);
        dir = reader.Read ();

        if (null == dir)
            return null;
    }

    if (Compression.None == reader.PackType)
        return new ArcFile (file, this, dir);
    return new PacArchive (file, this, dir, reader.PackType);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pac = arc as PacArchive;
    var pent = entry as PackedEntry;

    if (null == pac)
        return input;
    if (Compression.NeedDecryptionOnly == pac.PackType)
    {
        using (input)
        {
            var data = new byte[entry.Size];
            input.Read (data, 0, data.Length);
            for (int i = 0; i < Math.Min (3, data.Length); i++)
                data[i] = (byte)~data[i];
            return new BinMemoryStream (data, entry.Name);
        }
    }
    if (null == pent || !pent.IsPacked)
        return input;

    switch (pac.PackType)
    {
    case Compression.Lzss:
        return new LzssStream (input);

    case Compression.Huffman:
        using (input)
        {
            var packed = new byte[entry.Size];
            input.Read (packed, 0, packed.Length);
            var unpacked = HuffmanDecode (packed, (int)pent.UnpackedSize);
            return new BinMemoryStream (unpacked, 0, (int)pent.UnpackedSize, entry.Name);
        }
    case Compression.Deflate:
    case Compression.DeflateOrNone:
        return new ZLibStream (input, CompressionMode.Decompress);
    case Compression.Zstd:
    case Compression.ZstdOrNone:
    {
        using (input)
        {
            var unpacked = ZstdDecompress (input, pent.UnpackedSize);
            return new BinMemoryStream (unpacked, entry.Name);
        }
    }
    default:
        return input;
    }
}
```

#### HuffmanDecode

```csharp
static private byte[] HuffmanDecode (byte[] packed, int unpacked_size) {
    var dst = new byte[unpacked_size];
    var decoder = new HuffmanDecoder (packed, dst);
    return decoder.Unpack ();
}
```

#### ZstdDecompress

```csharp
static private byte[] ZstdDecompress (Stream s, uint unpackedSize) {
    using (var ds = new ZstdSharp.DecompressionStream (s))
    {
        var dst = new byte[unpackedSize];
        int decompressedSize = 0;

        while (decompressedSize < unpackedSize)
        {
            var count = ds.Read (dst, decompressedSize, (int)unpackedSize-decompressedSize);
            if (0 == count)
                return dst;
            decompressedSize += count;
        }

        return dst;
    }
}
```

### GameRes.Formats.NeXAS.PacOpener.IndexReaderV1

继承/接口：`INexasIndexReader`。

#### 状态与常量

```csharp
readonly ArcView    m_file ;

readonly int        m_count ;

readonly int        m_pack_type ;

readonly Encoding   m_encoding ;

const int MaxNameLength = 0x40 ;

public Compression PackType { get { return (Compression)m_pack_type; } }

List<Entry> m_dir ;
```

#### IndexReaderV1

```csharp
public IndexReaderV1 (ArcView file, Encoding enc) {
    m_file = file;
    m_count = file.View.ReadInt32 (4);
    m_pack_type = file.View.ReadInt32 (8);
    m_encoding = enc;
}
```

#### Read

```csharp
public List<Entry> Read () {
    if (!IsSaneCount (m_count))
        return null;
    m_dir = new List<Entry> (m_count);
    bool success = false;
    try
    {
        success = ReadV0 ();
    }
    catch {  }
    if (!success && !ReadV1 ())
        return null;
    return m_dir;
}
```

#### ReadV1

```csharp
bool ReadV1 () {
    uint index_size = m_file.View.ReadUInt32 (m_file.MaxOffset-4);
    int unpacked_size = m_count*0x4C;
    if (index_size >= m_file.MaxOffset || index_size > unpacked_size*2)
        return false;

    var index_packed = m_file.View.ReadBytes (m_file.MaxOffset-4-index_size, index_size);
    for (int i = 0; i < index_packed.Length; ++i)
        index_packed[i] = (byte)~index_packed[i];

    var index = HuffmanDecode (index_packed, unpacked_size);
    using (var input = new BinMemoryStream (index))
        return ReadFromStream (input, 0x40);
}
```

#### ReadV0

```csharp
bool ReadV0 () {
    using (var input = m_file.CreateStream ())
    {
        input.Position = 0xC;
        if (ReadFromStream (input, 0x20))
            return true;
        input.Position = 0xC;
        return ReadFromStream (input, 0x40);
    }
}
```

#### ReadFromStream

```csharp
bool ReadFromStream (IBinaryStream index, int name_length) {
    m_dir.Clear ();
    for (int i = 0; i < m_count; ++i)
    {
        var name = index.ReadCString (name_length, m_encoding);
        if (string.IsNullOrWhiteSpace (name))
            return false;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset        = index.ReadUInt32 ();
        entry.UnpackedSize  = index.ReadUInt32 ();
        entry.Size          = index.ReadUInt32 ();
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return false;
        switch (m_pack_type)
        {
            case 1:
            case 2:
            case 3:
            case 6:
            {
                entry.IsPacked = true;
                break;
            }
            case 4:
            case 7:
            {
                entry.IsPacked = entry.Size != entry.UnpackedSize;
                break;
            }
        }
        m_dir.Add (entry);
    }
    return true;
}
```

### GameRes.Formats.NeXAS.PacOpener.IndexReaderV0

继承/接口：`INexasIndexReader`。

#### 状态与常量

```csharp
readonly ArcView m_file ;

readonly uint    m_header_size ;

public Compression PackType { get { return Compression.NeedDecryptionOnly; } }

List<Entry> m_dir ;
```

#### IndexReaderV0

```csharp
public IndexReaderV0 (ArcView file) {
    m_file = file;
    m_header_size = file.View.ReadUInt32 (3);
}
```

#### Read

```csharp
public List<Entry> Read () {
    m_dir = new List<Entry> ();
    using (var input = m_file.CreateStream ())
    {
        input.Position = 7;
        while (input.Position < m_header_size)
        {
            byte c;
            List<byte> name_buffer = new List<byte> ();
            while (true)
            {
                c = (byte)input.ReadByte ();
                if (c == 0) break;
                name_buffer.Add ((byte)~c);
            }
            var name = Binary.GetCString (name_buffer.ToArray (), 0);
            if (string.IsNullOrWhiteSpace (name))
                return null;
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = input.ReadUInt32 () + m_header_size;
            entry.Size   = input.ReadUInt32 ();
            if (!entry.CheckPlacement (m_file.MaxOffset))
                return null;
            m_dir.Add (entry);
        }
    }
    return m_dir;
}
```

## 配套算法与外部条件

- [ArcFormats/HuffmanCompression.cs](../HuffmanCompression.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。
- [ArcFormats/ResourceSettings.cs](../ResourceSettings.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Nexas/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
