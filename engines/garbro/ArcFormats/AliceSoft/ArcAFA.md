# AliceSoft / ArcAFA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AFA` / `GameRes.Formats.AliceSoft.AfaOpener` | `afa` | `41464148` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AfaOpener.TryOpen` | `if (!file.View.AsciiEqual (8, "AlicArch"))` |
| `AfaOpener.TryOpen` | `if (!file.View.AsciiEqual (0x1C, "INFO"))` |
| `AfaOpener.TryOpen` | `int version = file.View.ReadInt32 (0x10);` |
| `AfaOpener.TryOpen` | `long base_offset = file.View.ReadUInt32 (0x18);` |
| `AfaOpener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (0x20);` |
| `AfaOpener.TryOpen` | `int unpacked_size = file.View.ReadInt32 (0x24);` |
| `AfaOpener.TryOpen` | `int count = file.View.ReadInt32 (0x28);` |
| `AfaOpener.TryOpen` | `int name_length = index.ReadInt32();` |
| `AfaOpener.TryOpen` | `int index_step = index.ReadInt32();` |
| `AfaOpener.TryOpen` | `index.ReadInt32();` |
| `AfaOpener.TryOpen` | `entry.Offset = index.ReadUInt32() + base_offset;` |
| `AfaOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `AfaOpener.TryOpenV3` | `if (file.View.ReadInt32 (8) != 3)` |
| `AfaOpener.TryOpenV3` | `uint index_size = file.View.ReadUInt32 (4);` |
| `AfaOpener.OpenEntry` | `if (entry.Size <= 0x10 \|\| !arc.File.View.AsciiEqual (entry.Offset, "AFF\0"))` |
| `AfaOpener.OpenEntry` | `var prefix = arc.File.View.ReadBytes (entry.Offset+0x10, encrypted_length);` |
| `AfaIndexReader.Read` | `m_dict = ReadBytes (bits);` |
| `AfaIndexReader.Read` | `int packed_size   = ReadInt32 (bits);` |
| `AfaIndexReader.Read` | `int unpacked_size = ReadInt32 (bits);` |
| `AfaIndexReader.Read` | `int count = ReadInt32 (index);` |
| `AfaIndexReader.Read` | `ReadInt32 (index);` |
| `AfaIndexReader.Read` | `entry.Offset = (uint)ReadInt32 (index) + m_data_offset;` |
| `AfaIndexReader.Read` | `entry.Size   = (uint)ReadInt32 (index);` |
| `AfaIndexReader.ReadBytes` | `byte[] ReadBytes (MsbBitStream input) {` |
| `AfaIndexReader.ReadBytes` | `int buf_size = ReadInt32 (input);` |
| `AfaIndexReader.ReadEncryptedChars` | `int buf_size = ReadInt32 (input);` |
| `AfaIndexReader.ReadInt32` | `static int ReadInt32 (MsbBitStream input) {` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AliceSoft.AfaOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal readonly EncodingSetting AfaEncoding = new EncodingSetting ("AFAEncodingCP", "DefaultEncoding") ;

internal Encoding NameEncoding { get { return AfaEncoding.Get<Encoding>(); } }

static readonly byte[] AffKey = {
    0xC8, 0xBB, 0x8F, 0xB7, 0xED, 0x43, 0x99, 0x4A,
    0xA2, 0x7E, 0x5B, 0xB0, 0x68, 0x18, 0xF8, 0x88
}
```

#### AfaOpener

```csharp
public AfaOpener () {
    ContainedFormats = new[] { "QNT", "AJP", "DCF", "OGG" };
    Settings = new[] { AfaEncoding };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (8, "AlicArch"))
        return TryOpenV3 (file);
    if (!file.View.AsciiEqual (0x1C, "INFO"))
        return null;
    int version = file.View.ReadInt32 (0x10);
    long base_offset = file.View.ReadUInt32 (0x18);
    uint packed_size = file.View.ReadUInt32 (0x20);
    int unpacked_size = file.View.ReadInt32 (0x24);
    int count = file.View.ReadInt32 (0x28);
    if (!IsSaneCount (count))
        return null;

    var default_enc = NameEncoding;
    var dir = new List<Entry> (count);
    var name_buf = new byte[0x40];
    using (var input = file.CreateStream (0x2C, packed_size))
    using (var zstream = new ZLibStream (input, CompressionMode.Decompress))
    using (var index = new BinaryReader (zstream))
    {
        for (int i = 0; i < count; ++i)
        {
            int name_length = index.ReadInt32();
            int index_step = index.ReadInt32();
            if (name_length <= 0 || name_length > index_step || index_step > unpacked_size)
                return null;
            if (index_step > name_buf.Length)
                name_buf = new byte[index_step];
            if (index_step != index.Read (name_buf, 0, index_step))
                return null;
            var name = default_enc.GetString (name_buf, 0, name_length);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            index.ReadInt32();
            index.ReadInt32();
            if (version < 2)
                index.ReadInt32();
            entry.Offset = index.ReadUInt32() + base_offset;
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### TryOpenV3

```csharp
internal ArcFile TryOpenV3 (ArcView file) {
    if (file.View.ReadInt32 (8) != 3)
        return null;
    uint index_size = file.View.ReadUInt32 (4);
    var index = new AfaIndexReader (file, index_size);
    var dir = index.Read();
    if (null == dir || 0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size <= 0x10 || !arc.File.View.AsciiEqual (entry.Offset, "AFF\0"))
        return base.OpenEntry (arc, entry);
    uint data_size = entry.Size - 0x10u;
    uint encrypted_length = Math.Min (0x40u, data_size);
    var prefix = arc.File.View.ReadBytes (entry.Offset+0x10, encrypted_length);
    for (int i = 0; i < prefix.Length; ++i)
        prefix[i] ^= AffKey[i & 0xF];
    if (data_size <= 0x40)
        return new BinMemoryStream (prefix, entry.Name);
    var rest = arc.File.CreateStream (entry.Offset+0x10+encrypted_length, data_size-encrypted_length);
    return new PrefixStream (prefix, rest);
}
```

### GameRes.Formats.AliceSoft.AfaIndexReader

#### 状态与常量

```csharp
ArcView         m_file ;

uint            m_data_offset ;

byte[]          m_dict ;

byte[] m_string_buf = new byte[0x100] ;
```

#### AfaIndexReader

```csharp
public AfaIndexReader (ArcView file, uint index_size) {
    m_file = file;
    m_data_offset = index_size + 8;
}
```

#### Read

```csharp
public List<Entry> Read () {
    byte[] packed;
    using (var input = m_file.CreateStream (12, m_data_offset-12))
    using (var bits = new MsbBitStream (input))
    {
        bits.GetNextBit();
        m_dict = ReadBytes (bits);
        if (null == m_dict)
            return null;
        int packed_size   = ReadInt32 (bits);
        int unpacked_size = ReadInt32 (bits);
        packed = new byte[packed_size];
        for (int i = 0; i < packed_size; ++i)
        {
            packed[i] = (byte)bits.GetBits (8);
        }
    }
    using (var bstr = new BinMemoryStream (packed))
    using (var zstr = new ZLibStream (bstr, CompressionMode.Decompress))
    using (var index = new MsbBitStream (zstr))
    {
        index.GetNextBit();
        int count = ReadInt32 (index);
        if (!ArchiveFormat.IsSaneCount (count))
            return null;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            if (index.GetBits (2) == -1)
                break;
            var name_buf = ReadEncryptedChars (index);
            if (null == name_buf)
                return null;
            var name = DecryptString (name_buf, name_buf.Length);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            ReadInt32 (index);
            ReadInt32 (index);
            entry.Offset = (uint)ReadInt32 (index) + m_data_offset;
            entry.Size   = (uint)ReadInt32 (index);
            if (!entry.CheckPlacement (m_file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return dir;
    }
}
```

#### ReadBytes

```csharp
byte[] ReadBytes (MsbBitStream input) {
    int buf_size = ReadInt32 (input);
    var buf = new byte[buf_size];
    int dst = 0;
    var rnd = new RandomGenerator ((uint)buf_size);
    while (dst < buf_size)
    {
        int count = (int)rnd.GetNext() & 3;
        int skipped = input.GetBits (count + 1);
        if (-1 == skipped)
            return null;
        rnd.GetNext();

        int v = input.GetBits (8);
        if (-1 == v)
            return null;
        buf[dst++] = (byte)v;
    }
    return buf;
}
```

#### ReadEncryptedChars

```csharp
ushort[] ReadEncryptedChars (MsbBitStream input) {
    int buf_size = ReadInt32 (input);
    var buf = new ushort[buf_size];
    int dst = 0;
    var rnd = new RandomGenerator ((uint)buf_size);
    while (dst < buf_size)
    {
        int count = (int)rnd.GetNext() & 3;
        int skipped = input.GetBits (count + 1);
        if (-1 == skipped)
            return null;
        rnd.GetNext();

        int lo = input.GetBits (8);
        int hi = input.GetBits (8);
        if (-1 == lo || -1 == hi)
            return null;
        buf[dst++] = (ushort)(lo | hi << 8);
    }
    return buf;
}
```

#### DecryptString

```csharp
string DecryptString (ushort[] input, int input_length) {
    if (m_string_buf.Length < input_length)
        m_string_buf = new byte[input_length];
    for (int i = 0; i < input_length; ++i)
    {
        m_string_buf[i] = (byte)(m_dict[input[i]] ^ 0xA4);
    }
    return Encodings.cp932.GetString (m_string_buf, 0, input_length);
}
```

#### ReadInt32

```csharp
static int ReadInt32 (MsbBitStream input) {
    int b0 = input.GetBits (8);
    int b1 = input.GetBits (8);
    int b2 = input.GetBits (8);
    int b3 = input.GetBits (8);
    return b3 << 24 | b2 << 16 | b1 << 8 | b0;
}
```

### GameRes.Formats.AliceSoft.RandomGenerator

#### 状态与常量

```csharp
uint[]  m_state = new uint[521] ;

int     m_current ;
```

#### RandomGenerator

```csharp
public RandomGenerator (uint seed) {
    Init (seed);
}
```

#### Init

```csharp
public void Init (uint seed) {
    uint val = 0;
    for (int i = 0; i < 17; ++i)
    {
        for (int j = 0; j < 32; ++j)
        {
            seed = 1566083941u * seed + 1;
            val = seed & 0x80000000 | (val >> 1);
        }
        m_state[i] = val;
    }
    m_state[16] = m_state[15] ^ (m_state[0] >> 9) ^ (m_state[16] << 23);
    for (int i = 17; i < 521; ++i)
    {
        m_state[i] = m_state[i-1] ^ (m_state[i-16] >> 9) ^ (m_state[i-17] << 23);
    }
    Shuffle();
    Shuffle();
    Shuffle();
    Shuffle();
    m_current = -1;
}
```

#### GetNext

```csharp
public uint GetNext () {
    ++m_current;
    if (m_current >= 521)
    {
        Shuffle();
        m_current = 0;
    }
    return m_state[m_current];
}
```

#### Shuffle

```csharp
void Shuffle () {
    for (int i = 0; i < 32; i += 4)
    {
        m_state[i  ] ^= m_state[i + 489];
        m_state[i+1] ^= m_state[i + 490];
        m_state[i+2] ^= m_state[i + 491];
        m_state[i+3] ^= m_state[i + 492];
    }
    for (int i = 32; i < 521; i += 3)
    {
        m_state[i  ] ^= m_state[i - 32];
        m_state[i+1] ^= m_state[i - 31];
        m_state[i+2] ^= m_state[i - 30];
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/ResourceSettings.cs](../ResourceSettings.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/AliceSoft/ArcAFA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
