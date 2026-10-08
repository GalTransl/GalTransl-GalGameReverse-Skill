# ArcFormats / Lz4Stream：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Lz4Stream.ReadNextBlock` | `int block_size = LittleEndian.ToInt32 (m_block_header, 0);` |
| `Lz4Compressor.DecompressBlock` | `int offset = LittleEndian.ToUInt16 (block, src);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Compression.Lz4FrameInfo

#### 状态与常量

```csharp
public int      BlockSize ;

public bool     IndependentBlocks ;

public bool     HasBlockChecksum ;

public bool     HasContentLength ;

public bool     HasContentChecksum ;

public bool     HasDictionary ;

public long     OriginalLength ;

public int      DictionaryId ;
```

#### Lz4FrameInfo

```csharp
public Lz4FrameInfo (byte flags) {
    int version = flags >> 6;
    if (version != 1)
        throw Lz4Compressor.InvalidData();
    IndependentBlocks  = 0 != (flags & 0x20);
    HasBlockChecksum   = 0 != (flags & 0x10);
    HasContentLength   = 0 != (flags & 8);
    HasContentChecksum = 0 != (flags & 4);
    HasDictionary      = 0 != (flags & 1);
}
```

#### SetBlockSize

```csharp
public void SetBlockSize (int code) {
    switch ((code >> 4) & 7)
    {
    case 4: BlockSize = 0x10000; break;
    case 5: BlockSize = 0x40000; break;
    case 6: BlockSize = 0x100000; break;
    case 7: BlockSize = 0x400000; break;
    default: throw Lz4Compressor.InvalidData();
    }
}
```

### GameRes.Compression.Lz4Stream

继承/接口：`GameRes.Formats.InputProxyStream`。

#### 状态与常量

```csharp
Lz4FrameInfo    m_info ;

readonly byte[] m_block_header ;

byte[]          m_block ;

int             m_block_size ;

byte[]          m_data ;

int             m_data_size ;

int             m_data_pos ;

bool            m_eof ;

public override bool CanSeek { get { return false; } }

public override long Length {
    get { throw new NotSupportedException ("Lz4Stream.Length property is not supported"); }
}

public override long Position {
    get { throw new NotSupportedException ("Lz4Stream.Position property is not supported"); }
    set { throw new NotSupportedException ("Lz4Stream.Position property is not supported"); }
}
```

#### Lz4Stream

```csharp
public Lz4Stream (Stream input, Lz4FrameInfo info, bool leave_open = false) : base (input, leave_open) {
    if (null == info)
        throw new ArgumentNullException ("info");
    if (info.BlockSize <= 0)
        throw new ArgumentOutOfRangeException ("info.BlockSize");
    if (!info.IndependentBlocks)
        throw new NotImplementedException ("LZ4 compression with linked blocks not implemented.");
    if (info.HasDictionary)
        throw new NotImplementedException ("LZ4 compression with dictionary not implemented.");
    m_info = info;
    m_block_header = new byte[4];
    m_data = new byte[m_info.BlockSize];
    m_data_size = 0;
    m_data_pos = 0;
    m_eof = false;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int total_read = 0;
    while (count > 0)
    {
        if (m_data_pos < m_data_size)
        {
            int available = Math.Min (m_data_size - m_data_pos, count);
            Buffer.BlockCopy (m_data, m_data_pos, buffer, offset, available);
            total_read += available;
            m_data_pos += available;
            offset += available;
            count -= available;
        }
        else if (m_eof)
            break;
        else
            ReadNextBlock();
    }
    return total_read;
}
```

#### ReadNextBlock

```csharp
void ReadNextBlock () {
    if (4 != BaseStream.Read (m_block_header, 0, 4))
        throw new EndOfStreamException();
    int block_size = LittleEndian.ToInt32 (m_block_header, 0);
    if (0 == block_size)
    {
        m_eof = true;
        m_data_size = 0;
        if (m_info.HasContentChecksum)
            ReadChecksum();
    }
    else if (block_size < 0)
    {
        m_data_size = block_size & 0x7FFFFFFF;
        if (m_data_size > m_data.Length)
            m_data = new byte[m_data_size];
        m_data_size = BaseStream.Read (m_data, 0, m_data_size);
        if (m_info.HasBlockChecksum)
            ReadChecksum();
    }
    else
    {
        m_block_size = block_size;
        if (null == m_block || m_block_size > m_block.Length)
            m_block = new byte[m_block_size];
        if (m_block_size != BaseStream.Read (m_block, 0, m_block_size))
            throw new EndOfStreamException();
        m_data_size = Lz4Compressor.DecompressBlock (m_block, m_block_size, m_data, m_data.Length);
        if (m_info.HasBlockChecksum)
            ReadChecksum();
    }
    m_data_pos = 0;
}
```

#### ReadChecksum

```csharp
void ReadChecksum () {
    if (4 != BaseStream.Read (m_block_header, 0, 4))
        throw new EndOfStreamException();

}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException ("Lz4Stream.Seek method is not supported");
}
```

### GameRes.Compression.Lz4Compressor

#### 状态与常量

```csharp
const int MinMatch          = 4 ;

const int LastLiterals      = 5 ;

const int MFLimit           = 12 ;

const int MatchLengthBits   = 4 ;

const int MatchLengthMask   = 0xF ;

const int RunMask           = 0xF ;
```

#### DecompressBlock

```csharp
public static int DecompressBlock (byte[] block, int block_size, byte[] output, int output_size) {
    int src = 0;
    int iend = block_size;

    int dst = 0;
    int oend = output_size;

    for (;;)
    {

        int token = block[src++];
        int length = token >> MatchLengthBits;
        if (RunMask == length)
        {
            int n;
            do
            {
                n = block[src++];
                length += n;
            }
            while ((src < iend - RunMask) && (0xFF == n));
            if (dst + length < dst || src + length < src)
                throw InvalidData();
        }

        int copy_end = dst + length;
        if ((copy_end > oend - MFLimit) || (src + length > iend - (3+LastLiterals)))
        {
            if ((src + length != iend) || copy_end > oend)
                throw InvalidData();
            Buffer.BlockCopy (block, src, output, dst, length);
            src += length;
            dst += length;
            break;
        }
        Buffer.BlockCopy (block, src, output, dst, length);
        src += length;
        dst = copy_end;

        int offset = LittleEndian.ToUInt16 (block, src);
        src += 2;
        int match = dst - offset;
        if (match < 0)
            throw InvalidData();

        length = token & MatchLengthMask;
        if (MatchLengthMask == length)
        {
            int n;
            do
            {
                n = block[src++];
                if (src > iend - LastLiterals)
                    throw InvalidData();
                length += n;
            }
            while (0xFF == n);
            if (dst + length < dst)
                throw InvalidData();
        }
        length += MinMatch;

        Binary.CopyOverlapped (output, match, dst, length);
        dst += length;
    }
    return dst;
}
```

#### InvalidData

```csharp
internal static InvalidDataException InvalidData () {
    return new InvalidDataException ("Invalid LZ4 compressed stream.");
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Lz4Stream.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
