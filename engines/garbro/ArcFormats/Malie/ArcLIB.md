# Malie / ArcLIB：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LIBP` / `GameRes.Formats.Malie.DatOpener` | `lib`, `dat` | `b13f503f`, `4e4337c2`, `2215d18c`, `a711d409`, `aa8cc4aa`, `b1bcc29f`, `a300c9aa` | `False` |
| `LIB` / `GameRes.Formats.Malie.LibOpener` | `lib`, `sdp` | `4c494200` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Reader.ReadIndex` | `uint signature = m_view.ReadUInt32 (base_offset);` |
| `Reader.ReadIndex` | `int count = m_view.ReadInt16 (base_offset + 8);` |
| `Reader.ReadIndex` | `string name = m_view.ReadString (index_offset, 0x24);` |
| `Reader.ReadIndex` | `uint entry_size = m_view.ReadUInt32 (index_offset+0x24);` |
| `Reader.ReadIndex` | `long offset = base_offset + m_view.ReadUInt32 (index_offset+0x28);` |
| `DatOpener.TryOpen` | `var decryptor = file.View.AsciiEqual (0, "LIB") ? new NoOpDecryptor() : scheme.CreateDecryptor();` |
| `DatOpener.TryOpen` | `if (Binary.AsciiEqual (header, 0, "LIBP"))` |
| `DatOpener.TryOpen` | `else if (Binary.AsciiEqual (header, 0, "LIBU"))` |
| `DatOpener.UnpackPsbz` | `if (!header.AsciiEqual ("PSBZ"))` |
| `DatOpener.UnpackPsbz` | `int unpacked_size = header.ToInt32 (4);` |
| `LibPReader.ReadIndex` | `int count = LittleEndian.ToInt32 (m_header, 4);` |
| `LibPReader.ReadIndex` | `int offset_count = LittleEndian.ToInt32 (m_header, 8);` |
| `LibPReader.ReadDir` | `int flags   = LittleEndian.ToInt32 (m_index, current_offset+0x14);` |
| `LibPReader.ReadDir` | `int offset  = LittleEndian.ToInt32 (m_index, current_offset+0x18);` |
| `LibPReader.ReadDir` | `uint size   = LittleEndian.ToUInt32 (m_index, current_offset+0x1c);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Malie.LibOpener

继承/接口：`ArchiveFormat`。

#### LibOpener

```csharp
public LibOpener () {
    Extensions = new string[] { "lib", "sdp" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var reader = new Reader (file);
    if (reader.ReadIndex ("", 0, (uint)file.MaxOffset))
        return new ArcFile (file, this, reader.Dir);
    else
        return null;
}
```

### GameRes.Formats.Malie.LibOpener.Reader

#### 状态与常量

```csharp
ArcView.Frame   m_view ;

List<Entry>     m_dir = new List<Entry>() ;

public List<Entry> Dir { get { return m_dir; } }
```

#### Reader

```csharp
public Reader (ArcView file) {
    m_view = file.View;
}
```

#### ReadIndex

```csharp
public bool ReadIndex (string root, long base_offset, uint size) {
    uint signature = m_view.ReadUInt32 (base_offset);
    if (0x0042494C != signature)
        return false;

    int count = m_view.ReadInt16 (base_offset + 8);
    if (count <= 0)
        return false;
    long index_offset = base_offset + 0x10;
    uint index_size = (uint)(0x30 * count);
    if (index_size > size)
        return false;
    if (index_size > m_view.Reserve (index_offset, index_size))
        return false;
    long data_offset = index_offset + index_size;
    if (m_dir.Capacity < m_dir.Count + count)
        m_dir.Capacity = m_dir.Count + count;
    for (int i = 0; i < count; ++i)
    {
        string name = m_view.ReadString (index_offset, 0x24);
        uint entry_size = m_view.ReadUInt32 (index_offset+0x24);
        long offset = base_offset + m_view.ReadUInt32 (index_offset+0x28);
        index_offset += 0x30;
        string ext = Path.GetExtension (name);
        name = Path.Combine (root, name);
        if (string.IsNullOrEmpty (ext) && ReadIndex (name, offset, entry_size))
        {
            continue;
        }
        if (offset < data_offset || offset + entry_size > base_offset + size)
            return false;

        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = entry_size;
        m_dir.Add (entry);
    }
    return true;
}
```

### GameRes.Formats.Malie.MalieArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IMalieDecryptor Decryptor ;
```

#### MalieArchive

```csharp
public MalieArchive (ArcView file, ArchiveFormat format, ICollection<Entry> dir, IMalieDecryptor decr)
    : base (file, format, dir) {
    Decryptor = decr;
}
```

### GameRes.Formats.Malie.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "lib", "dat" };
    Signatures = new uint[] { 0, 0x3F503FB1, 0xC237434E, 0x8CD11522, 0x09D411A7, 0xAAC48CAA, 0x9FC2BCB1, 0xAAC900A3 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 0x10)
        return null;
    var header = new byte[0x10];
    foreach (var scheme in KnownSchemes.Values)
    {
        var decryptor = file.View.AsciiEqual (0, "LIB") ? new NoOpDecryptor() : scheme.CreateDecryptor();
        ReadEncrypted (file.View, decryptor, 0, header, 0, 0x10);
        ILibIndexReader reader;
        if (Binary.AsciiEqual (header, 0, "LIBP"))
            reader = new LibPReader (file, decryptor, header, scheme);
        else if (Binary.AsciiEqual (header, 0, "LIBU"))
            reader = LibUReader.Create (file, decryptor);
        else
            continue;
        using (reader)
        {
            if (reader.ReadIndex())
                return new MalieArchive (file, this, reader.Dir, decryptor);
        }
    }
    return null;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var march = arc as MalieArchive;
    if (null == march)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    Stream input = new EncryptedStream (march.File, march.Decryptor);
    input = new StreamRegion (input, entry.Offset, entry.Size);
    if (entry.Name.HasExtension (".txtz"))
    {
        input = new ZLibStream (input, CompressionMode.Decompress);
    }
    else if (entry.Name.HasExtension (".psbz"))
    {
        input = UnpackPsbz (input);
    }
    return input;
}
```

#### UnpackPsbz

```csharp
Stream UnpackPsbz (Stream input) {
    var header = new byte[8];
    input.Read (header, 0, 8);
    if (!header.AsciiEqual ("PSBZ"))
    {
        input.Position = 0;
        return input;
    }
    int unpacked_size = header.ToInt32 (4);
    var output = new MemoryStream (unpacked_size);
    using (input = new ZLibStream (input, CompressionMode.Decompress))
        input.CopyTo (output);
    output.Position = 0;
    return output;
}
```

#### ReadEncrypted

```csharp
private static int ReadEncrypted (ArcView.Frame view, IMalieDecryptor dec, long offset, byte[] buffer, int index, int length) {
    int offset_pad  = (int)offset & 0xF;
    int aligned_len = (offset_pad + length + 0xF) & ~0xF;
    byte[] aligned_buf;
    int block = 0;
    if (aligned_len == length)
    {
        aligned_buf = buffer;
        block = index;
    }
    else
    {
        aligned_buf = new byte[aligned_len];
    }

    int read = view.Read (offset - offset_pad, aligned_buf, block, (uint)aligned_len);
    if (read < offset_pad)
        return 0;

    for (int block_count = aligned_len / 0x10; block_count > 0; --block_count)
    {
        dec.DecryptBlock (offset, aligned_buf, block);
        block  += 0x10;
        offset += 0x10;
    }
    if (aligned_buf != buffer)
        Buffer.BlockCopy (aligned_buf, offset_pad, buffer, index, length);
    return Math.Min (length, read-offset_pad);
}
```

### GameRes.Formats.Malie.DatOpener.LibIndexReader

继承/接口：`ILibIndexReader`。

#### 状态与常量

```csharp
protected ArcView.Frame     m_view ;

protected readonly long     m_max_offset ;

protected IMalieDecryptor   m_dec ;

protected List<Entry>       m_dir = new List<Entry>() ;

protected byte[]            m_header ;

public List<Entry> Dir { get { return m_dir; } }
```

#### LibIndexReader

```csharp
protected LibIndexReader (ArcView file, IMalieDecryptor decryptor, byte[] header) {
    m_view = file.View;
    m_max_offset = file.MaxOffset;
    m_dec = decryptor;
    m_header = header;
}
```

#### ReadIndex

```csharp
public abstract bool ReadIndex () ;
```

### GameRes.Formats.Malie.DatOpener.LibPReader

继承/接口：`LibIndexReader`。

#### 状态与常量

```csharp
byte[]      m_index ;

long        m_base_offset ;

uint[]      m_offset_table ;

LibScheme   m_scheme ;
```

#### LibPReader

```csharp
public LibPReader (ArcView file, IMalieDecryptor decryptor, byte[] header, LibScheme scheme)
    : base (file, decryptor, header) {
    m_base_offset = 0;
    m_scheme = scheme;
}
```

#### ReadIndex

```csharp
public override bool ReadIndex () {
    int count = LittleEndian.ToInt32 (m_header, 4);
    if (!IsSaneCount (count))
        return false;
    int offset_count = LittleEndian.ToInt32 (m_header, 8);

    m_index     = new byte[0x20 * count];
    var offsets = new byte[4 * offset_count];

    m_base_offset += 0x10;
    if (m_index.Length != ReadEncrypted (m_view, m_dec, m_base_offset, m_index, 0, m_index.Length))
        return false;
    m_base_offset += m_index.Length;
    if (offsets.Length != ReadEncrypted (m_view, m_dec, m_base_offset, offsets, 0, offsets.Length))
        return false;
    m_offset_table = new uint[offset_count];
    Buffer.BlockCopy (offsets, 0, m_offset_table, 0, offsets.Length);

    m_base_offset += offsets.Length;
    m_base_offset = m_scheme.GetAlignedOffset (m_base_offset);

    m_dir.Capacity = offset_count;
    ReadDir ("", 0, 1);
    return m_dir.Count > 0;
}
```

#### ReadDir

```csharp
private void ReadDir (string root, int entry_index, int count) {
    int current_offset = entry_index * 0x20;
    for (int i = 0; i < count; ++i)
    {
        string name = Binary.GetCString (m_index, current_offset, 0x14);
        int flags   = LittleEndian.ToInt32 (m_index, current_offset+0x14);
        int offset  = LittleEndian.ToInt32 (m_index, current_offset+0x18);
        uint size   = LittleEndian.ToUInt32 (m_index, current_offset+0x1c);
        current_offset += 0x20;
        if (name.StartsWith ("/"))
            name = name.Substring (1);
        name = Path.Combine (root, name);
        if (0 == (flags & 0x30000))
        {
            if (offset > entry_index)
                ReadDir (name, (int)offset, (int)size);
            continue;
        }
        long entry_offset = m_base_offset + ((long)m_offset_table[offset] << 10);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        if (entry.CheckPlacement (m_max_offset))
        {
            entry.Offset = entry_offset;
            entry.Size   = size;
            m_dir.Add (entry);
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Malie/ArcLIBU.cs](ArcLIBU.md)：本页引用的随包算法资料。
- [ArcFormats/Malie/LibScheme.cs](LibScheme.md)：本页引用的随包算法资料。
- [ArcFormats/Malie/MalieEncryption.cs](MalieEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Malie/ArcLIB.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
