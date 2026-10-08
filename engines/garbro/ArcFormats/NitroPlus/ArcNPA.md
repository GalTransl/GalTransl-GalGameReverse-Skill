# NitroPlus / ArcNPA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NPA` / `GameRes.Formats.NitroPlus.NpaOpener` | `npa` | `4e504101` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NpaOpener.TryOpen` | `int key1 = file.View.ReadInt32 (7);` |
| `NpaOpener.TryOpen` | `int key2 = file.View.ReadInt32 (11);` |
| `NpaOpener.TryOpen` | `bool compressed = 0 != file.View.ReadByte (15);` |
| `NpaOpener.TryOpen` | `bool encrypted  = 0 != file.View.ReadByte (16);` |
| `NpaOpener.TryOpen` | `int total_count = file.View.ReadInt32 (17);` |
| `NpaOpener.TryOpen` | `int folder_count = file.View.ReadInt32 (21);` |
| `NpaOpener.TryOpen` | `int file_count = file.View.ReadInt32 (25);` |
| `NpaOpener.TryOpen` | `uint dir_size = file.View.ReadUInt32 (37);` |
| `NpaOpener.TryOpen` | `int name_size = file.View.ReadInt32 (cur_offset);` |
| `NpaOpener.TryOpen` | `int type = file.View.ReadByte (cur_offset+4+name_size);` |
| `NpaOpener.TryOpen` | `int  id = file.View.ReadInt32 (info_offset);` |
| `NpaOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (info_offset+4);` |
| `NpaOpener.TryOpen` | `uint size = file.View.ReadUInt32 (info_offset+8);` |
| `NpaOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (info_offset+12);` |
| `EncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `EncryptedStream.ReadByte` | `return m_stream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum NpaVariant
    {
        General,
        LAMENTO, TOTONO
    }
```

### GameRes.Formats.NitroPlus.NpaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte[] RawName ;

public int    FolderId ;
```

### GameRes.Formats.NitroPlus.NpaArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public int                 Key { get; private set; }

public byte[]         KeyTable { get { return m_key_table.Value; } }

private Lazy<byte[]> m_key_table ;
```

#### NpaArchive

```csharp
public NpaArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir,
                   EncryptionScheme scheme, int key)
    : base (arc, impl, dir) {
    Scheme   = scheme;
    Key      = key;
    m_key_table = new Lazy<byte[]> (() => NpaOpener.GenerateKeyTable (scheme));
}
```

### GameRes.Formats.NitroPlus.EncryptionScheme

#### 状态与常量

```csharp
public NpaVariant   TitleId ;

public uint         NameKey ;

public byte[]       Order ;
```

#### EncryptionScheme

```csharp
public EncryptionScheme (NpaVariant id, uint key, byte[] order) {
    TitleId = id;
    NameKey = key;
    Order = order;
}
```

### GameRes.Formats.NitroPlus.NpaOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public bool CompressContents { get; set; }

public int              Key1 { get; set; }

public int              Key2 { get; set; }
```

### GameRes.Formats.NitroPlus.NpaOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public const int DefaultKey1 = 0x4147414e ;

public const int DefaultKey2 = 0x21214f54 ;

static readonly byte[] BaseTable = {
    0x6F,0x05,0x6A,0xBF,0xA1,0xC7,0x8E,0xFB,0xD4,0x2F,0x80,0x58,0x4A,0x17,0x3B,0xB1,
    0x89,0xEC,0xA0,0x9F,0xD3,0xFC,0xC2,0x04,0x68,0x03,0xF3,0x25,0xBE,0x24,0xF1,0xBD,
    0xB8,0x41,0xC9,0x27,0x0E,0xA3,0xD8,0x7F,0x5B,0x8F,0x16,0x49,0xAA,0xB2,0x18,0xA7,
    0x33,0xE4,0xDB,0x48,0xCA,0xDE,0xAE,0xCD,0x13,0x1F,0x15,0x2E,0x39,0xF5,0x1E,0xDD,
    0x0F,0x88,0x4C,0x98,0x36,0xB4,0x3F,0x09,0x83,0xFD,0x32,0xBA,0x14,0x30,0x7A,0x63,
    0xB9,0x56,0x95,0x61,0xCC,0x8B,0xEF,0xDA,0xE5,0x2C,0xDC,0x12,0x1A,0x67,0x23,0x50,
    0xD1,0xC3,0x7E,0x6D,0xB6,0x90,0x3C,0xB3,0x0B,0xE2,0x91,0x70,0xA8,0xDF,0x44,0xC4,
    0xF4,0x01,0x5C,0x10,0x06,0xE7,0x54,0x40,0x43,0x72,0x38,0xBC,0xE3,0x07,0xFA,0x34,
    0x02,0xA4,0xF7,0x74,0xA9,0x4D,0x42,0xA5,0x85,0x35,0x79,0xD2,0x76,0x97,0x45,0x4F,
    0x08,0x5A,0xB0,0xEE,0x51,0x73,0x69,0x9E,0x94,0x47,0x77,0x29,0xD9,0x64,0x11,0xEB,
    0x37,0xAC,0x20,0x62,0x9A,0x6B,0x9C,0x75,0x22,0x87,0xAB,0x78,0x53,0xC8,0x5D,0xAD,
    0x2A,0xF2,0xCB,0xB7,0x0D,0xED,0x86,0x55,0xFF,0x19,0x57,0xD7,0xD5,0x60,0xC6,0x3D,
    0xEA,0xC1,0x6C,0xE1,0xC0,0x65,0x84,0xC5,0xE0,0x3E,0x7D,0x28,0x66,0xAF,0x1C,0x9B,
    0xCF,0x81,0x4E,0x26,0x59,0x2B,0x5F,0x7B,0xE8,0x8D,0x52,0x7C,0xF8,0x82,0x0C,0xF9,
    0x8C,0xE9,0xB5,0xE6,0x31,0x93,0x46,0x5E,0x1D,0x1B,0x4B,0x71,0xD6,0x92,0x3A,0xA6,
    0x2D,0x00,0x9D,0xBB,0x6E,0xF0,0x99,0xCE,0x21,0x0A,0xD0,0xF6,0xFE,0xA2,0x8A,0x96,
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int key1 = file.View.ReadInt32 (7);
    int key2 = file.View.ReadInt32 (11);
    bool compressed = 0 != file.View.ReadByte (15);
    bool encrypted  = 0 != file.View.ReadByte (16);
    int total_count = file.View.ReadInt32 (17);
    int folder_count = file.View.ReadInt32 (21);
    int file_count = file.View.ReadInt32 (25);
    if (total_count < folder_count + file_count)
        return null;
    uint dir_size = file.View.ReadUInt32 (37);
    if (dir_size >= file.MaxOffset)
        return null;

    EncryptionScheme enc = null;
    var game_id = NpaVariant.General;
    if (encrypted)
    {
        enc = QueryGameEncryption (file.Name);
        if (null == enc)
            throw new OperationCanceledException (garStrings.MsgUnknownEncryption);
        game_id = enc.TitleId;
    }

    int key = GetArchiveKey (game_id, key1, key2);

    long cur_offset = 41;
    var dir = new List<Entry> (file_count);
    for (int i = 0; i < total_count; ++i)
    {
        int name_size = file.View.ReadInt32 (cur_offset);
        if ((uint)name_size >= dir_size)
            return null;
        int type = file.View.ReadByte (cur_offset+4+name_size);
        if (1 != type)
        {
            var raw_name = new byte[name_size];
            file.View.Read (cur_offset+4, raw_name, 0, (uint)name_size);
            for (int x = 0; x < name_size; ++x)
                raw_name[x] += DecryptName (x, i, key);
            var info_offset = cur_offset + 5 + name_size;

            int  id = file.View.ReadInt32 (info_offset);
            uint offset = file.View.ReadUInt32 (info_offset+4);
            uint size = file.View.ReadUInt32 (info_offset+8);
            uint unpacked_size = file.View.ReadUInt32 (info_offset+12);

            var entry = new NpaEntry {
                Name        = Encodings.cp932.GetString (raw_name),
                Offset      = dir_size+offset+41,
                Size        = size,
                UnpackedSize = unpacked_size,
                RawName     = raw_name,
                FolderId    = id,
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
            entry.IsPacked = compressed && entry.Type != "image";
            dir.Add (entry);
        }
        cur_offset += 4 + name_size + 17;
    }
    if (enc != null)
        return new NpaArchive (file, this, dir, enc, key);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input;
    if (arc is NpaArchive && entry is NpaEntry)
        input = new EncryptedStream (arc as NpaArchive, entry as NpaEntry);
    else
        input = arc.File.CreateStream (entry.Offset, entry.Size);
    return UnpackEntry (input, entry as PackedEntry);
}
```

#### UnpackEntry

```csharp
private Stream UnpackEntry (Stream input, PackedEntry entry) {
    if (null != entry && entry.IsPacked)
        return new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

#### DecryptName

```csharp
internal static byte DecryptName (int index, int curfile, int arc_key) {
    int key = 0xFC*index;

    key -= arc_key >> 0x18;
    key -= arc_key >> 0x10;
    key -= arc_key >> 0x08;
    key -= arc_key  & 0xff;

    key -= curfile >> 0x18;
    key -= curfile >> 0x10;
    key -= curfile >> 0x08;
    key -= curfile;

    return (byte)(key & 0xff);
}
```

#### GetArchiveKey

```csharp
internal static int GetArchiveKey (NpaVariant game_id, int key1, int key2) {
    if (NpaVariant.LAMENTO == game_id)
        return key1 + key2;
    else
        return key1 * key2;
}
```

#### GetKeyFromEntry

```csharp
internal static byte GetKeyFromEntry (NpaEntry entry, EncryptionScheme scheme, int arc_key) {
    int key = (int)scheme.NameKey;
    var name = entry.RawName;
    for (int i = 0; i < name.Length; ++i)
        key -= name[i];

    key *= name.Length;

    if (scheme.TitleId != NpaVariant.LAMENTO)
    {
        key += arc_key;
        key *= (int)entry.UnpackedSize;
    }
    return (byte)key;
}
```

#### GenerateKeyTable

```csharp
public static byte[] GenerateKeyTable (EncryptionScheme scheme) {
    byte[] order = scheme.Order;
    if (null == order)
        throw new ArgumentException ("Encryption key table not defined", "title_id");

    var table = new byte[256];
    for (int i = 0; i < 256; ++i)
    {
        int edx = i << 4;
        int dl = (edx + order[i & 0x0f]) & 0xff;
        int dh = (edx + (order[i>>4] << 8)) & 0xff00;
        edx = (dh | dl) >> 4;
        var eax = BaseTable[i];
        table[eax] = (byte)(edx & 0xff);
    }
    for (int i = 17; i < order.Length; i+=2)
    {
        int ecx = order[i-1];
        int edx = order[i];
        byte tmp = table[ecx];
        table[ecx] = table[edx];
        table[edx] = tmp;
    }
    if (NpaVariant.TOTONO == scheme.TitleId)
    {
        var totono_table = new byte[256];
        for (int i = 0; i < 256; ++i)
        {
            byte r = table[i];
            r = table[r];
            r = table[r];
            totono_table[i] = (byte)~r;
        }
        table = totono_table;
    }
    return table;
}
```

#### QueryGameEncryption

```csharp
EncryptionScheme QueryGameEncryption (string arc_name) {
    EncryptionScheme scheme = null;
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title))
        scheme = GetScheme (title);
    if (null == scheme)
    {
        var options = Query<NpaOptions> (arcStrings.ArcEncryptedNotice);
        scheme = options.Scheme;
    }
    return scheme;
}
```

#### GetTitleId

```csharp
public static NpaVariant GetTitleId (string title) {
    var scheme = GetScheme (title);
    return scheme != null ? scheme.TitleId : NpaVariant.General;
}
```

#### GetScheme

```csharp
public static EncryptionScheme GetScheme (string title) {
    EncryptionScheme scheme;
    if (KnownSchemes.TryGetValue (title, out scheme))
        return scheme;
    else
        return null;
}
```

### GameRes.Formats.NitroPlus.EncryptedStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
private Stream          m_stream ;

private Lazy<byte[]>    m_encrypted ;

private int             m_encrypted_length ;

private bool            m_read_mode ;

private long            m_base_pos ;

public override bool  CanRead { get { return m_read_mode && m_stream.CanRead; } }

public override bool  CanSeek { get { return m_stream.CanSeek; } }

public override long   Length { get { return m_stream.Length - m_base_pos; } }

public override long Position {
    get { return m_stream.Position - m_base_pos; }
    set { m_stream.Position = m_base_pos + value; }
}

CryptFunc Encrypt ;

bool disposed = false ;
```

#### CryptFunc

```csharp
delegate byte CryptFunc (int index, byte value) ;
```

#### EncryptedStream

```csharp
public EncryptedStream (NpaArchive arc, NpaEntry entry) {
    m_read_mode = true;
    m_encrypted_length = GetEncryptedLength (entry, arc.Scheme.TitleId);
    if (m_encrypted_length > entry.Size)
        m_encrypted_length = (int)entry.Size;
    int key = NpaOpener.GetKeyFromEntry (entry, arc.Scheme, arc.Key);

    m_stream = arc.File.CreateStream (entry.Offset, entry.Size);
    m_encrypted = new Lazy<byte[]> (() => InitEncrypted (key, arc.Scheme.TitleId, arc.KeyTable));
    m_base_pos = m_stream.Position;
}
```

#### EncryptedStream

```csharp
public EncryptedStream (Stream output, NpaEntry entry, EncryptionScheme scheme, int arc_key) {
    m_read_mode = false;
    m_encrypted_length = GetEncryptedLength (entry, scheme.TitleId);
    int key = NpaOpener.GetKeyFromEntry (entry, scheme, arc_key);

    m_stream = output;
    m_encrypted = new Lazy<byte[]> (() => new byte[m_encrypted_length]);
    m_base_pos = m_stream.Position;

    byte[] decrypt_table = NpaOpener.GenerateKeyTable (scheme);
    byte[] encrypt_table = new byte[256];
    for (int i = 0; i < 256; ++i)
        encrypt_table[decrypt_table[i]] = (byte)i;

    if (NpaVariant.LAMENTO == scheme.TitleId)
    {
        Encrypt = (i, x) => encrypt_table[(x + key) & 0xff];
    }
    else
    {
        Encrypt = (i, x) => encrypt_table[(x + key + i) & 0xff];
    }
}
```

#### GetEncryptedLength

```csharp
int GetEncryptedLength (NpaEntry entry, NpaVariant game_id) {
    int length = 0x1000;
    if (game_id != NpaVariant.LAMENTO)
        length += entry.RawName.Length;
    return length;
}
```

#### InitEncrypted

```csharp
byte[] InitEncrypted (int key, NpaVariant game_id, byte[] key_table) {
    var position = Position;
    if (0 != position)
        Position = 0;
    byte[] buffer = new byte[m_encrypted_length];
    m_encrypted_length = m_stream.Read (buffer, 0, m_encrypted_length);
    Position = position;

    if (game_id == NpaVariant.LAMENTO)
    {
        for (int i = 0; i < m_encrypted_length; i++)
            buffer[i] = (byte)(key_table[buffer[i]] - key);
    }
    else
    {
        for (int i = 0; i < m_encrypted_length; i++)
            buffer[i] = (byte)(key_table[buffer[i]] - key - i);
    }
    return buffer;
}
```

#### Flush

```csharp
public override void Flush() {
    m_stream.Flush();
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    if (SeekOrigin.Begin == origin)
        offset += m_base_pos;
    offset = m_stream.Seek (offset, origin);
    return offset - m_base_pos;
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("EncryptedStream.SetLength is not supported");
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    var position = Position;
    if (position >= m_encrypted_length)
        return m_stream.Read (buffer, offset, count);
    int read = Math.Min (m_encrypted_length - (int)position, count);
    Buffer.BlockCopy (m_encrypted.Value, (int)position, buffer, offset, read);
    m_stream.Seek (read, SeekOrigin.Current);
    if (read < count)
    {
        read += m_stream.Read (buffer, offset+read, count-read);
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    var position = Position;
    if (position >= m_encrypted_length)
        return m_stream.ReadByte();
    m_stream.Seek (1, SeekOrigin.Current);
    return m_encrypted.Value[(int)position];
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    var position = Position;
    if (position < m_encrypted_length)
        value = Encrypt ((int)position, value);
    m_stream.WriteByte (value);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NitroPlus/ArcNPA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
