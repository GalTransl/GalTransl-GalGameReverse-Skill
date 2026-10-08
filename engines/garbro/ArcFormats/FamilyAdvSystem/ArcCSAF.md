# FamilyAdvSystem / ArcCSAF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CSAF` / `GameRes.Formats.FamilyAdvSystem.CsafOpener` | `` | `43534146` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CsafOpener.TryOpen` | `uint flags = file.View.ReadUInt32 (4);` |
| `CsafOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `CsafOpener.TryOpen` | `uint names_size = file.View.ReadUInt32 (12);` |
| `CsafOpener.TryOpen` | `var arc_md5 = file.View.ReadBytes (0x10, 0x10);` |
| `CsafOpener.TryOpen` | `entry.Offset = (long)index.ToUInt32 (index_pos) << 12;` |
| `CsafOpener.TryOpen` | `entry.Size = index.ToUInt32 (index_pos+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FamilyAdvSystem.CsafOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly string DefaultKey = "江ノ島の南" ;

static readonly byte[] DefaultIV = Encoding.ASCII.GetBytes ("FamilyAdvSystem ") ;

FamilyAdvScheme DefaultScheme = new FamilyAdvScheme { KnownKeys = new Dictionary<string, string>() }
```

#### CsafOpener

```csharp
public CsafOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint flags = file.View.ReadUInt32 (4);
    if ((flags & 0x7FFFFFFF) != 0x10000)
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    bool is_encrypted = (flags >> 31) != 0;
    uint index_size = (uint)((count * 24 + 31) & -4096) + 0xFE0u;
    uint names_size = file.View.ReadUInt32 (12);
    var arc_md5 = file.View.ReadBytes (0x10, 0x10);
    var index = new byte[index_size + names_size];
    CsafEncryption enc = null;
    try
    {
        if (is_encrypted)
        {
            var key = QueryEncryptionKey (file);
            file.View.Read (0x20, index, 0, index_size);
            enc = new CsafEncryption (key, DefaultIV);
            using (var decryptor = enc.CreateDecryptor (0))
            using (var enc_names = file.CreateStream (0x20 + index_size, names_size))
            using (var dec_names = new InputCryptoStream (enc_names, decryptor))
            {
                dec_names.Read (index, (int)index_size, (int)names_size);
            }
        }
        else
        {
            file.View.Read (0x20, index, 0, index_size + names_size);
        }
        using (var md5 = MD5.Create())
        {
            var hash = md5.ComputeHash (index);
            if (!hash.SequenceEqual (arc_md5))
                return null;
            int index_pos = 0x10;
            int name_pos = (int)index_size;
            var dir = new List<Entry> (count);
            for (int i = 0; i < count; ++i)
            {
                int j;
                for (j = name_pos; j+1 < index.Length; j += 2)
                {
                    if (index[j] == 0 && index[j+1] == 0)
                        break;
                }
                int name_length = j - name_pos;
                var name = Encoding.Unicode.GetString (index, name_pos, name_length);

                name_pos += name_length + 10;

                var entry = Create<Entry> (name);
                entry.Offset = (long)index.ToUInt32 (index_pos) << 12;
                entry.Size = index.ToUInt32 (index_pos+4);
                index_pos += 0x18;
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                dir.Add (entry);
            }
            if (!is_encrypted)
                return new ArcFile (file, this, dir);
            var arc = new CsafArchive (file, this, dir, enc);
            enc = null;
            return arc;
        }
    }
    finally
    {
        if (enc != null)
            enc.Dispose();
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var carc = arc as CsafArchive;
    if (null == carc)
        return base.OpenEntry (arc, entry);
    var input = new CsafStream (carc);
    return new StreamRegion (input, entry.Offset, entry.Size);
}
```

#### QueryEncryptionKey

```csharp
internal string QueryEncryptionKey (ArcView file) {
    var title = FormatCatalog.Instance.LookupGame (file.Name);
    if (string.IsNullOrEmpty (title))
        return DefaultKey;
    string key;
    if (!KnownKeys.TryGetValue (title, out key))
        return DefaultKey;
    return key;
}
```

### GameRes.Formats.FamilyAdvSystem.CsafEncryption

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
Aes     m_aes ;

MD5     m_md5 ;

byte[]  m_key ;

byte[]  m_iv ;

bool m_disposed = false ;
```

#### CsafEncryption

```csharp
public CsafEncryption (string password, byte[] iv) {
    m_md5 = MD5.Create();
    m_aes = Aes.Create();
    m_aes.Mode = CipherMode.CBC;
    m_aes.Padding = PaddingMode.None;
    m_key = InitKey (password);
    m_iv = iv;
}
```

#### CreateDecryptor

```csharp
public ICryptoTransform CreateDecryptor (int block_num) {
    var block_key = GetBlockKey (block_num);
    return m_aes.CreateDecryptor (block_key, m_iv);
}
```

#### InitKey

```csharp
byte[] InitKey (string pass_phrase) {
    var key = new byte[32];
    if (!string.IsNullOrEmpty (pass_phrase))
    {
        var bytes = Encoding.Unicode.GetBytes (pass_phrase);
        var hash = m_md5.ComputeHash (bytes);
        Buffer.BlockCopy (hash, 0, key, 0, 16);
        hash = m_md5.ComputeHash (bytes, 1, bytes.Length - 2);
        Buffer.BlockCopy (hash, 0, key, 16, 16);
    }
    return key;
}
```

#### GetBlockKey

```csharp
byte[] GetBlockKey (int block_num) {
    int offset = block_num / 8;
    int shift = block_num & 7;
    var key = new byte[32];
    var buf = new byte[16];
    for (int i = 0; i < 16; ++i)
    {
        buf[i] = Binary.RotByteL (m_key[(offset + i) & 0xF], shift);
    }
    var hash = m_md5.ComputeHash (buf, 0, 16);
    Buffer.BlockCopy (hash, 0, key, 0, 16);
    for (int i = 0; i < 16; ++i)
    {
        buf[i] = Binary.RotByteL (m_key[16 + ((offset + i) & 0xF)], shift);
    }
    hash = m_md5.ComputeHash (buf, 0, 16);
    Buffer.BlockCopy (hash, 0, key, 16, 16);
    return key;
}
```

### GameRes.Formats.FamilyAdvSystem.CsafArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly CsafEncryption  Encryption ;

bool _csaf_disposed = false ;
```

#### CsafArchive

```csharp
public CsafArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, CsafEncryption enc)
    : base (arc, impl, dir) {
    Encryption = enc;
}
```

### GameRes.Formats.FamilyAdvSystem.CsafStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
readonly long   m_length ;

ArcView.Frame   m_view ;

CsafEncryption  m_encryption ;

long            m_position = 0 ;

byte[]          m_block = new byte[0x1000] ;

long            m_block_start = 0 ;

int             m_block_length = 0 ;

public override bool CanRead { get { return true; } }

public override bool CanSeek { get { return true; } }

public override long Length { get { return m_length; } }

public override long Position {
    get { return m_position; }
    set { m_position = value; }
}

bool _disposed = false ;
```

#### CsafStream

```csharp
public CsafStream (CsafArchive arc) {
    m_length = arc.File.MaxOffset;
    m_view = arc.File.CreateFrame();
    m_encryption = arc.Encryption;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int read = 0;
    while (count > 0)
    {
        if (!(m_position >= m_block_start && m_position < m_block_start + m_block_length))
        {
            if (!ReadBlock())
                break;
        }
        int block_pos = (int)m_position & 0xFFF;
        int avail = Math.Min (count, m_block_length - block_pos);
        Buffer.BlockCopy (m_block, block_pos, buffer, offset, avail);
        m_position += avail;
        offset += avail;
        read += avail;
        count -= avail;
    }
    return read;
}
```

#### ReadBlock

```csharp
bool ReadBlock () {
    if (m_position >= m_length)
        return false;
    m_block_start = m_position & ~0xFFFL;
    m_block_length = m_view.Read (m_block_start, m_block, 0, 0x1000);
    if (m_block_length != 0x1000)
        return false;
    using (var decryptor = m_encryption.CreateDecryptor ((int)(m_block_start >> 12)))
    using (var enc = new BinMemoryStream (m_block))
    using (var dec = new InputCryptoStream (enc, decryptor))
        dec.Read (m_block, 0, m_block_length);
    return true;
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    if (SeekOrigin.Begin == origin)
        Position = offset;
    else if (SeekOrigin.Current == origin)
        Position = m_position + offset;
    else
        Position = m_length + offset;

    return m_position;
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("CsafStream.SetLength method is not supported");
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    throw new NotSupportedException("CsafStream.WriteByte method is not supported");
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/FamilyAdvSystem/ArcCSAF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
