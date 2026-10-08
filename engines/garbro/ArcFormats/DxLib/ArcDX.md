# DxLib / ArcDX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DXA` / `GameRes.Formats.DxLib.DxOpener` | `dxa`, `hud`, `usi`, `med`, `dat`, `bin`, `bcx`, `wolf` | `d48eef19`, `ddcefca9`, `d30fee0a`, `11f22355`, `11f22455`, `e45ffc69`, `d99ee109`, `835dcc7d`, `73445dc5` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DxOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (0);` |
| `DxOpener.TryOpen` | `uint sig_key = LittleEndian.ToUInt32 (key, 0);` |
| `DxOpener.GuessKey` | `uint key0 = LittleEndian.ToUInt32 (key, 0);` |
| `DxOpener.GuessKey` | `uint index_offset = file.View.ReadUInt32 (12) ^ key0;` |
| `DxOpener.GuessKeyV6` | `var header = file.View.ReadBytes (0, 0x30);` |
| `DxOpener.GuessKeyV6` | `uint key0 = header.ToUInt32 (0);` |
| `DxOpener.GuessKeyV6` | `uint data_offset_hi = header.ToUInt32 (12) ^ key0;` |
| `DxOpener.GuessKeyV6` | `uint key2 = header.ToUInt32 (8);` |
| `DxOpener.GuessKeyV6` | `uint key1 = header.ToUInt32 (0x1C);` |
| `DxOpener.GuessKeyV6` | `long index_offset = header.ToInt64 (0x10) ^ key1 ^ ((long)key2 << 32);` |
| `DxOpener.Unpack` | `uint unpacked_size = input.ReadUInt32();` |
| `DxOpener.Unpack` | `int remaining = input.ReadInt32() - 9;` |
| `DxOpener.Unpack` | `byte control_code = input.ReadByte();` |
| `DxOpener.Unpack` | `byte b = input.ReadByte();` |
| `DxOpener.Unpack` | `b = input.ReadByte();` |
| `DxOpener.Unpack` | `count \|= input.ReadByte() << 5;` |
| `DxOpener.Unpack` | `offset = input.ReadByte();` |
| `DxOpener.Unpack` | `offset = input.ReadUInt16();` |
| `DxOpener.Unpack` | `offset \|= input.ReadByte() << 16;` |
| `DxOpener.ReadArcHeaderV4` | `var header = file.View.ReadBytes (4, 0x18);` |
| `DxOpener.ReadArcHeaderV4` | `IndexSize  = LittleEndian.ToUInt32 (header, 0),` |
| `DxOpener.ReadArcHeaderV4` | `BaseOffset = LittleEndian.ToUInt32 (header, 4),` |
| `DxOpener.ReadArcHeaderV4` | `IndexOffset = LittleEndian.ToUInt32 (header, 8),` |
| `DxOpener.ReadArcHeaderV4` | `FileTable  = LittleEndian.ToUInt32 (header, 0x0C),` |
| `DxOpener.ReadArcHeaderV4` | `DirTable   = LittleEndian.ToUInt32 (header, 0x10),` |
| `DxOpener.ReadArcHeaderV6` | `var header = file.View.ReadBytes (4, 0x2C);` |
| `DxOpener.ReadArcHeaderV6` | `IndexSize  = LittleEndian.ToUInt32 (header, 0),` |
| `DxOpener.ReadArcHeaderV6` | `BaseOffset = LittleEndian.ToInt64 (header, 4),` |
| `DxOpener.ReadArcHeaderV6` | `IndexOffset = LittleEndian.ToInt64 (header, 0x0C),` |
| `DxOpener.ReadArcHeaderV6` | `FileTable  = LittleEndian.ToInt64 (header, 0x14),` |
| `DxOpener.ReadArcHeaderV6` | `DirTable   = LittleEndian.ToInt64 (header, 0x1C),` |
| `DxOpener.ReadArcHeaderV6` | `CodePage   = LittleEndian.ToInt32 (header, 0x24),` |
| `IndexReader.ExtractFileName` | `int name_offset = m_input.ReadUInt16() * 4 + 4;` |
| `IndexReader.ExtractFileName` | `return m_input.ReadCString (m_encoding);` |
| `IndexReaderV2.ReadDirEntry` | `dir.DirOffset = m_input.ReadInt32();` |
| `IndexReaderV2.ReadDirEntry` | `dir.ParentDirOffset = m_input.ReadInt32();` |
| `IndexReaderV2.ReadDirEntry` | `dir.FileCount = m_input.ReadInt32();` |
| `IndexReaderV2.ReadDirEntry` | `dir.FileTable = m_input.ReadInt32();` |
| `IndexReaderV2.ReadFileTable` | `root = Path.Combine (root, ExtractFileName (m_input.ReadUInt32()));` |
| `IndexReaderV2.ReadFileTable` | `uint name_offset = m_input.ReadUInt32();` |
| `IndexReaderV2.ReadFileTable` | `uint attr = m_input.ReadUInt32();` |
| `IndexReaderV2.ReadFileTable` | `uint offset = m_input.ReadUInt32();` |
| `IndexReaderV2.ReadFileTable` | `uint size = m_input.ReadUInt32();` |
| `IndexReaderV2.ReadFileTable` | `packed_size = m_input.ReadInt32();` |
| `IndexReaderV6.ReadDirEntry` | `dir.DirOffset = m_input.ReadInt64();` |
| `IndexReaderV6.ReadDirEntry` | `dir.ParentDirOffset = m_input.ReadInt64();` |
| `IndexReaderV6.ReadDirEntry` | `dir.FileCount = (int)m_input.ReadInt64();` |
| `IndexReaderV6.ReadDirEntry` | `dir.FileTable = m_input.ReadInt64();` |
| `IndexReaderV6.ReadFileTable` | `root = Path.Combine (root, ExtractFileName (m_input.ReadInt64()));` |
| `IndexReaderV6.ReadFileTable` | `var name_offset = m_input.ReadInt64();` |
| `IndexReaderV6.ReadFileTable` | `uint attr = (uint)m_input.ReadInt64();` |
| `IndexReaderV6.ReadFileTable` | `var offset = m_input.ReadInt64();` |
| `IndexReaderV6.ReadFileTable` | `var size = m_input.ReadInt64();` |
| `IndexReaderV6.ReadFileTable` | `var packed_size = m_input.ReadInt64();` |
| `EncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `EncryptedStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DxLib.DxArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IDxKey Encryption ;

public readonly int Version ;
```

#### DxArchive

```csharp
public DxArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IDxKey enc, int version)
    : base (arc, impl, dir) {
    Encryption = enc;
    Version = version;
}
```

### GameRes.Formats.DxLib.DxOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
DxScheme DefaultScheme = new DxScheme { KnownKeys = new List<IDxKey>() }
```

#### DxOpener

```csharp
public DxOpener () {
    Extensions = new string[] { "dxa", "hud", "usi", "med", "dat", "bin", "bcx", "wolf" };
    Signatures = new uint[] {
        0x19EF8ED4, 0xA9FCCEDD, 0x0AEE0FD3, 0x5523F211, 0x5524F211, 0x69FC5FE4, 0x09E19ED9, 0x7DCC5D83,
        0xC55D4473, 0
    };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset < 0x1C)
        return null;
    uint signature = file.View.ReadUInt32 (0);
    foreach (var enc in KnownKeys)
    {
        var key = enc.Key;
        uint sig_key = LittleEndian.ToUInt32 (key, 0);
        uint sig_test = signature ^ sig_key;
        int version = (int)(sig_test >> 16);
        if (0x5844 == (sig_test & 0xFFFF) && version <= 7)
        {
            var dir = ReadIndex (file, version, key);
            if (null != dir)
            {
                if (KnownKeys[0] != enc)
                {

                    KnownKeys.Remove (enc);
                    KnownKeys.Insert (0, enc);
                }
                return new DxArchive (file, this, dir, enc, version);
            }
            return null;
        }
    }
    var arc = GuessKey (file);
    if (arc != null)
    {
        var encryption = arc.Encryption;
        KnownKeys.Insert (0, encryption);

    }
    return arc;
}
```

#### GuessKey

```csharp
DxArchive GuessKey (ArcView file) {
    if (file.MaxOffset > uint.MaxValue)
        return null;
    var key = GuessKeyV6 (file);
    if (key != null)
    {
        var dir = ReadIndex (file, 6, key);
        if (dir != null)
            return new DxArchive (file, this, dir, DxKey.CreateInstanceFromKey (key), 6);
    }
    key = new byte[12];
    for (short version = 4; version >= 1; --version)
    {
        file.View.Read (0, key, 0, 12);
        key[0] ^= (byte)'D';
        key[1] ^= (byte)'X';
        key[2] ^= (byte)version;
        int base_offset = version > 3 ? 0x1C : 0x18;
        key[8] ^= (byte)base_offset;
        uint key0 = LittleEndian.ToUInt32 (key, 0);
        uint index_offset = file.View.ReadUInt32 (12) ^ key0;
        if (index_offset <= base_offset || index_offset >= file.MaxOffset)
            continue;
        uint index_size = (uint)(file.MaxOffset - index_offset);
        if (index_size > 0xFFFFFF)
            continue;
        key[4] ^= (byte)index_size;
        key[5] ^= (byte)(index_size >> 8);
        key[6] ^= (byte)(index_size >> 16);
        try
        {
            var dir = ReadIndex (file, version, key);
            if (null != dir)
                return new DxArchive (file, this, dir, DxKey.CreateInstanceFromKey (key), version);
        }
        catch {  }
    }
    return null;
}
```

#### GuessKeyV6

```csharp
byte[] GuessKeyV6 (ArcView file) {
    var header = file.View.ReadBytes (0, 0x30);
    header[0] ^= (byte)'D';
    header[1] ^= (byte)'X';
    header[2] ^= 6;
    uint key0 = header.ToUInt32 (0);
    header[8] ^= (byte)0x30;
    uint data_offset_hi = header.ToUInt32 (12) ^ key0;
    if (data_offset_hi != 0)
        return null;
    uint key2 = header.ToUInt32 (8);
    uint key1 = header.ToUInt32 (0x1C);
    long index_offset = header.ToInt64 (0x10) ^ key1 ^ ((long)key2 << 32);
    if (index_offset <= 0x30 || index_offset >= file.MaxOffset)
        return null;
    var key = new byte[12];
    LittleEndian.Pack (key0, key, 0);
    LittleEndian.Pack (key1, key, 4);
    LittleEndian.Pack (key2, key, 8);
    return key;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    var dx_arc = arc as DxArchive;
    if (null == dx_arc)
        return input;
    var dx_ent = (PackedEntry)entry;
    long dec_offset = entry.Offset;
    if (dx_arc.Version > 5)
    {
        dec_offset = dx_ent.UnpackedSize;
    }
    var key = dx_arc.Encryption.GetEntryKey (dx_ent.Name);
    input = new EncryptedStream (input, dec_offset, key);
    if (!dx_ent.IsPacked)
        return input;
    using (input)
    {
        var data = Unpack (input);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### Unpack

```csharp
protected byte[] Unpack (Stream stream) {
    using (var input = new ArcView.Reader (stream))
    {
        uint unpacked_size = input.ReadUInt32();
        int remaining = input.ReadInt32() - 9;
        var output = new byte[unpacked_size];
        byte control_code = input.ReadByte();
        int dst = 0;
        while (remaining > 0)
        {
            byte b = input.ReadByte();
            --remaining;
            if (b != control_code)
            {
                output[dst++] = b;
                continue;
            }
            b = input.ReadByte();
            --remaining;
            if (b == control_code)
            {
                output[dst++] = b;
                continue;
            }
            if (b > control_code)
                --b;
            int count = b >> 3;
            if (0 != (b & 4))
            {
                count |= input.ReadByte() << 5;
                --remaining;
            }
            count += 4;
            int offset;
            switch (b & 3)
            {
            case 0:
                offset = input.ReadByte();
                --remaining;
                break;

            case 1:
                offset = input.ReadUInt16();
                remaining -= 2;
                break;

            case 2:
                offset = input.ReadUInt16();
                offset |= input.ReadByte() << 16;
                remaining -= 3;
                break;

            default:
                throw new InvalidFormatException ("DX decompression failed");
            }
            ++offset;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
        return output;
    }
}
```

#### ReadIndex

```csharp
protected List<Entry> ReadIndex (ArcView file, int version, byte[] key) {
    DxHeader dx = null;
    if (version <= 4)
        dx = ReadArcHeaderV4 (file, version, key);
    else if (version >= 6)
        dx = ReadArcHeaderV6 (file, version, key);
    if (null == dx || dx.DirTable >= dx.IndexSize || dx.FileTable >= dx.IndexSize)
        return null;
    using (var encrypted = file.CreateStream (dx.IndexOffset, (uint)dx.IndexSize))
    using (var index = new EncryptedStream (encrypted, version >= 6 ? 0 : dx.IndexOffset, key))
    using (var reader = IndexReader.Create (dx, version, index))
    {
        return reader.Read();
    }
}
```

#### ReadArcHeaderV4

```csharp
DxHeader ReadArcHeaderV4 (ArcView file, int version, byte[] key) {
    var header = file.View.ReadBytes (4, 0x18);
    if (0x18 != header.Length)
        return null;
    Decrypt (header, 0, header.Length, 4, key);
    return new DxHeader {
        IndexSize  = LittleEndian.ToUInt32 (header, 0),
        BaseOffset = LittleEndian.ToUInt32 (header, 4),
        IndexOffset = LittleEndian.ToUInt32 (header, 8),
        FileTable  = LittleEndian.ToUInt32 (header, 0x0C),
        DirTable   = LittleEndian.ToUInt32 (header, 0x10),
        CodePage   = 932,
    };
}
```

#### ReadArcHeaderV6

```csharp
DxHeader ReadArcHeaderV6 (ArcView file, int version, byte[] key) {
    var header = file.View.ReadBytes (4, 0x2C);
    if (0x2C != header.Length)
        return null;
    Decrypt (header, 0, header.Length, 4, key);
    return new DxHeader {
        IndexSize  = LittleEndian.ToUInt32 (header, 0),
        BaseOffset = LittleEndian.ToInt64 (header, 4),
        IndexOffset = LittleEndian.ToInt64 (header, 0x0C),
        FileTable  = LittleEndian.ToInt64 (header, 0x14),
        DirTable   = LittleEndian.ToInt64 (header, 0x1C),
        CodePage   = LittleEndian.ToInt32 (header, 0x24),
    };
}
```

#### Decrypt

```csharp
internal static void Decrypt (byte[] data, int index, int count, long offset, byte[] key) {
    if (key.Length == 0)
        return;
    int key_pos = (int)(offset % key.Length);
    for (int i = 0; i < count; ++i)
    {
        data[index + i] ^= key[key_pos++];
        if (key.Length == key_pos)
            key_pos = 0;
    }
}
```

### GameRes.Formats.DxLib.DxHeader

#### 状态与常量

```csharp
public long BaseOffset ;

public long IndexOffset ;

public long IndexSize ;

public long FileTable ;

public long DirTable ;

public int  CodePage ;
```

### GameRes.Formats.DxLib.IndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
protected readonly int  m_version ;

protected DxHeader      m_header ;

protected BinaryStream  m_input ;

protected Encoding      m_encoding ;

protected List<Entry>   m_dir = new List<Entry>() ;

internal int Version { get { return m_version; } }

bool disposed = false ;
```

#### IndexReader

```csharp
protected IndexReader (DxHeader header, int version, Stream input) {
    m_header = header;
    m_version = version;
    m_input = new BinaryStream (input, "");
    m_encoding = Encoding.GetEncoding (header.CodePage);
}
```

#### Create

```csharp
public static IndexReader Create (DxHeader header, int version, Stream input) {
    if (version <= 4)
        return new IndexReaderV2 (header, version, input);
    else if (version >= 6 && version < 8)
        return new IndexReaderV6 (header, version, input);
    else if (version >= 8)
        return new IndexReaderV8 (header, version, input);
    else
        throw new InvalidFormatException ("Not supported DX archive version.");
}
```

#### Read

```csharp
public List<Entry> Read () {
    ReadFileTable ("", 0);
    return m_dir;
}
```

#### ReadFileTable

```csharp
protected abstract void ReadFileTable (string root, long table_offset) ;
```

#### ExtractFileName

```csharp
protected string ExtractFileName (long table_offset) {
    m_input.Position = table_offset;
    int name_offset = m_input.ReadUInt16() * 4 + 4;
    m_input.Position = table_offset + name_offset;
    return m_input.ReadCString (m_encoding);
}
```

### GameRes.Formats.DxLib.IndexReaderV2

继承/接口：`IndexReader`。

#### 状态与常量

```csharp
readonly int    m_entry_size ;
```

#### IndexReaderV2

```csharp
public IndexReaderV2 (DxHeader header, int version, Stream input) : base (header, version, input) {
    m_entry_size = Version >= 2 ? 0x2C : 0x28;
}
```

#### ReadDirEntry

```csharp
DxDirectory ReadDirEntry () {
    var dir = new DxDirectory();
    dir.DirOffset = m_input.ReadInt32();
    dir.ParentDirOffset = m_input.ReadInt32();
    dir.FileCount = m_input.ReadInt32();
    dir.FileTable = m_input.ReadInt32();
    return dir;
}
```

#### ReadFileTable

```csharp
protected override void ReadFileTable (string root, long table_offset) {
    m_input.Position = m_header.DirTable + table_offset;
    var dir = ReadDirEntry();
    if (dir.DirOffset != -1 && dir.ParentDirOffset != -1)
    {
        m_input.Position = m_header.FileTable + dir.DirOffset;
        root = Path.Combine (root, ExtractFileName (m_input.ReadUInt32()));
    }
    long current_pos = m_header.FileTable + dir.FileTable;
    for (int i = 0; i < dir.FileCount; ++i)
    {
        m_input.Position = current_pos;
        uint name_offset = m_input.ReadUInt32();
        uint attr = m_input.ReadUInt32();
        m_input.Seek (0x18, SeekOrigin.Current);
        uint offset = m_input.ReadUInt32();
        if (0 != (attr & 0x10))
        {
            if (0 == offset || table_offset == offset)
                throw new InvalidFormatException ("Infinite recursion in DXA directory index");
            ReadFileTable (root, offset);
        }
        else
        {
            uint size = m_input.ReadUInt32();
            int packed_size = -1;
            if (Version >= 2)
                packed_size = m_input.ReadInt32();
            var entry = FormatCatalog.Instance.Create<PackedEntry> (Path.Combine (root, ExtractFileName (name_offset)));
            entry.Offset = m_header.BaseOffset + offset;
            entry.UnpackedSize = size;
            entry.IsPacked = -1 != packed_size;
            if (entry.IsPacked)
                entry.Size = (uint)packed_size;
            else
                entry.Size = size;
            m_dir.Add (entry);
        }
        current_pos += m_entry_size;
    }
}
```

### GameRes.Formats.DxLib.IndexReaderV2.DxDirectory

#### 状态与常量

```csharp
public int DirOffset ;

public int ParentDirOffset ;

public int FileCount ;

public int FileTable ;
```

### GameRes.Formats.DxLib.IndexReaderV6

继承/接口：`IndexReader`。

#### 状态与常量

```csharp
readonly int    m_entry_size ;
```

#### IndexReaderV6

```csharp
public IndexReaderV6 (DxHeader header, int version, Stream input) : base (header, version, input) {
    m_entry_size = 0x40;
}
```

#### ReadDirEntry

```csharp
DxDirectory ReadDirEntry () {
    var dir = new DxDirectory();
    dir.DirOffset = m_input.ReadInt64();
    dir.ParentDirOffset = m_input.ReadInt64();
    dir.FileCount = (int)m_input.ReadInt64();
    dir.FileTable = m_input.ReadInt64();
    return dir;
}
```

#### ReadFileTable

```csharp
protected override void ReadFileTable (string root, long table_offset) {
    m_input.Position = m_header.DirTable + table_offset;
    var dir = ReadDirEntry();
    if (dir.DirOffset != -1 && dir.ParentDirOffset != -1)
    {
        m_input.Position = m_header.FileTable + dir.DirOffset;
        root = Path.Combine (root, ExtractFileName (m_input.ReadInt64()));
    }
    long current_pos = m_header.FileTable + dir.FileTable;
    for (int i = 0; i < dir.FileCount; ++i)
    {
        m_input.Position = current_pos;
        var name_offset = m_input.ReadInt64();
        uint attr = (uint)m_input.ReadInt64();
        m_input.Seek (0x18, SeekOrigin.Current);
        var offset = m_input.ReadInt64();
        if (0 != (attr & 0x10))
        {
            if (0 == offset || table_offset == offset)
                throw new InvalidFormatException ("Infinite recursion in DXA directory index");
            ReadFileTable (root, offset);
        }
        else
        {
            var size = m_input.ReadInt64();
            var packed_size = m_input.ReadInt64();
            var entry = FormatCatalog.Instance.Create<PackedEntry> (Path.Combine (root, ExtractFileName (name_offset)));
            entry.Offset = m_header.BaseOffset + offset;
            entry.UnpackedSize = (uint)size;
            entry.IsPacked = -1 != packed_size;
            if (entry.IsPacked)
                entry.Size = (uint)packed_size;
            else
                entry.Size = (uint)size;
            m_dir.Add (entry);
        }
        current_pos += m_entry_size;
    }
}
```

### GameRes.Formats.DxLib.IndexReaderV6.DxDirectory

#### 状态与常量

```csharp
public long DirOffset ;

public long ParentDirOffset ;

public int  FileCount ;

public long FileTable ;
```

### GameRes.Formats.DxLib.EncryptedStream

继承/接口：`ProxyStream`。

#### 状态与常量

```csharp
private int         m_base_pos ;

private byte[]      m_key ;
```

#### EncryptedStream

```csharp
public EncryptedStream (Stream stream, long base_position, byte[] key, bool leave_open = false)
    : base (stream, leave_open) {
    m_key = key;
    m_base_pos = m_key.Length != 0 ? (int)(base_position % m_key.Length) : 0;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    var key_pos = m_base_pos + Position;
    int read = BaseStream.Read (buffer, offset, count);
    if (read > 0)
        DxOpener.Decrypt (buffer, offset, count, key_pos, m_key);
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    long pos = Position;
    int b = BaseStream.ReadByte();
    if (m_key.Length != 0)
    {
        int key_pos = (int)((m_base_pos + pos) % m_key.Length);
        if (-1 != b)
        {
            b ^= m_key[key_pos];
        }
    }
    return b;
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    if (m_key.Length != 0)
    {
        int key_pos = (int)((m_base_pos + Position) % m_key.Length);
        BaseStream.WriteByte ((byte)(value ^ m_key[key_pos]));
    }
    else
    {
        BaseStream.WriteByte ((byte)value);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/DxLib/ArcDX8.cs](ArcDX8.md)：本页引用的随包算法资料。
- [ArcFormats/DxLib/DxKey.cs](DxKey.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DxLib/ArcDX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
