# ShiinaRio / ArcWARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WAR` / `GameRes.Formats.ShiinaRio.WarOpener` | `war` | `57415243` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WarOpener.TryOpen` | `if (!file.View.AsciiEqual (4, " 1."))` |
| `WarOpener.TryOpen` | `int version = file.View.ReadByte (7) - 0x30;` |
| `WarOpener.TryOpen` | `uint index_offset = 0xF182AD82u ^ file.View.ReadUInt32 (8);` |
| `WarOpener.TryOpen` | `entry.Offset       = header.ReadUInt32();` |
| `WarOpener.TryOpen` | `entry.Size         = header.ReadUInt32();` |
| `WarOpener.TryOpen` | `entry.UnpackedSize = header.ReadUInt32();` |
| `WarOpener.TryOpen` | `entry.FileTime     = header.ReadInt64();` |
| `WarOpener.TryOpen` | `entry.Flags        = header.ReadUInt32();` |
| `WarOpener.OpenEntry` | `var enc_data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `WarOpener.OpenEntry` | `uint sig = LittleEndian.ToUInt32 (enc_data, 0);` |
| `WarOpener.OpenEntry` | `uint unpacked_size = LittleEndian.ToUInt32 (enc_data, 4);` |
| `YlzReader.GetCtlBit` | `m_ctl = LittleEndian.ToUInt32 (m_input, m_src);` |
| `HuffmanReader.ReadUInt32` | `uint ReadUInt32 () {` |
| `HuffmanReader.ReadUInt32` | `v = LittleEndian.ToUInt32 (m_src, m_input_pos);` |
| `HuffmanReader.GetBits` | `m_cache = ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ShiinaRio.WarcEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public long FileTime ;

public uint Flags ;
```

### GameRes.Formats.ShiinaRio.WarcFile

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Decoder Decoder ;
```

#### WarcFile

```csharp
public WarcFile (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Decoder decoder)
    : base (arc, impl, dir) {
    this.Decoder = decoder;
}
```

### GameRes.Formats.ShiinaRio.WarOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, " 1."))
        return null;
    int version = file.View.ReadByte (7) - 0x30;
    if (version < 1 || version > 7)
        return null;
    version = 100 + version * 10;
    uint index_offset = 0xF182AD82u ^ file.View.ReadUInt32 (8);
    if (index_offset >= file.MaxOffset)
        return null;

    EncryptionScheme scheme;
    if (version > 110)
        scheme = QueryEncryption (file.Name);
    else
        scheme = EncryptionScheme.Warc110;
    if (null == scheme)
        return null;
    var decoder = new Decoder (version, scheme);

    uint max_index_len = decoder.MaxIndexLength;
    uint index_length = (uint)Math.Min (max_index_len, file.MaxOffset - index_offset);
    if (index_length < 8)
        return null;
    var enc_index = new byte[max_index_len];
    if (index_length != file.View.Read (index_offset, enc_index, 0, index_length))
        return null;
    decoder.DecryptIndex (index_offset, enc_index);
    Stream index;
    if (version >= 170)
    {
        if (0x78 != enc_index[8])
            return null;
        var zindex = new MemoryStream (enc_index, 8, (int)index_length-8);
        index = new ZLibStream (zindex, CompressionMode.Decompress);
    }
    else if (version >= 120)
    {
        var unpacked = new byte[max_index_len];
        index_length = UnpackRNG (enc_index, 0, index_length, unpacked);
        if (0 == index_length)
            return null;
        index = new MemoryStream (unpacked, 0, (int)index_length);
    }
    else
    {
        index = new MemoryStream (enc_index, 0, (int)index_length);
    }
    using (var header = new BinaryReader (index))
    {
        byte[] name_buf = new byte[decoder.EntryNameSize];
        var dir = new List<Entry> ();
        var unique_names = new HashSet<string>();
        while (name_buf.Length == header.Read (name_buf, 0, name_buf.Length))
        {
            var name = Binary.GetCString (name_buf, 0, name_buf.Length);
            var entry = FormatCatalog.Instance.Create<WarcEntry> (name);
            entry.Offset       = header.ReadUInt32();
            entry.Size         = header.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.UnpackedSize = header.ReadUInt32();
            entry.IsPacked     = entry.Size != entry.UnpackedSize;
            entry.FileTime     = header.ReadInt64();
            entry.Flags        = header.ReadUInt32();
            if (0 != name.Length && name_buf[0] < 0x80 && unique_names.Add (name))
                dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        return new WarcFile (file, this, dir, decoder);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var warc = arc as WarcFile;
    var wentry = entry as WarcEntry;
    if (null == warc || null == wentry || entry.Size < 8)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var enc_data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (enc_data.Length <= 8)
        return new BinMemoryStream (enc_data, entry.Name);
    uint sig = LittleEndian.ToUInt32 (enc_data, 0);
    uint unpacked_size = LittleEndian.ToUInt32 (enc_data, 4);
    if (warc.Decoder.WarcVersion > 110)
    {
        sig ^= (unpacked_size ^ 0x82AD82) & 0xFFFFFF;
        if (0 != (wentry.Flags & 0x80000000u))
            warc.Decoder.Decrypt (enc_data, 8, entry.Size-8);
        if (warc.Decoder.ExtraCrypt != null)
            warc.Decoder.ExtraCrypt.Decrypt (enc_data, 8, entry.Size-8, 0x202);
        if (0 != (wentry.Flags & 0x20000000u))
            warc.Decoder.Decrypt2 (enc_data, 8, entry.Size-8);
    }
    byte[] unpacked = enc_data;
    UnpackMethod unpack = null;
    switch (sig & 0xffffff)
    {
    case 0x314859:
        unpack = UnpackYH1;
        break;
    case 0x4b5059:
        unpack = UnpackYPK;
        break;
    case 0x5a4c59:
        unpack = UnpackYLZ;
        break;
    }
    if (null != unpack)
    {
        unpacked = new byte[unpacked_size];
        unpack (enc_data, unpacked);
        if (warc.Decoder.WarcVersion > 110)
        {
            if (0 != (wentry.Flags & 0x40000000))
                warc.Decoder.Decrypt2 (unpacked, 0, (uint)unpacked.Length);
            if (warc.Decoder.ExtraCrypt != null)
                warc.Decoder.ExtraCrypt.Decrypt (unpacked, 0, (uint)unpacked.Length, 0x204);
        }
    }
    return new BinMemoryStream (unpacked, entry.Name);
}
```

#### UnpackMethod

```csharp
delegate void UnpackMethod (byte[] input, byte[] output) ;
```

#### UnpackYH1

```csharp
void UnpackYH1 (byte[] input, byte[] output) {
    if (0 != input[3])
    {
        uint key = 0x6393528e^0x4b4du;
        unsafe
        {
            fixed (byte* buf_raw = input)
            {
                uint* encoded = (uint*)buf_raw;
                int i;
                for (i = 2; i < input.Length/4; ++i)
                    encoded[i] ^= key;
            }
        }
    }
    var decoder = new HuffmanReader (input, 8, input.Length-8, output);
    decoder.Unpack();
}
```

#### UnpackYPK

```csharp
void UnpackYPK (byte[] input, byte[] output) {
    if (0 != input[3])
    {
        uint key = ~0x4b4d4b4du;
        unsafe
        {
            fixed (byte* buf_raw = input)
            {
                uint* encoded = (uint*)buf_raw;
                int i;
                for (i = 2; i < input.Length/4; ++i)
                    encoded[i] ^= key;
                for (i *= 4; i < input.Length; ++i)
                    buf_raw[i] ^= (byte)key;
            }
        }
    }
    if (0x78 != input[8])
        throw new ApplicationException ("Invalid decryption scheme");
    var src = new MemoryStream (input, 8, input.Length-8);
    using (var zlib = new ZLibStream (src, CompressionMode.Decompress))
        zlib.Read (output, 0, output.Length);
}
```

#### UnpackYLZ

```csharp
void UnpackYLZ (byte[] input, byte[] output) {
    if (0 != input[3])
    {
        uint key = 0x4b4d4b4du;
        unsafe
        {
            fixed (byte* buf_raw = input)
            {
                uint* encoded = (uint*)buf_raw;
                int i;
                for (i = 2; i < input.Length/4; ++i)
                    encoded[i] ^= key;
                for (i *= 4; i < input.Length; ++i)
                {
                    buf_raw[i] ^= (byte)key;
                    key >>= 8;
                }
            }
        }
    }
    var decoder = new YlzReader (input, 8, output);
    decoder.Unpack();
}
```

#### UnpackRNG

```csharp
uint UnpackRNG (byte[] input, int in_start, uint input_size, byte[] output) {
    var coder = new Kogado.CRangeCoder();
    coder.InitQSModel (257, 12, 2000, null, false);
    return coder.Decode (output, 0, (uint)output.Length, input, (uint)in_start, input_size);
}
```

#### QueryEncryption

```csharp
EncryptionScheme QueryEncryption (string arc_name) {
    EncryptionScheme scheme = null;
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title))
        scheme = GetScheme (title);
    if (null == scheme)
    {
        var options = Query<WarOptions> (arcStrings.ArcEncryptedNotice);
        scheme = options.Scheme;
    }
    return scheme;
}
```

#### GetScheme

```csharp
static EncryptionScheme GetScheme (string scheme) {
    return Decoder.KnownSchemes.FirstOrDefault (s => s.Name == scheme);
}
```

### GameRes.Formats.ShiinaRio.YlzReader

#### 状态与常量

```csharp
byte[]  m_input ;

byte[]  m_output ;

int     m_src ;

uint    m_ctl = 0 ;

uint    m_mask = 0 ;
```

#### YlzReader

```csharp
public YlzReader (byte[] input, int src_offset, byte[] output) {
    m_input = input;
    m_src = src_offset;
    m_output = output;
}
```

#### GetCtlBit

```csharp
bool GetCtlBit () {
    bool bit = 0 != (m_ctl & m_mask);
    m_mask >>= 1;
    if (0 == m_mask)
    {
        m_ctl = LittleEndian.ToUInt32 (m_input, m_src);
        m_src += 4;
        m_mask = 0x80000000;
    }
    return bit;
}
```

#### GetBits

```csharp
int GetBits (int n) {
    int v = 0;
    for (int i = 0; i < n; ++i)
    {
        v <<= 1;
        if (GetCtlBit())
            v |= 1;
    }
    return v;
}
```

#### Unpack

```csharp
public void Unpack () {
    GetCtlBit();
    int dst = 0;
    while (dst < m_output.Length)
    {
        if (GetCtlBit())
        {
            m_output[dst++] = m_input[m_src++];
            continue;
        }
        bool next_bit = GetCtlBit();
        int offset = m_input[m_src++] | ~0xffff;
        int ah = 0xff;
        int count = 0;
        if (next_bit)
        {
            if (GetCtlBit())
            {
                ah = (ah << 1) | GetBits (1);
            }
            else if (GetCtlBit())
            {
                ah = (ah << 1) | GetBits (1);
                offset -= 0x200;
            }
            else if (GetCtlBit())
            {
                ah = (ah << 2) | GetBits (2);
                offset -= 0x400;
            }
            else if (GetCtlBit())
            {
                ah = (ah << 3) | GetBits (3);
                offset -= 0x800;
            }
            else
            {
                ah = (ah << 4) | GetBits (4);
                offset -= 0x1000;
            }

            if (GetCtlBit())
            {
                count = 3;
            }
            else if (GetCtlBit())
            {
                count = 4;
            }
            else if (GetCtlBit())
            {
                count = 5 + GetBits (1);
            }
            else if (GetCtlBit())
            {
                count = 7 + GetBits (2);
            }
            else if (GetCtlBit())
            {
                count = 0x0b + GetBits (3);
            }
            else
            {
                count = 0x13 + m_input[m_src++];
            }
        }
        else if (GetCtlBit())
        {
            ah <<= 3;
            ah |= GetBits (3);
            ah = (ah - 1) & 0xff;
            count = 2;
        }
        else if (0xff == (offset & 0xff))
        {
            return;
        }
        else
        {
            count = 2;
        }
        offset += (ah & 0xff) << 8;
        Binary.CopyOverlapped (m_output, dst + offset, dst, count);
        dst += count;
    }
}
```

### GameRes.Formats.ShiinaRio.HuffmanReader

#### 状态与常量

```csharp
byte[] m_src ;

byte[] m_dst ;

ushort[,] m_tree = new ushort[2,511] ;

int m_origin ;

int m_total ;

int m_input_pos ;

int m_remaining ;

int m_curbits ;

uint m_cache ;

ushort m_curindex ;
```

#### HuffmanReader

```csharp
public HuffmanReader (byte[] src, int index, int length, byte[] dst) {
    m_src = src;
    m_dst = dst;
    m_origin = index;
    m_total = length;
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    m_input_pos = m_origin;
    m_remaining = m_total;
    m_curbits = 0;
    m_curindex = 256;
    ushort root = CreateTree();
    for (int i = 0; i < m_dst.Length; ++i)
    {
        ushort symbol = root;
        while (symbol >= 256)
        {
            symbol = m_tree[GetBits(1), symbol];
        }
        m_dst[i] = (byte)symbol;
    }
    return m_dst;
}
```

#### ReadUInt32

```csharp
uint ReadUInt32 () {
    uint v;
    if (m_remaining >= 4)
    {
        v = LittleEndian.ToUInt32 (m_src, m_input_pos);
        m_input_pos += 4;
        m_remaining -= 4;
    }
    else if (m_remaining > 0)
    {
        v = m_src[m_input_pos++];
        int shift = 8;
        while (--m_remaining != 0)
        {
            v |= (uint)(m_src[m_input_pos++] << shift);
            shift += 8;
        }
    }
    else
        throw new InvalidFormatException ("Unexpected end of file");
    return v;
}
```

#### GetBits

```csharp
uint GetBits (int req_bits) {
    uint ret_val = 0;
    if (req_bits > m_curbits)
    {
        req_bits -= m_curbits;
        ret_val |= (m_cache & ((1u << m_curbits) - 1u)) << req_bits;
        m_cache = ReadUInt32();
        m_curbits = 32;
    }
    m_curbits -= req_bits;
    return ret_val | ((1u << req_bits) - 1u) & (m_cache >> m_curbits);
}
```

#### CreateTree

```csharp
ushort CreateTree () {
    ushort i;
    if (0 != GetBits (1))
    {
        i = m_curindex++;
        m_tree[0,i] = CreateTree();
        m_tree[1,i] = CreateTree();
    }
    else
        i = (ushort)GetBits (8);
    return i;
}
```

## 配套算法与外部条件

- [ArcFormats/ShiinaRio/WarcEncryption.cs](WarcEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ShiinaRio/ArcWARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
