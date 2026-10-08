# NScripter / ArcNSA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NSA` / `GameRes.Formats.NScripter.NsaOpener` | `nsa`, `dat` | 无固定签名或来源表达式未解析 | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NsaOpener.TryOpen` | `bool zero_signature = 0 == file.View.ReadInt16 (0);` |
| `NsaOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (0);` |
| `NsaOpener.ReadIndex` | `int count = Binary.BigEndian (input.ReadInt16());` |
| `NsaOpener.ReadIndex` | `base_offset += Binary.BigEndian (input.ReadUInt32());` |
| `NsaOpener.ReadIndex` | `var name = file.ReadCString();` |
| `NsaOpener.ReadIndex` | `byte compression_type = input.ReadByte();` |
| `NsaOpener.ReadIndex` | `entry.Offset = Binary.BigEndian (input.ReadUInt32()) + base_offset;` |
| `NsaOpener.ReadIndex` | `entry.Size   = Binary.BigEndian (input.ReadUInt32());` |
| `NsaOpener.ReadIndex` | `entry.UnpackedSize = Binary.BigEndian (input.ReadUInt32());` |
| `Unpacker.DecodeSPB` | `uint width   = (uint)Input.ReadByte() << 8;` |
| `Unpacker.DecodeSPB` | `width       \|= (uint)Input.ReadByte();` |
| `Unpacker.DecodeSPB` | `uint height  = (uint)Input.ReadByte() << 8;` |
| `Unpacker.DecodeSPB` | `height      \|= (uint)Input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum Compression
    {
        Unknown = 256,
        None    = 0,
        SPB     = 1,
        LZSS    = 2,
        NBZ     = 4,
    }
```

### GameRes.Formats.NScripter.NsaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public Compression CompressionType { get; set; }
```

### GameRes.Formats.NScripter.NsaEncryptedArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### NsaEncryptedArchive

```csharp
public NsaEncryptedArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.NScripter.NsaOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public Compression CompressionType { get; set; }

public string             Password { get; set; }
```

### GameRes.Formats.NScripter.NsaOpener

继承/接口：`SarOpener`。

#### NsaOpener

```csharp
public NsaOpener () {
    Extensions = new string[] { "nsa", "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    List<Entry> dir = null;
    bool zero_signature = 0 == file.View.ReadInt16 (0);
    try
    {
        using (var input = file.CreateStream())
        {
            if (zero_signature)
                input.Seek (2, SeekOrigin.Begin);
            dir = ReadIndex (input);
            if (null != dir)
                return new ArcFile (file, this, dir);
        }
    }
    catch {  }
    if (zero_signature || !file.Name.HasExtension (".nsa"))
        return null;
    uint signature = file.View.ReadUInt32 (0);
    if ((signature & 0xFFFFFF) == 0x90FBFF)
        return new WrapSingleFileArchive (file, Path.GetFileNameWithoutExtension (file.Name)+".mp3");

    var password = QueryPassword();
    if (string.IsNullOrEmpty (password))
        return null;
    var key = Encoding.ASCII.GetBytes (password);

    using (var input = new EncryptedViewStream (file, key))
    {
        dir = ReadIndex (input);
        if (null == dir)
            return null;
        return new NsaEncryptedArchive (file, this, dir, key);
    }
}
```

#### ReadIndex

```csharp
protected List<Entry> ReadIndex (Stream file) {
    long base_offset = file.Position;
    using (var input = new ArcView.Reader (file))
    {
        int count = Binary.BigEndian (input.ReadInt16());
        if (!IsSaneCount (count))
            return null;
        base_offset += Binary.BigEndian (input.ReadUInt32());
        if (base_offset >= file.Length || base_offset < 15 * count)
            return null;

        var dir = new List<Entry>();
        for (int i = 0; i < count; ++i)
        {
            if (base_offset - file.Position < 15)
                return null;
            var name = file.ReadCString();
            if (base_offset - file.Position < 13 || 0 == name.Length)
                return null;

            var entry = FormatCatalog.Instance.Create<NsaEntry> (name);
            byte compression_type = input.ReadByte();
            entry.Offset = Binary.BigEndian (input.ReadUInt32()) + base_offset;
            entry.Size   = Binary.BigEndian (input.ReadUInt32());
            if (!entry.CheckPlacement (file.Length))
                return null;
            entry.UnpackedSize = Binary.BigEndian (input.ReadUInt32());
            entry.IsPacked = compression_type != 0;
            switch (compression_type)
            {
            case 0:  entry.CompressionType = Compression.None; break;
            case 1:  entry.CompressionType = Compression.SPB; break;
            case 2:  entry.CompressionType = Compression.LZSS; break;
            case 4:  entry.CompressionType = Compression.NBZ; break;
            default: entry.CompressionType = Compression.Unknown; break;
            }
            if (name.HasExtension (".nbz"))
                entry.Type = "audio";
            dir.Add (entry);
        }
        return dir;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var nsa_arc = arc as NsaEncryptedArchive;
    if (null == nsa_arc)
    {
        var input = arc.File.CreateStream (entry.Offset, entry.Size);
        return UnpackEntry (input, entry as NsaEntry);
    }
    var encrypted = new EncryptedViewStream (arc.File, nsa_arc.Key);
    var stream = new StreamRegion (encrypted, entry.Offset, entry.Size);
    return UnpackEntry (stream, entry as NsaEntry);
}
```

#### UnpackEntry

```csharp
protected Stream UnpackEntry (Stream input, NsaEntry nsa_entry) {
    if (null == nsa_entry)
        return input;
    if (nsa_entry.Name.HasExtension (".nbz") || Compression.NBZ == nsa_entry.CompressionType)
    {
        input.Position = 4;
        return new BZip2InputStream (input);
    }
    if (!(Compression.LZSS == nsa_entry.CompressionType ||
          Compression.SPB  == nsa_entry.CompressionType))
        return input;
    using (input)
    {
        var decoder = new Unpacker (input, nsa_entry.UnpackedSize);
        if (Compression.SPB == nsa_entry.CompressionType)
            return decoder.SpbDecodedStream();
        else
            return decoder.LzssDecodedStream();
    }
}
```

#### QueryPassword

```csharp
private string QueryPassword () {
    var options = Query<NsaOptions> (arcStrings.ArcEncryptedNotice);
    return options.Password;
}
```

### GameRes.Formats.NScripter.LZSS

#### 状态与常量

```csharp
public const int EI = 8 ;

public const int EJ = 4 ;

public const int P  = 1 ;

public const int N  = (1 << EI) ;

public const int F  = ((1 << EJ) + P) ;
```

### GameRes.Formats.NScripter.Unpacker

继承/接口：`MsbBitStream`。

#### 状态与常量

```csharp
private byte[]          m_output ;

public byte[] Output { get { return m_output; } }
```

#### Unpacker

```csharp
public Unpacker (Stream input, uint unpacked_size) : base (input, true) {
    m_output = new byte[unpacked_size];
}
```

#### LzssDecodedStream

```csharp
public Stream LzssDecodedStream () {
    DecodeLZSS();
    return new MemoryStream (m_output);
}
```

#### SpbDecodedStream

```csharp
public Stream SpbDecodedStream () {
    DecodeSPB();
    return new MemoryStream (m_output);
}
```

#### DecodeLZSS

```csharp
uint DecodeLZSS () {
    uint count = 0;

    byte[] decomp_buffer = new byte[LZSS.N*2];
    int r = LZSS.N - LZSS.F;
    int c;
    while (count < m_output.Length)
    {
        if (0 != GetBits (1))
        {
            c = GetBits (8);
            if (-1 == c)
                break;
            m_output[count++] = (byte)c;
            decomp_buffer[r++] = (byte)c;
            r &= (LZSS.N - 1);
        }
        else
        {
            int i = GetBits (LZSS.EI);
            if (-1 == i)
                break;
            int j = GetBits (LZSS.EJ);
            if (-1 == j)
                break;
            for (int k = 0; k <= j + 1; k++)
            {
                c = decomp_buffer[(i + k) & (LZSS.N - 1)];
                m_output[count++] = (byte)c;
                decomp_buffer[r++] = (byte)c;
                r &= (LZSS.N - 1);
            }
        }
    }
    return count;
}
```

#### DecodeSPB

```csharp
uint DecodeSPB () {
    uint width   = (uint)Input.ReadByte() << 8;
    width       |= (uint)Input.ReadByte();
    uint height  = (uint)Input.ReadByte() << 8;
    height      |= (uint)Input.ReadByte();

    uint width_pad  = (4 - width * 3 % 4) % 4;
    int stride = (int)(width * 3 + width_pad);
    uint total_size = (uint)stride * height + 54;

    if ((uint)m_output.Length < total_size)
        m_output = new byte[total_size];

    m_output[0] = (byte)'B';
    m_output[1] = (byte)'M';
    LittleEndian.Pack (total_size, m_output, 2);
    m_output[10] = 54;
    m_output[14] = 40;
    LittleEndian.Pack (width,  m_output, 18);
    LittleEndian.Pack (height, m_output, 22);
    m_output[26] = 1;
    m_output[28] = 24;

    byte[] decomp_buffer = new byte[width*height*4];

    for (int i = 0; i < 3; i++)
    {
        uint count = 0;
        int c = GetBits (8);
        if (-1 == c)
            break;
        decomp_buffer[count++] = (byte)c;
        while (count < width * height)
        {
            int n = GetBits (3);
            if (0 == n)
            {
                decomp_buffer[count++] = (byte)c;
                decomp_buffer[count++] = (byte)c;
                decomp_buffer[count++] = (byte)c;
                decomp_buffer[count++] = (byte)c;
                continue;
            }
            int m;
            if (7 == n)
                m = GetBits (1) + 1;
            else
                m = n + 2;

            for (uint j = 0; j < 4; j++)
            {
                if (8 == m)
                {
                    c = GetBits (8);
                }
                else
                {
                    int k = GetBits (m);
                    if (0 != (k & 1))
                        c += (k>>1) + 1;
                    else
                        c -= (k>>1);
                }
                decomp_buffer[count++] = (byte)c;
            }
        }

        int pbuf  = stride * (int)(height-1) + i + 54;
        int psbuf = 0;

        for (uint j = 0; j < height; j++)
        {
            if (0 != (j & 1))
            {
                for (uint k = 0; k < width; k++, pbuf -= 3)
                    m_output[pbuf] = decomp_buffer[psbuf++];
                pbuf -= stride - 3;
            }
            else
            {
                for (uint k = 0; k < width; k++, pbuf += 3)
                    m_output[pbuf] = decomp_buffer[psbuf++];
                pbuf -= stride + 3;
            }
        }
    }
    return total_size;
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/NScripter/ArcSAR.cs](ArcSAR.md)：本页引用的随包算法资料。
- [ArcFormats/NScripter/EncryptedStream.cs](EncryptedStream.md)：本页引用的随包算法资料。
- [ArcFormats/SingleFileArchive.cs](../SingleFileArchive.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/NScripter/ArcNSA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
