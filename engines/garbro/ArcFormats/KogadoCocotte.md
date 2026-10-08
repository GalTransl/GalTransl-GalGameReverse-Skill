# ArcFormats / KogadoCocotte：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CocotteEncoder.Decode` | `ushort src_block_size  = reader.ReadUInt16();` |
| `CocotteEncoder.Decode` | `ushort dest_block_size = reader.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kogado.CocotteEncoder

#### 状态与常量

```csharp
BWTEncode   m_cBWTEncode = new BWTEncode() ;

MTFEncode   m_cMTFEncode = new MTFEncode() ;

CRangeCoder m_cRangeCoder = new CRangeCoder() ;

const int RANGECODER_BLOCKSIZE = 0x2000 ;
```

#### Decode

```csharp
public bool Decode (Stream input, Stream output) {
    uint dwSrcLength = (uint)input.Length;
    var buffer = new byte [RANGECODER_BLOCKSIZE*4+2];
    uint dwSrcCursor = 0;
    var input_buffer = new byte[RANGECODER_BLOCKSIZE];

    m_cRangeCoder.InitQSModel();
    m_cMTFEncode.InitMTFOrder();

    using (var reader = new BinaryReader (input, Encoding.ASCII, true))
    {
        while (dwSrcCursor < dwSrcLength)
        {
            if (dwSrcCursor + 4 >= dwSrcLength)
                return false;
            ushort src_block_size  = reader.ReadUInt16();
            ushort dest_block_size = reader.ReadUInt16();
            ushort comp_block_size = (ushort)(src_block_size - 4);
            ushort decomp_block_size = (ushort)(dest_block_size + 2);

            if (dwSrcCursor + src_block_size > dwSrcLength)
                return false;
            if (src_block_size <= 4 || dest_block_size == 0)
                return false;
            if (comp_block_size == decomp_block_size)
            {
                int read = input.Read (buffer, 0, comp_block_size);
                m_cRangeCoder.InitQSModel();
            }
            else
            {
                if (comp_block_size > input_buffer.Length)
                    input_buffer = new byte[comp_block_size];
                int read = input.Read (input_buffer, 0, comp_block_size);
                if (read != comp_block_size)
                    return false;
                uint written = m_cRangeCoder.Decode (buffer, input_buffer, decomp_block_size, comp_block_size);
                if (0 == written)
                    break;
                if (written != decomp_block_size)
                    return false;
            }
            m_cMTFEncode.Decode (buffer, buffer, decomp_block_size);
            m_cBWTEncode.Decode (output, buffer, decomp_block_size);

            dwSrcCursor += src_block_size;
        }
    }
    return dwSrcCursor == dwSrcLength;
}
```

### GameRes.Formats.Kogado.CRangeCoder

#### 状态与常量

```csharp
byte[]  m_pSrcBuffer ;

byte[]  m_pDestBuffer ;

uint    m_dwSrcEnd ;

uint    m_dwDestEnd ;

uint    m_dwSrcIndex ;

uint    m_dwDestIndex ;

RangeCoder m_rc = new RangeCoder() ;

QSModel m_qsm ;

const int CODE_BITS = 32 ;

const int SHIFT_BITS = CODE_BITS - 9 ;

const int EXTRA_BITS = (CODE_BITS - 2) % 8 + 1 ;

const uint Top_value = 1u << (CODE_BITS - 1) ;

const uint Bottom_value = Top_value >> 8 ;

static readonly int[] RANGECODER_INITFREQ = {
    1400, 640, 320, 240, 160, 120,  80,  64,
    48,  40,  32,  24,  20,  20,  20,  20,
    16,  16,  16,  16,  12,  12,  12,  12,
    12,  12,   8,   8,   8,   8,   8,   8,
    6,   6,   6,   6,   6,   6,   6,   6,
    6,   6,   6,   6,   6,   6,   6,   6,
    5,   5,   5,   5,   5,   5,   5,   5,
    5,   5,   5,   5,   5,   5,   5,   5,

    4,   4,   4,   4,   4,   4,   4,   4,
    4,   4,   4,   4,   4,   4,   4,   4,
    4,   4,   4,   4,   4,   4,   4,   4,
    4,   4,   4,   4,   4,   4,   4,   4,
    3,   3,   3,   3,   3,   3,   3,   3,
    3,   3,   3,   3,   3,   3,   3,   3,
    3,   3,   3,   3,   3,   3,   3,   3,
    3,   3,   3,   3,   3,   3,   3,   3,

    3,   3,   3,   3,   3,   3,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,

    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,
    2,   2,   2,   2,   2,   2,   2,   2,

    2,
}
```

#### InitQSModel

```csharp
public void InitQSModel() {
    InitQSModel (257, 12, 2000, RANGECODER_INITFREQ, false);
}
```

#### InitQSModel

```csharp
public void InitQSModel (int n, int lg_totf, int rescale, int[] init, bool compress) {
    m_qsm = new QSModel (n, lg_totf, rescale, init, compress);
}
```

#### Decode

```csharp
public uint Decode (byte[] dest, byte[] src, uint destsize, uint srcsize) {
    return Decode (dest, 0, destsize, src, 0, srcsize);
}
```

#### Decode

```csharp
public uint Decode (byte[] dst, uint dst_index, uint dst_size,
                    byte[] src, uint src_index, uint src_size) {
    int ch, ltfreq, syfreq;

    m_dwSrcIndex = src_index;
    m_dwDestIndex = dst_index;
    m_pSrcBuffer = src;
    m_pDestBuffer = dst;
    m_dwSrcEnd = src_index + src_size;
    m_dwDestEnd = dst_index + dst_size;

    StartDecoding();

    while (m_dwSrcIndex < m_dwSrcEnd)
    {
        ltfreq = (int)DecodeCulshift (12);
        ch = m_qsm.GetSym (ltfreq);
        if (256 == ch)
            break;
        if (!SetDestByteImpl ((byte)ch))
            return 0;
        m_qsm.GetFreq (ch, out syfreq, out ltfreq);
        DecodeUpdate (syfreq, ltfreq, 1 << 12);
        m_qsm.Update (ch);
    }
    m_qsm.GetFreq (256, out syfreq, out ltfreq);
    DecodeUpdate (syfreq, ltfreq, 1 << 12);
    DoneDecoding();
    return m_dwDestIndex-dst_index;
}
```

#### StartDecoding

```csharp
int StartDecoding () {
    byte c;

    if (!GetSrcByteImpl (out c))
        return -1;
    if (!GetSrcByteImpl (out m_rc.buffer))
        return -1;
    m_rc.low = (uint)(m_rc.buffer >> (8 - EXTRA_BITS));
    m_rc.range = (uint)1 << EXTRA_BITS;

    return c;
}
```

#### DecNormalize

```csharp
bool DecNormalize() {
    while ( m_rc.range <= Bottom_value )
    {
        m_rc.low = ( m_rc.low << 8 ) | (byte)(m_rc.buffer << EXTRA_BITS);
        if (!GetSrcByteImpl (out m_rc.buffer))
            return false;
        m_rc.low |= (uint)m_rc.buffer >> ( 8 - EXTRA_BITS );
        m_rc.range <<= 8;
    }
    return true;
}
```

#### DecodeCulshift

```csharp
uint DecodeCulshift (int shift) {
    uint tmp;

    DecNormalize();
    m_rc.help = m_rc.range >> shift;
    tmp = m_rc.low / m_rc.help;
    return (0 != (tmp >> shift) ? (1u << shift) - 1u : tmp);
}
```

#### DecodeUpdate

```csharp
void DecodeUpdate (int sy_f, int lt_f, int tot_f) {
    uint tmp = m_rc.help * (uint)lt_f;

    m_rc.low -= tmp;
    if ( lt_f + sy_f < tot_f )
        m_rc.range = m_rc.help * (uint)sy_f;
    else
        m_rc.range -= tmp;
}
```

#### DoneDecoding

```csharp
void DoneDecoding() {
    DecNormalize();
}
```

#### GetSrcByteImpl

```csharp
bool GetSrcByteImpl (out byte pData) {
    if (m_dwSrcIndex >= m_dwSrcEnd)
    {
        pData = 0;
        return false;
    }
    pData = m_pSrcBuffer[m_dwSrcIndex++];
    return true;
}
```

#### SetDestByteImpl

```csharp
bool SetDestByteImpl (byte byData) {
    if (m_dwDestIndex >= m_dwDestEnd)
        return false;
    m_pDestBuffer[m_dwDestIndex++] = byData;
    return true;
}
```

### GameRes.Formats.Kogado.RangeCoder

#### 状态与常量

```csharp
public uint low ;

public uint range ;

public uint help ;

public byte buffer ;
```

### GameRes.Formats.Kogado.BWTEncode

#### 状态与常量

```csharp
public const ulong BWT_SORTTABLESIZE = 0x00010000 ;

int[] sort_table = new int[BWT_SORTTABLESIZE] ;
```

#### Decode

```csharp
public void Decode (Stream dest, byte[] src, int size) {
    int[] count = new int[256];
    int top = src[0] | src[1] << 8;

    int pos = 2;
    size -= 2;

    for (int i = 0; i < size; i++)
        count[ src[pos+i] ]++;
    for (short i = 1; i < 256; i++)
        count[i] += count[i-1];
    for (int i = size - 1; i >= 0; i --)
    {
        sort_table[--count[src[pos+i]]] = i;
    }

    int ptr = sort_table[top];
    for (int i = 0; i < size; i++)
    {
        dest.WriteByte (src[pos+ptr]);
        ptr = sort_table[ptr];
    }
}
```

### GameRes.Formats.Kogado.MTFEncode

#### 状态与常量

```csharp
byte[] m_MTFTable = new byte[256] ;
```

#### InitMTFOrder

```csharp
public void InitMTFOrder() {
    for (int i = 0; i < 256; i++)
        m_MTFTable[i] = (byte)i;
}
```

#### Encode

```csharp
public void Encode (byte[] dest, byte[] src, int size) {
    for (int i = 0; i < size; i++)
    {
        byte c = src[i];
        byte n = 0;

        while (m_MTFTable[n] != c)
            n++;
        if (n > 0)
        {
            Buffer.BlockCopy (m_MTFTable, 0, m_MTFTable, 1, n);
            m_MTFTable[0] = c;
        }
        dest[i] = n;
    }
}
```

#### Decode

```csharp
public void Decode (byte[] dest, byte[] src, int size) {
    for ( int i = 0; i < size; i++ )
    {
        byte n = src[i];
        byte c = m_MTFTable[n];
        if (n > 0)
        {
            Buffer.BlockCopy (m_MTFTable, 0, m_MTFTable, 1, n);
            m_MTFTable[0] = c;
        }
        dest[i] = c;
    }
}
```

### GameRes.Formats.Kogado.QSModel

#### 状态与常量

```csharp
public int m_n ;

public int m_left ;

public int m_nextleft ;

public int m_rescale ;

public int m_targetrescale ;

public int m_incr ;

public int m_searchshift ;

public ushort[] m_cf ;

public ushort[] m_newf ;

public ushort[] m_search ;

public const int TBLSHIFT = 7 ;
```

#### QSModel

```csharp
public QSModel (int n, int lg_totf, int rescale, int[] init, bool compress) {
    m_n = n;
    m_targetrescale = rescale;
    m_searchshift = lg_totf - TBLSHIFT;
    if (m_searchshift < 0)
        m_searchshift = 0;
    m_cf = new ushort[n+1];
    m_newf = new ushort[n+1];
    m_cf[n] = (ushort)(1 << lg_totf);
    m_cf[0] = 0;
    if (compress)
    {
        m_search = null;
    }
    else
    {
        m_search = new ushort[(1<<TBLSHIFT)+1];
        m_search[1<<TBLSHIFT] = (ushort)(n-1);
    }
    Reset (init);
}
```

#### Reset

```csharp
public void Reset (int[] init) {
    int i;
    m_rescale = m_n>>4 | 2;
    m_nextleft = 0;
    if (init == null)
    {
        int initval = m_cf[m_n] / m_n;
        int end = m_cf[m_n] % m_n;
        for (i = 0; i < end; i++)
            m_newf[i] = (ushort)(initval+1);
        for (; i < m_n; i++)
            m_newf[i] = (ushort)initval;
    }
    else
    {
        for (i = 0; i < m_n; i++)
            m_newf[i] = (ushort)init[i];
    }
    DoRescale();
}
```

#### DoRescale

```csharp
void DoRescale () {
    if (0 != m_nextleft)
    {
        m_incr++;
        m_left = m_nextleft;
        m_nextleft = 0;
        return;
    }
    if (m_rescale < m_targetrescale)
    {
        m_rescale <<= 1;
        if (m_rescale > m_targetrescale)
            m_rescale = m_targetrescale;
    }
    int i, cf, missing;
    cf = missing = m_cf[m_n];
    for (i = m_n-1; i != 0; i--)
    {
        int tmp = m_newf[i];
        cf -= tmp;
        m_cf[i] = (ushort)cf;
        tmp = tmp>>1 | 1;
        missing -= tmp;
        m_newf[i] = (ushort)tmp;
    }
    if (cf != m_newf[0])
        throw new ApplicationException ("Run-time error in QSModel.DoRescale");

    m_newf[0] = (ushort)(m_newf[0]>>1 | 1);
    missing -= m_newf[0];
    m_incr = missing / m_rescale;
    m_nextleft = missing % m_rescale;
    m_left = m_rescale - m_nextleft;
    if (m_search != null)
    {
        i = m_n;
        while (i != 0)
        {
            int end = (m_cf[i]-1) >> m_searchshift;
            i--;
            int start = m_cf[i] >> m_searchshift;
            while (start <= end)
            {
                m_search[start] = (ushort)i;
                start++;
            }
        }
    }
}
```

#### GetFreq

```csharp
public void GetFreq (int sym, out int sy_f, out int lt_f) {
    lt_f = m_cf[sym];
    sy_f = m_cf[sym+1] - lt_f;
}
```

#### GetSym

```csharp
public int GetSym (int lt_f) {
    int lo, hi;
    int tmp = lt_f >> m_searchshift;
    lo = m_search[tmp];
    hi = m_search[tmp+1] + 1;
    while (lo+1 < hi)
    {
        int mid = (lo + hi) >> 1;
        if (lt_f < m_cf[mid])
            hi = mid;
        else
            lo = mid;
    }
    return lo;
}
```

#### Update

```csharp
public void Update (int sym) {
    if (m_left <= 0)
        DoRescale();
    m_left--;
    m_newf[sym] += (ushort)m_incr;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/KogadoCocotte.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
