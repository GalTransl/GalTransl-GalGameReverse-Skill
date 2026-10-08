# FC01 / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/AGSI` / `GameRes.Formats.FC01.PakOpener` | `pak` | `5041434b`, `2820a024` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.OpenEncryptedEntry` | `header_size = output.ToInt32 (output.Length-4);` |
| `IndexReader.Create` | `if (!file.View.AsciiEqual (0, "PACK"))` |
| `IndexReader.Create` | `var header = file.View.ReadBytes (0, 12);` |
| `IndexReader.Create` | `byte k1 = file.View.ReadByte (file.MaxOffset-9);` |
| `IndexReader.Create` | `byte k2 = file.View.ReadByte (file.MaxOffset-6);` |
| `IndexReader.Create` | `if (!header.AsciiEqual ("PACK"))` |
| `IndexReader.Create` | `count = header.ToInt32 (4);` |
| `IndexReader.Create` | `record_size = header.ToInt32 (8);` |
| `IndexReader.Create` | `count = file.View.ReadInt32 (4);` |
| `IndexReader.Create` | `record_size = file.View.ReadInt32 (8);` |
| `IndexReader.ReadIndex` | `entry.UnpackedSize = index.ReadUInt32();` |
| `IndexReader.ReadIndex` | `entry.Size         = index.ReadUInt32();` |
| `IndexReader.ReadIndex` | `entry.Method       = index.ReadInt32();` |
| `IndexReader.ReadIndex` | `entry.Offset       = index.ReadUInt32() + DataOffset;` |
| `IndexReader.ReadIndex` | `var name = index.ReadCString (name_size);` |
| `IndexReader.OpenIndex` | `var index = m_file.View.ReadBytes (12, (uint)index_size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FC01.AgsiEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int  Method ;

public bool IsEncrypted { get { return Method >= 3 && (Method <= 5 || Method == 7); } }

public bool IsSpecial ;
```

### GameRes.Formats.FC01.AgsiArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### AgsiArchive

```csharp
public AgsiArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.FC01.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static AgsiScheme DefaultScheme = new AgsiScheme {
    KnownSchemes = new Dictionary<string, IDictionary<string, byte[]>>()
}
```

#### PakOpener

```csharp
public PakOpener () {
    Signatures = new uint[] { 0x4B434150, 0x24A02028, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var reader = IndexReader.Create (file);
    if (null == reader)
        return null;
    var dir = reader.ReadIndex();
    if (null == dir)
        return null;
    if (dir.Cast<AgsiEntry>().Any (e => e.IsEncrypted))
    {
        var scheme = QueryScheme (file);
        if (null == scheme)
        {
            Trace.WriteLine ("Unknown AGSI encryption scheme", "[PAK/AGSI]");
            return null;
        }
        var arc_name = Path.GetFileName (file.Name).ToLowerInvariant();
        byte[] key;
        if (scheme.TryGetValue (arc_name, out key) && key != null)
            return new AgsiArchive (file, this, dir, key);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var aent = entry as AgsiEntry;
    var aarc = arc as AgsiArchive;
    if (null == aent)
        return base.OpenEntry (arc, entry);
    Stream input;
    if (!aent.IsEncrypted)
        input = arc.File.CreateStream (entry.Offset, entry.Size);
    else if (aarc != null && aarc.Key != null)
        input = OpenEncryptedEntry (aarc, aent);
    else
        return base.OpenEntry (arc, entry);
    switch (aent.Method)
    {
    case 0:
    case 3:
        break;
    case 1:
    case 4:
        input = new PackedStream<RleDecompressor> (input, new RleDecompressor ((int)aent.UnpackedSize));
        break;
    case 2:
    case 5:
        input = new PackedStream<LzBitStream> (input, new LzBitStream ((int)aent.UnpackedSize));
        break;
    case 6:
    case 7:
        input = new LzssStream (input);
        break;
    }
    return input;
}
```

#### OpenEncryptedEntry

```csharp
internal Stream OpenEncryptedEntry (AgsiArchive arc, AgsiEntry entry) {
    uint enc_size = entry.Size;
    if (enc_size > 1024)
    {
        enc_size = 1032;
    }
    using (var des = DES.Create())
    {
        des.Key = arc.Key;
        des.Mode = CipherMode.ECB;
        des.Padding = PaddingMode.Zeros;
        using (var enc = arc.File.CreateStream (entry.Offset, enc_size))
        using (var dec = new InputCryptoStream (enc, des.CreateDecryptor()))
        {
            var output = new byte[enc_size];
            dec.Read (output, 0, output.Length);
            int header_size;
            if (!entry.IsSpecial)
            {
                header_size = output.ToInt32 (output.Length-4);
                if (header_size > entry.UnpackedSize)
                    throw new InvalidEncryptionScheme();
            }
            else
                header_size = (int)entry.UnpackedSize;
            if (!entry.IsSpecial && entry.Size > enc_size)
            {
                var header = new byte[header_size];
                Buffer.BlockCopy (output, 0, header, 0, header_size);
                var input = arc.File.CreateStream (entry.Offset + enc_size, entry.Size - enc_size);
                return new PrefixStream (header, input);
            }
            else
                return new BinMemoryStream (output, 0, header_size, entry.Name);
        }
    }
}
```

#### QueryScheme

```csharp
protected IDictionary<string, byte[]> QueryScheme (ArcView file) {
    var title = FormatCatalog.Instance.LookupGame (file.Name, "*.sb")
             ?? FormatCatalog.Instance.LookupGame (file.Name, @"..\*.sb");
    if (string.IsNullOrEmpty (title) || !KnownSchemes.ContainsKey (title))
        return null;
    return KnownSchemes[title];
}
```

### GameRes.Formats.FC01.IndexReader

#### 状态与常量

```csharp
ArcView     m_file ;

int         m_count ;

int         m_record_size ;

public bool IsEncrypted { get; set; }

public uint  DataOffset { get; set; }
```

#### IndexReader

```csharp
public IndexReader (ArcView file, int count, int record_size, bool is_encrypted = false) {
    m_file = file;
    m_count = count;
    m_record_size = record_size;
    DataOffset = (uint)(0xC + m_count * m_record_size);
    IsEncrypted = is_encrypted;
}
```

#### Create

```csharp
public static IndexReader Create (ArcView file) {
    int count, record_size;
    bool is_encrypted = false;
    if (!file.View.AsciiEqual (0, "PACK"))
    {
        var header = file.View.ReadBytes (0, 12);
        byte k1 = file.View.ReadByte (file.MaxOffset-9);
        byte k2 = file.View.ReadByte (file.MaxOffset-6);
        DecryptHeader (header, k1, k2);
        if (!header.AsciiEqual ("PACK"))
            return null;
        count = header.ToInt32 (4);
        record_size = header.ToInt32 (8);
        is_encrypted = true;
    }
    else
    {
        count = file.View.ReadInt32 (4);
        record_size = file.View.ReadInt32 (8);
    }
    if (!ArchiveFormat.IsSaneCount (count) || record_size <= 0x10 || record_size > 0x100)
        return null;
    var reader = new IndexReader (file, count, record_size, is_encrypted);
    if (reader.DataOffset >= file.MaxOffset)
        return null;
    return reader;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    using (var index = OpenIndex())
        return ReadIndex (index);
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex (IBinaryStream index) {
    int name_size = m_record_size - 0x10;
    var dir = new List<Entry> (m_count);
    for (int i = 0; i < m_count; ++i)
    {
        var entry = new AgsiEntry();
        entry.UnpackedSize = index.ReadUInt32();
        entry.Size         = index.ReadUInt32();
        entry.Method       = index.ReadInt32();
        entry.Offset       = index.ReadUInt32() + DataOffset;
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return null;
        var name = index.ReadCString (name_size);
        if (string.IsNullOrEmpty (name))
            return null;
        entry.Name = name;
        entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
        entry.IsPacked = entry.Method != 0 && entry.Method != 3;
        entry.IsSpecial = name.Equals ("Copyright.Dat", StringComparison.OrdinalIgnoreCase);
        dir.Add (entry);
    }
    return dir;
}
```

#### OpenIndex

```csharp
IBinaryStream OpenIndex () {
    int index_size = m_count * m_record_size;
    if (IsEncrypted)
    {
        var index = m_file.View.ReadBytes (12, (uint)index_size);
        DecryptIndex (index, 0, index_size, 7524u);
        return new BinMemoryStream (index);
    }
    else
        return m_file.CreateStream (12, (uint)index_size);
}
```

#### DecryptHeader

```csharp
static void DecryptHeader (byte[] header, byte k1, byte k2) {
    int shift = k2 & 7;
    if (0 == shift)
        shift = 1;
    for (int i = 0; i < header.Length; ++i)
    {
        byte x = Binary.RotByteL (header[i], shift);
        header[i] = (byte)(x ^ k1++);
    }
}
```

#### DecryptIndex

```csharp
static void DecryptIndex (byte[] data, int pos, int length, uint seed) {
    var rnd = new MersenneTwister (seed);
    for (int i = 0; i < length; ++i)
    {
        uint key = rnd.Rand();
        int shift = (int)key & 7;
        if (0 == shift)
            shift = 1;
        byte x = Binary.RotByteL (data[pos+i], shift);
        data[pos+i] = (byte)(key ^ x);
    }
}
```

### GameRes.Formats.FC01.LzBitStream

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
MsbBitStream    m_input ;

int             m_unpacked_size ;

bool m_disposed = false ;
```

#### LzBitStream

```csharp
public LzBitStream (int unpacked_size) {
    m_unpacked_size = unpacked_size;
}
```

#### Initialize

```csharp
public override void Initialize (Stream input) {
    m_input = new MsbBitStream (input, true);
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    var frame = new byte[0x1000];
    int dst = 0;
    int frame_pos = 1;
    while (dst < m_unpacked_size)
    {
        int bit = m_input.GetNextBit();
        if (bit != 0)
        {
            if (-1 == bit)
                yield break;
            int v = m_input.GetBits (8);
            if (-1 == v)
                yield break;
            frame[frame_pos++ & 0xFFF] = m_buffer[m_pos++] = (byte)v;
            dst++;
            if (0 == --m_length)
                yield return m_pos;
        }
        else
        {
            int offset = m_input.GetBits (12);
            if (-1 == offset)
                yield break;
            int count = m_input.GetBits (4);
            if (-1 == count)
                yield break;
            count += 2;
            dst += count;
            while (count --> 0)
            {
                byte v = frame[offset++ & 0xFFF];
                frame[frame_pos++ & 0xFFF] = v;
                m_buffer[m_pos++] = v;
                if (0 == --m_length)
                    yield return m_pos;
            }
        }
    }
}
```

### GameRes.Formats.FC01.RleDecompressor

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
int             m_unpacked_size ;
```

#### RleDecompressor

```csharp
public RleDecompressor (int unpacked_size) {
    m_unpacked_size = unpacked_size;
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    throw new NotImplementedException();
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。
- [ArcFormats/MersenneTwister.cs](../MersenneTwister.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/FC01/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
