# ShiinaRio / WarcEncryption：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Decoder.Decrypt2` | `uint src = LittleEndian.ToUInt32 (data, index) & 0x1ffcu;` |
| `Decoder.Decrypt2` | `src = LittleEndian.ToUInt32 (m_scheme.DecodeBin, (int)src);` |
| `Decoder.DecryptHelper4` | `buf[i] = BigEndian.ToUInt32 (data, index+40+4*i);` |
| `Decoder.DecryptHelper4` | `uint flags = LittleEndian.ToUInt32 (data, index+40) \| 0x80000000;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ShiinaRio.EncryptionScheme

#### 状态与常量

```csharp
public string Name { get; set; }

public string OriginalTitle { get; set; }

public    int Version { get; set; }

public    int EntryNameSize ;

public byte[] CryptKey ;

public uint[] HelperKey ;

public byte[] Region ;

public byte[] DecodeBin ;

public IByteArray       ShiinaImage ;

public IDecryptExtra    ExtraCrypt ;

public static readonly EncryptionScheme Warc110 = new EncryptionScheme { EntryNameSize = 0x10 }
```

### GameRes.Formats.ShiinaRio.Decoder

#### 状态与常量

```csharp
EncryptionScheme    m_scheme ;

public int   SchemeVersion { get { return m_scheme.Version; } }

public int     WarcVersion { get; private set; }

public uint MaxIndexLength { get; private set; }

public int   EntryNameSize { get { return m_scheme.EntryNameSize; } }

public IDecryptExtra ExtraCrypt { get { return m_scheme.ExtraCrypt; } }

private uint          Rand { get; set; }

static readonly uint[] CustomCrcTable = InitCrcTable() ;
```

#### Decoder

```csharp
public Decoder (int version, EncryptionScheme scheme) {
    m_scheme = scheme;
    WarcVersion = version;
    MaxIndexLength = GetMaxIndexLength (version);
}
```

#### Decrypt

```csharp
public void Decrypt (byte[] data, int index, uint data_length) {
    DoEncryption (data, index, data_length, DecryptContent);
}
```

#### Encrypt

```csharp
public void Encrypt (byte[] data, int index, uint data_length) {
    DoEncryption (data, index, data_length, EncryptContent);
}
```

#### DecryptIndex

```csharp
public void DecryptIndex (uint index_offset, byte[] index) {
    Decrypt (index, 0, (uint)index.Length);
    XorIndex (index_offset, index);
}
```

#### EncryptIndex

```csharp
public void EncryptIndex (uint index_offset, byte[] index) {
    XorIndex (index_offset, index);
    Encrypt (index, 0, (uint)index.Length);
}
```

#### DecryptContent

```csharp
void DecryptContent (int x, byte[] data, int index, uint length) {
    int n = 0;
    for (int i = 2; i < length; ++i)
    {
        byte d = data[index+i];
        if (WarcVersion > 120)
            d ^= (byte)((double)NextRand() / 16777216.0);
        d = Binary.RotByteR (d, 1);
        d ^= (byte)(m_scheme.CryptKey[n++] ^ m_scheme.CryptKey[x]);
        data[index+i] = d;
        x = d % m_scheme.CryptKey.Length;
        if (n >= m_scheme.CryptKey.Length)
            n = 0;
    }
}
```

#### EncryptContent

```csharp
void EncryptContent (int x, byte[] data, int index, uint length) {
    int n = 0;
    for (int i = 2; i < length; ++i)
    {
        byte k = (byte)(m_scheme.CryptKey[n++] ^ m_scheme.CryptKey[x]);
        byte d = data[index+i];
        x = d % m_scheme.CryptKey.Length;
        d ^= k;
        d = Binary.RotByteL (d, 1);
        if (WarcVersion > 120)
            d ^= (byte)((double)NextRand() / 16777216.0);
        data[index+i] = d;
        if (n >= m_scheme.CryptKey.Length)
            n = 0;
    }
}
```

#### ContentEncryptor

```csharp
delegate void ContentEncryptor (int start_key, byte[] data, int index, uint length) ;
```

#### DoEncryption

```csharp
void DoEncryption (byte[] data, int index, uint data_length, ContentEncryptor encryptor) {
    if (data_length < 3 || WarcVersion < 120)
        return;
    uint effective_length = Math.Min (data_length, 1024u);
    int a, b;
    uint fac = 0;
    Rand = data_length;
    if (WarcVersion > 120)
    {
        a = (sbyte)data[index]   ^ (sbyte)data_length;
        b = (sbyte)data[index+1] ^ (sbyte)(data_length / 2);
        if (data_length != MaxIndexLength && (WarcVersion > 130 || m_scheme.Version > 2150))
        {

            int idx = (int)((double)NextRand() * (m_scheme.ShiinaImage.Length / 4294967296.0));
            if (WarcVersion >= 160)
            {
                fac = Rand + m_scheme.ShiinaImage[idx];
                fac = DecryptHelper3 (fac) & 0xfffffff;
                if (effective_length > 0x80 && SchemeVersion > 2350)
                {
                    DecryptHelper4 (data, index+4, m_scheme.HelperKey);
                    index += 0x80;
                    effective_length -= 0x80;
                }
            }
            else if (150 == WarcVersion)
            {
                fac = Rand + m_scheme.ShiinaImage[idx];
                fac ^= (fac & 0xfff) * (fac & 0xfff);
                uint v = 0;
                for (int i = 0; i < 32; ++i)
                {
                    uint bit = fac & 1;
                    fac >>= 1;
                    if (0 != bit)
                        v += fac;
                }
                fac = v;
            }
            else if (140 == WarcVersion)
            {
                fac = m_scheme.ShiinaImage[idx];
            }
            else if (130 == WarcVersion)
            {
                fac = m_scheme.ShiinaImage[idx & 0xff];
            }
        }
    }
    else
    {
        a = data[index];
        b = data[index+1];
    }
    Rand ^= (uint)(DecryptHelper1 (a) * 100000000.0);

    double token = 0.0;
    if (0 != (a|b))
    {
        token = Math.Acos ((double)a / Math.Sqrt ((double)(a*a + b*b)));
        token = token / Math.PI * 180.0;
    }
    if (b < 0)
        token = 360.0 - token;

    int x = (int)((fac + (byte)DecryptHelper2 (token)) % (uint)m_scheme.CryptKey.Length);
    encryptor (x, data, index, effective_length);
}
```

#### XorIndex

```csharp
unsafe void XorIndex (uint index_offset, byte[] index) {
    fixed (byte* buf_raw = index)
    {
        uint* encoded = (uint*)buf_raw;
        for (int i = 0; i < index.Length/4; ++i)
            encoded[i] ^= index_offset;
        if (WarcVersion >= 170)
        {
            byte key = (byte)~WarcVersion;
            for (int i = 0; i < index.Length; ++i)
                buf_raw[i] ^= key;
        }
    }
}
```

#### Decrypt2

```csharp
public void Decrypt2 (byte[] data, int index, uint length) {
    if (length < 0x400 || null == m_scheme.DecodeBin)
        return;
    uint crc = Crc32Normal.UpdateCrc (0xFFFFFFFF, data, index, 0x100);
    index += 0x100;
    for (int i = 0; i < 0x40; ++i)
    {
        uint src = LittleEndian.ToUInt32 (data, index) & 0x1ffcu;
        src = LittleEndian.ToUInt32 (m_scheme.DecodeBin, (int)src);
        uint key = src ^ crc;
        data[index++ + 0x100] ^= (byte)key;
        data[index++ + 0x100] ^= (byte)(key >> 8);
        data[index++ + 0x100] ^= (byte)(key >> 16);
        data[index++ + 0x100] ^= (byte)(key >> 24);
    }
}
```

#### DecryptHelper1

```csharp
double DecryptHelper1 (double a) {
    if (a < 0)
        return -DecryptHelper1 (-a);

    double v0;
    double v1;
    if (a < 18.0)
    {
        v0 = a;
        v1 = a;
        double v2 = -(a * a);

        for (int j = 3; j < 1000; j += 2)
        {
            v1 *= v2 / (j * (j - 1));
            v0 += v1 / j;
            if (v0 == v2)
                break;
        }
        return v0;
    }

    int flags = 0;
    double v0_l = 0;
    v1 = 0;
    double div = 1 / a;
    double v1_h = 2.0;
    double v0_h = 2.0;
    double v1_l = 0;
    v0 = 0;
    int i = 0;

    do
    {
        v0 += div;
        div *= ++i / a;
        if (v0 < v0_h)
            v0_h = v0;
        else
            flags |= 1;

        v1 += div;
        div *= ++i / a;
        if (v1 < v1_h)
            v1_h = v1;
        else
            flags |= 2;

        v0 -= div;
        div *= ++i / a;
        if (v0 > v0_l)
            v0_l = v0;
        else
            flags |= 4;

        v1 -= div;
        div *= ++i / a;
        if (v1 > v1_l)
            v1_l = v1;
        else
            flags |= 8;
    }
    while (flags != 0xf);

    return ((Math.PI - Math.Cos(a) * (v0_l + v0_h)) - (Math.Sin(a) * (v1_l + v1_h))) / 2.0;
}
```

#### DecryptHelper2

```csharp
uint DecryptHelper2 (double a) {
    double v0, v1, v2, v3;

    if (a > 1.0)
    {
        v0 = Math.Sqrt (a * 2 - 1);
        for (;;)
        {
            v1 = 1 - (double)NextRand() / 4294967296.0;
            v2 = 2.0 * (double)NextRand() / 4294967296.0 - 1.0;
            if (v1 * v1 + v2 * v2 > 1.0)
                continue;

            v2 /= v1;
            v3 = v2 * v0 + a - 1.0;
            if (v3 <= 0)
                continue;

            v1 = (a - 1.0) * Math.Log (v3 / (a - 1.0)) - v2 * v0;
            if (v1 < -50.0)
                continue;

            if (((double)NextRand() / 4294967296.0) <= (Math.Exp(v1) * (v2 * v2 + 1.0)))
                break;
        }
    }
    else
    {
        v0 = Math.Exp(1.0) / (a + Math.Exp(1.0));
        do
        {
            v1 = (double)NextRand() / 4294967296.0;
            v2 = (double)NextRand() / 4294967296.0;
            if (v1 < v0)
            {
                v3 = Math.Pow(v2, 1.0 / a);
                v1 = Math.Exp(-v3);
            } else
            {
                v3 = 1.0 - Math.Log(v2);
                v1 = Math.Pow(v3, a - 1.0);
            }
        }
        while ((double)NextRand() / 4294967296.0 >= v1);
    }

    if (WarcVersion > 120)
        return (uint)(v3 * 256.0);
    else
        return (byte)((double)NextRand() / 4294967296.0);
}
```

#### DecryptHelper3

```csharp
uint DecryptHelper3 (uint key) {
    var p = new Union();
    p.u = key;
    var fv = new Union();
    fv.f = (float)(1.5 * (double)p.b0 + 0.1);
    uint v0 = Binary.BigEndian (fv.u);
    fv.f = (float)(1.5 * (double)p.b1 + 0.1);
    uint v1 = (uint)fv.f;
    fv.f = (float)(1.5 * (double)p.b2 + 0.1);
    uint v2 = (uint)-fv.i;
    fv.f = (float)(1.5 * (double)p.b3 + 0.1);
    uint v3 = ~fv.u;

    return ((v0 + v1) | (v2 - v3));
}
```

#### DecryptHelper4

```csharp
void DecryptHelper4 (byte[] data, int index, uint[] key_src) {
    uint[] buf = new uint[0x50];
    int i;
    for (i = 0; i < 0x10; ++i)
    {
        buf[i] = BigEndian.ToUInt32 (data, index+40+4*i);
    }
    for (; i < 0x50; ++i)
    {
        uint v = buf[i-16];
        v ^= buf[i-14];
        v ^= buf[i-8];
        v ^= buf[i-3];
        buf[i] = Binary.RotL (v, 1);
    }
    uint[] key = new uint[10];
    Array.Copy (key_src, key, 5);
    uint k0 = key[0];
    uint k1 = key[1];
    uint k2 = key[2];
    uint k3 = key[3];
    uint k4 = key[4];

    for (int buf_idx = 0; buf_idx < 0x50; ++buf_idx)
    {
        uint f, c;
        if (buf_idx < 0x10)
        {
            f = k1 ^ k2 ^ k3;
            c = 0;
        }
        else if (buf_idx < 0x20)
        {
            f = k1 & k2 | k3 & ~k1;
            c = 0x5A827999;
        }
        else if (buf_idx < 0x30)
        {
            f = k3 ^ (k1 | ~k2);
            c = 0x6ED9EBA1;
        }
        else if (buf_idx < 0x40)
        {
            f = k1 & k3 | k2 & ~k3;
            c = 0x8F1BBCDC;
        }
        else
        {
            f = k1 ^ (k2 | ~k3);
            c = 0xA953FD4E;
        }
        uint new_k0 = buf[buf_idx] + k4 + f + c + Binary.RotL (k0, 5);
        uint new_k2 = Binary.RotR (k1, 2);
        k1 = k0;
        k4 = k3;
        k3 = k2;
        k2 = new_k2;
        k0 = new_k0;
    }
    key[0] += k0;
    key[1] += k1;
    key[2] += k2;
    key[3] += k3;
    key[4] += k4;
    var ft = new FILETIME {
        DateTimeLow = key[1],
        DateTimeHigh = key[0] & 0x7FFFFFFF
    };
    var sys_time = new SYSTEMTIME (ft);
    key[5] = (uint)(sys_time.Year | sys_time.Month << 16);
    key[7] = (uint)(sys_time.Hour | sys_time.Minute << 16);
    key[8] = (uint)(sys_time.Second | sys_time.Milliseconds << 16);

    uint flags = LittleEndian.ToUInt32 (data, index+40) | 0x80000000;
    uint rgb = buf[1] >> 8;
    if (0 == (flags & 0x78000000))
        flags |= 0x98000000;
    key[6] = RegionCrc32 (m_scheme.Region, flags, rgb);
    key[9] = (uint)(((int)key[2] * (long)(int)key[3]) >> 8);
    if (m_scheme.Version >= 2390)
        key[6] += key[9];
    unsafe
    {
        fixed (byte* data_fixed = data)
        {
            uint* encoded = (uint*)(data_fixed+index);
            for (i = 0; i < 10; ++i)
            {
                encoded[i] ^= key[i];
            }
        }
    }
}
```

#### InitCrcTable

```csharp
static uint[] InitCrcTable () {
    var table = new uint[0x100];
    for (uint i = 0; i != 256; ++i)
    {
        uint poly = i;
        for (int j = 0; j < 8; ++j)
        {
            uint bit = poly & 1;
            poly = Binary.RotR (poly, 1);
            if (0 == bit)
                poly ^= 0x6DB88320;
        }
        table[i] = poly;
    }
    return table;
}
```

#### RegionCrc32

```csharp
uint RegionCrc32 (byte[] src, uint flags, uint rgb) {
    int src_alpha = (int)flags & 0x1ff;
    int dst_alpha = (int)(flags >> 12) & 0x1ff;
    flags >>= 24;
    if (0 == (flags & 0x10))
        dst_alpha = 0;
    if (0 == (flags & 8))
        src_alpha = 0x100;
    int y_step = 0;
    int x_step = 4;
    int width = 48;
    int pos = 0;
    if (0 != (flags & 0x40))
    {
        y_step += width;
        pos += (width-1)*4;
        x_step = -x_step;
    }
    if (0 != (flags & 0x20))
    {
        y_step -= width;
        pos += width*0x2f*4;
    }
    y_step <<= 3;
    uint checksum = 0;
    for (int y = 0; y < 48; ++y)
    {
        for (int x = 0; x < 48; ++x)
        {
            int alpha = src[pos+3] * src_alpha;
            alpha >>= 8;
            uint color = rgb;
            for (int i = 0; i < 3; ++i)
            {
                int v = src[pos+i];
                int c = (int)(color & 0xff);
                c -= v;
                c = (c * dst_alpha) >> 8;
                c = (c + v) & 0xff;
                c = (c * alpha) >> 8;
                checksum = (checksum >> 8) ^ CustomCrcTable[(c ^ checksum) & 0xff];
                color >>= 8;
            }
            pos += x_step;
        }
        pos += y_step;
    }
    return checksum;
}
```

#### NextRand

```csharp
uint NextRand () {
    Rand = 1566083941u * Rand + 1u;
    return Rand;
}
```

#### GetMaxIndexLength

```csharp
uint GetMaxIndexLength (int version) {
    int max_index_entries = version < 150 || SchemeVersion < 2310 ? 8192 : 16384;
    return (uint)((m_scheme.EntryNameSize + 0x18) * max_index_entries);
}
```

### GameRes.Formats.ShiinaRio.Decoder.Union

#### FieldOffset

```csharp
[FieldOffset(0)]
public int i ;
```

#### FieldOffset

```csharp
[FieldOffset (0)]
public uint u ;
```

#### FieldOffset

```csharp
[FieldOffset(0)]
public float f ;
```

#### FieldOffset

```csharp
[FieldOffset(0)]
public byte b0 ;
```

#### FieldOffset

```csharp
[FieldOffset(1)]
public byte b1 ;
```

#### FieldOffset

```csharp
[FieldOffset(2)]
public byte b2 ;
```

#### FieldOffset

```csharp
[FieldOffset(3)]
public byte b3 ;
```

### GameRes.Formats.ShiinaRio.Decoder.FILETIME

#### 状态与常量

```csharp
public uint DateTimeLow ;

public uint DateTimeHigh ;
```

### GameRes.Formats.ShiinaRio.Decoder.SYSTEMTIME

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Year ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Month ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort DayOfWeek ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Day ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Hour ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Minute ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Second ;
```

#### MarshalAs

```csharp
[MarshalAs(UnmanagedType.U2)] public ushort Milliseconds ;
```

#### SYSTEMTIME

```csharp
public SYSTEMTIME (FILETIME ft) {
    FileTimeToSystemTime (ref ft, out this);
}
```

#### DllImport

```csharp
[DllImport ("kernel32.dll", CallingConvention = CallingConvention.Winapi, SetLastError = true)]
static extern bool FileTimeToSystemTime (ref FILETIME lpFileTime, out SYSTEMTIME lpSystemTime) ;
```

## 配套算法与外部条件

- [ArcFormats/Crc32.cs](../Crc32.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ShiinaRio/WarcEncryption.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
