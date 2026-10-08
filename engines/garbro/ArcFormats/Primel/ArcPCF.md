# Primel / ArcPCF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCF` / `GameRes.Formats.Primel.PcfOpener` | `pcf` | `5061636b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PcfOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "Code"))` |
| `PcfOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `PcfIndexReader.Read` | `long data_size = m_file.View.ReadInt64 (0x10);` |
| `PcfIndexReader.Read` | `long index_offset = m_file.View.ReadInt64 (0x28);` |
| `PcfIndexReader.Read` | `uint index_size = m_file.View.ReadUInt32 (0x30);` |
| `PcfIndexReader.Read` | `uint flags = m_file.View.ReadUInt32 (0x38);` |
| `PcfIndexReader.Read` | `var key = m_file.View.ReadBytes (0x58, 8);` |
| `PcfIndexReader.ReadIndex` | `entry.Offset = LittleEndian.ToInt64 (m_buffer, 0x50) + m_base_offset;` |
| `PcfIndexReader.ReadIndex` | `entry.UnpackedSize = LittleEndian.ToUInt32 (m_buffer, 0x58);` |
| `PcfIndexReader.ReadIndex` | `entry.Size   = LittleEndian.ToUInt32 (m_buffer, 0x60);` |
| `PcfIndexReader.ReadIndex` | `entry.Flags  = LittleEndian.ToUInt32 (m_buffer, 0x68);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Primel.PcfEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint     Flags ;

public byte[]   Key ;
```

### GameRes.Formats.Primel.PcfArchive

继承/接口：`ArcFile`。

#### PcfArchive

```csharp
public PcfArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, PrimelScheme scheme)
    : base (arc, impl, dir) {
    Scheme = scheme;
}
```

### GameRes.Formats.Primel.PcfOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "Code"))
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    var reader = new PcfIndexReader (file, count);
    var dir = reader.Read();
    if (null == dir)
        return null;
    return new PcfArchive (file, this, dir, reader.Scheme);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = arc as PcfArchive;
    var pent = entry as PcfEntry;
    if (null == pent || null == parc)
        return base.OpenEntry (arc, entry);
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    try
    {
        input = parc.Scheme.TransformStream (input, pent.Key, pent.Flags);
        if (pent.IsPacked)
            input = new LimitStream (input, pent.UnpackedSize);
        return input;
    }
    catch
    {
        input.Dispose();
        throw;
    }
}
```

### GameRes.Formats.Primel.PcfIndexReader

#### 状态与常量

```csharp
ArcView         m_file ;

int             m_count ;

long            m_base_offset ;

List<Entry>     m_dir ;

static readonly PrimelScheme[] KnownSchemes = {
    new PrimelScheme(), new PrimelSchemeV2()
}

byte[] m_buffer = new byte[0x80] ;
```

#### PcfIndexReader

```csharp
public PcfIndexReader (ArcView file, int count) {
    m_file = file;
    m_count = count;
    m_dir = new List<Entry> (m_count);
}
```

#### Read

```csharp
public List<Entry> Read () {
    long data_size = m_file.View.ReadInt64 (0x10);
    long index_offset = m_file.View.ReadInt64 (0x28);
    if (data_size >= m_file.MaxOffset || index_offset >= m_file.MaxOffset)
        return null;
    uint index_size = m_file.View.ReadUInt32 (0x30);
    uint flags = m_file.View.ReadUInt32 (0x38);
    var key = m_file.View.ReadBytes (0x58, 8);
    m_base_offset = m_file.MaxOffset - data_size;
    foreach (var scheme in KnownSchemes)
    {
        m_dir.Clear();
        try
        {
            using (var stream = m_file.CreateStream (m_base_offset + index_offset, index_size))
            using (var index = scheme.TransformStream (stream, key, flags))
            {
                if (ReadIndex (index))
                {
                    this.Scheme = scheme;
                    return m_dir;
                }
            }
        }
        catch {  }
    }
    return null;
}
```

#### ReadIndex

```csharp
bool ReadIndex (Stream index) {
    for (int i = 0; i < m_count; ++i)
    {
        if (m_buffer.Length != index.Read (m_buffer, 0, m_buffer.Length))
            break;
        var name = Binary.GetCString (m_buffer, 0, 0x50);
        var entry = FormatCatalog.Instance.Create<PcfEntry> (name);
        entry.Offset = LittleEndian.ToInt64 (m_buffer, 0x50) + m_base_offset;
        entry.UnpackedSize = LittleEndian.ToUInt32 (m_buffer, 0x58);
        entry.Size   = LittleEndian.ToUInt32 (m_buffer, 0x60);
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return false;
        entry.Flags  = LittleEndian.ToUInt32 (m_buffer, 0x68);
        entry.Key    = new ArraySegment<byte> (m_buffer, 0x78, 8).ToArray();
        entry.IsPacked = entry.UnpackedSize != entry.Size;
        m_dir.Add (entry);
    }
    return m_dir.Count > 0;
}
```

### GameRes.Formats.Primel.PrimelScheme

#### TransformStream

```csharp
public Stream TransformStream (Stream input, byte[] key, uint flags) {
    var key1 = GenerateKey (key);
    var iv   = GenerateKey (key1);

    ICryptoTransform decryptor;
    switch (flags & 0xF0000)
    {
    case 0x10000:
        decryptor = new Primel1Encryption (key1, iv);
        break;
    case 0x20000:
        decryptor = new Primel2Encryption (key1, iv);
        break;
    case 0x30000:
        decryptor = new Primel3Encryption (key1, iv);
        break;
    case 0x80000:
        decryptor = new GameRes.Cryptography.RC6 (key1, iv);
        break;

    case 0xA0000:
        using (var aes = Rijndael.Create())
        {
            aes.Mode = CipherMode.CFB;
            aes.Padding = PaddingMode.Zeros;
            decryptor = aes.CreateDecryptor (key1, iv);
        }
        break;

    default:
        return input;
    }
    input = new InputCryptoStream (input, decryptor);
    try
    {
        if (0 != (flags & 0xFF))
        {
            input = new RangePackedStream (input);
        }
        switch (flags & 0xF00)
        {
        case 0x400:
            input = new RlePackedStream (input);
            input = new MtfPackedStream (input);
            break;
        case 0x700:
            input = new LzssPackedStream (input);
            break;
        }
        return input;
    }
    catch
    {
        input.Dispose();
        throw;
    }
}
```

#### GenerateKey

```csharp
byte[] GenerateKey (byte[] seed) {
    var hash = ComputeHash (seed);
    var key = new byte[0x10];
    for (int i = 0; i < hash.Length; ++i)
    {
        key[i & 0xF] ^= hash[i];
    }
    return key;
}
```

#### ComputeHash

```csharp
protected virtual byte[] ComputeHash (byte[] seed) {
    var sha = new Primel.SHA256();
    return sha.ComputeHash (seed);
}
```

### GameRes.Formats.Primel.PrimelSchemeV2

继承/接口：`PrimelScheme`。

#### ComputeHash

```csharp
protected override byte[] ComputeHash (byte[] seed) {
    using (var sha = System.Security.Cryptography.SHA256.Create())
        return sha.ComputeHash (seed);
}
```

## 配套算法与外部条件

- [ArcFormats/Primel/Compression.cs](Compression.md)：本页引用的随包算法资料。
- [ArcFormats/Primel/Encryption.cs](Encryption.md)：本页引用的随包算法资料。
- [ArcFormats/Primel/RC6.cs](RC6.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Primel/ArcPCF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
