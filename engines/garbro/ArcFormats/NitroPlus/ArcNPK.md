# NitroPlus / ArcNPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NPK` / `GameRes.Formats.NitroPlus.NpkOpener` | `npk` | `4e504b32`, `4e504b33` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NpkOpener.TryOpen` | `int version = file.View.ReadByte (3) - '0';` |
| `NpkOpener.TryOpen` | `int count = file.View.ReadInt32 (0x18);` |
| `NpkOpener.TryOpen` | `aes.IV = file.View.ReadBytes (8, 0x10);` |
| `NpkOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0x1C);` |
| `NpkOpener.ReadIndex` | `index.ReadByte();` |
| `NpkOpener.ReadIndex` | `int name_length = index.ReadUInt16();` |
| `NpkOpener.ReadIndex` | `entry.UnpackedSize = index.ReadUInt32();` |
| `NpkOpener.ReadIndex` | `int segment_count = index.ReadInt32();` |
| `NpkOpener.ReadIndex` | `segment.Offset = index.ReadInt64();` |
| `NpkOpener.ReadIndex` | `segment.AlignedSize = index.ReadUInt32();` |
| `NpkOpener.ReadIndex` | `segment.Size = index.ReadUInt32();` |
| `NpkOpener.ReadIndex` | `segment.UnpackedSize = index.ReadUInt32();` |
| `NpkStream.ReadByte` | `public override int ReadByte () {` |
| `NpkStream.ReadByte` | `b = m_stream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NitroPlus.NpkEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public readonly List<NpkSegment> Segments = new List<NpkSegment>() ;
```

### GameRes.Formats.NitroPlus.NpkSegment

#### 状态与常量

```csharp
public long Offset ;

public uint AlignedSize ;

public uint Size ;

public uint UnpackedSize ;

public bool IsCompressed { get { return Size < UnpackedSize; } }
```

### GameRes.Formats.NitroPlus.Npk2Options

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] Key ;
```

### GameRes.Formats.NitroPlus.NpkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Aes Encryption ;

public readonly int Version ;

bool _npk_disposed = false ;
```

#### NpkArchive

```csharp
public NpkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Aes enc, int version)
    : base (arc, impl, dir) {
    Encryption = enc;
    Version = version;
}
```

### GameRes.Formats.NitroPlus.NpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static Npk2Scheme DefaultScheme = new Npk2Scheme { KnownKeys = new Dictionary<string, byte[]>() }

const uint DefaultSegmentSize = 0x10000 ;

static readonly Encoding DefaultEncoding = Encoding.UTF8 ;

static readonly HashSet<string> SolidFiles = new HashSet<string> { ".png", ".jpg" }

static readonly HashSet<string> DisableCompression = new HashSet<string> { ".png", ".jpg", ".ogg" }
```

#### NpkOpener

```csharp
public NpkOpener () {
    Signatures = new uint[] { 0x324B504E, 0x334B504E };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadByte (3) - '0';
    int count = file.View.ReadInt32 (0x18);
    if (!IsSaneCount (count))
        return null;
    var key = QueryEncryption (file.Name);
    if (null == key)
        return null;
    var aes = Aes.Create();
    try
    {
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.PKCS7;
        aes.Key = key;
        aes.IV = file.View.ReadBytes (8, 0x10);
        uint index_size = file.View.ReadUInt32 (0x1C);
        using (var decryptor = aes.CreateDecryptor())
        using (var enc_index = file.CreateStream (0x20, index_size))
        using (var dec_index = new CryptoStream (enc_index, decryptor, CryptoStreamMode.Read))
        using (var index = new ArcView.Reader (dec_index))
        {
            var dir = ReadIndex (index, count, file.MaxOffset);
            if (null == dir)
                return null;
            var arc = new NpkArchive (file, this, dir, aes, version);
            aes = null;
            return arc;
        }
    }
    finally
    {
        if (aes != null)
            aes.Dispose();
    }
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (BinaryReader index, int count, long max_offset) {
    var name_buffer = new byte[0x104];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index.ReadByte();
        int name_length = index.ReadUInt16();
        if (0 == name_length || name_length > name_buffer.Length)
            return null;
        index.Read (name_buffer, 0, name_length);
        var name = DefaultEncoding.GetString (name_buffer, 0, name_length);
        var entry = FormatCatalog.Instance.Create<NpkEntry> (name);
        entry.UnpackedSize = index.ReadUInt32();
        index.Read (name_buffer, 0, 0x20);
        int segment_count = index.ReadInt32();
        if (segment_count < 0)
            return null;
        if (0 == segment_count)
        {
            entry.Offset = 0;
            dir.Add (entry);
            continue;
        }
        entry.Segments.Capacity = segment_count;
        uint packed_size = 0;
        bool is_packed = false;
        for (int j = 0; j < segment_count; ++j)
        {
            var segment = new NpkSegment();
            segment.Offset = index.ReadInt64();
            segment.AlignedSize = index.ReadUInt32();
            segment.Size = index.ReadUInt32();
            segment.UnpackedSize = index.ReadUInt32();
            entry.Segments.Add (segment);
            packed_size += segment.AlignedSize;
            is_packed = is_packed || segment.IsCompressed;
        }
        entry.Offset = entry.Segments[0].Offset;
        entry.Size   = packed_size;
        entry.IsPacked = is_packed;
        if (!entry.CheckPlacement (max_offset))
            return null;
        dir.Add (entry);
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var narc = arc as NpkArchive;
    var nent = entry as NpkEntry;
    if (null == narc || null == nent)
        return base.OpenEntry (arc, entry);

    if (1 == nent.Segments.Count && !nent.IsPacked)
    {
        var input = narc.File.CreateStream (nent.Segments[0].Offset, nent.Segments[0].AlignedSize);
        var decryptor = narc.Encryption.CreateDecryptor();
        return new InputCryptoStream (input, decryptor);
    }
    return new NpkStream (narc, nent);
}
```

#### QueryEncryption

```csharp
byte[] QueryEncryption (string arc_name) {
    byte[] key = null;
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title))
        key = GetKey (title);
    if (null == key)
    {
        var options = Query<Npk2Options> (arcStrings.ArcEncryptedNotice);
        key = options.Key;
    }
    return key;
}
```

#### GetKey

```csharp
byte[] GetKey (string title) {
    byte[] key;
    KnownKeys.TryGetValue (title, out key);
    return key;
}
```

#### GenerateAesIV

```csharp
byte[] GenerateAesIV () {
    using (var rng = new RNGCryptoServiceProvider())
    {
        var iv = new byte[0x10];
        rng.GetBytes (iv);
        return iv;
    }
}
```

### GameRes.Formats.NitroPlus.NpkStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
ArcView     m_file ;

Aes         m_encryption ;

int         m_version ;

IEnumerator<NpkSegment> m_segment ;

Stream      m_stream ;

bool        m_eof = false ;

public override bool CanRead { get { return m_stream != null && m_stream.CanRead; } }

public override bool CanSeek { get { return false; } }

public override long Length {
    get { throw new NotSupportedException ("NpkStream.Length not supported"); }
}

public override long Position {
    get { throw new NotSupportedException ("NpkStream.Position not supported."); }
    set { throw new NotSupportedException ("NpkStream.Position not supported."); }
}

bool _disposed = false ;
```

#### NpkStream

```csharp
public NpkStream (NpkArchive arc, NpkEntry entry) {
    m_file = arc.File;
    m_encryption = arc.Encryption;
    m_version = arc.Version;
    m_segment = entry.Segments.GetEnumerator();
    NextSegment();
}
```

#### NextSegment

```csharp
private void NextSegment () {
    if (!m_segment.MoveNext())
    {
        m_eof = true;
        return;
    }
    if (null != m_stream)
        m_stream.Dispose();
    var segment = m_segment.Current;
    m_stream = m_file.CreateStream (segment.Offset, segment.AlignedSize);
    var decryptor = m_encryption.CreateDecryptor();
    m_stream = new InputCryptoStream (m_stream, decryptor);
    if (segment.IsCompressed)
        switch (m_version)
        {
            case 2:
                m_stream = new DeflateStream (m_stream, CompressionMode.Decompress);
                break;
            case 3:
                m_stream = new ZstdSharp.DecompressionStream (m_stream);
                break;
        }
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int total = 0;
    while (!m_eof && count > 0)
    {
        int read = m_stream.Read (buffer, offset, count);
        if (0 != read)
        {
            total += read;
            offset += read;
            count -= read;
        }
        if (0 != count)
            NextSegment();
    }
    return total;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = -1;
    while (!m_eof)
    {
        b = m_stream.ReadByte();
        if (-1 != b)
            break;
        NextSegment();
    }
    return b;
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException ("NpkStream.Seek method is not supported");
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("NpkStream.SetLength method is not supported");
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    throw new NotSupportedException("NpkStream.WriteByte method is not supported");
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/NitroPlus/ArcNPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
