# Unity / BundleStream：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 类型别名

| 摘录中的名称 | 来源类型 |
|---|---|
| `LZMA` | `SevenZip.Compression.LZMA` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BundleStream.LzmaDecompressBlock` | `var props = m_input.ReadBytes (5);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.BundleStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
readonly ArcViewStream  m_input ;

readonly long           m_length ;

IList<BundleSegment>    m_segments ;

long                    m_position ;

int                     m_current_segment ;

byte[]                  m_buffer ;

int                     m_buffer_pos ;

int                     m_buffer_len ;

byte[]                  m_packed ;

public override bool CanRead { get { return !m_disposed; } }

public override bool CanSeek { get { return !m_disposed; } }

public override long Length { get { return m_length; } }

public override long Position {
    get { return m_position; }
    set {
        if (value == m_position)
            return;
        if (value < 0)
            throw new ArgumentOutOfRangeException ("value", "Stream position is out of range.");
        m_position = value;
        int segment_index = 0;
        for (int i = 1; i < m_segments.Count; ++i)
        {
            if (m_segments[i].UnpackedOffset > value)
                break;
            ++segment_index;
        }
        var segment = m_segments[segment_index];
        if (segment_index != m_current_segment)
        {
            m_current_segment = segment_index;
            m_buffer_len = 0;
        }
        if (segment.IsCompressed)
        {
            m_buffer_pos = (int)(m_position - segment.UnpackedOffset);
        }
        else
        {
            m_buffer_pos = 0;
            m_input.Position = segment.Offset + (m_position - segment.UnpackedOffset);
        }
    }
}

bool m_disposed = false ;
```

#### BundleStream

```csharp
public BundleStream (ArcView file, IList<BundleSegment> segments) {
    if (null == segments || 0 == segments.Count)
        throw new ArgumentException ("Segments list is empty.", "segments");
    m_input = file.CreateStream();
    m_segments = segments;
    var last_segment = m_segments[m_segments.Count-1];
    m_length = last_segment.UnpackedOffset + last_segment.UnpackedSize;
    m_position = 0;
    m_current_segment = 0;
    m_input.Position = m_segments[0].Offset;
}
```

#### PrepareBuffer

```csharp
byte[] PrepareBuffer (uint length) {
    if (null == m_buffer || length > m_buffer.Length)
        m_buffer = new byte[length];
    return m_buffer;
}
```

#### ReadCompressedSegment

```csharp
void ReadCompressedSegment (BundleSegment segment) {
    m_input.Position = segment.Offset;
    int method = segment.Compression & 0x3F;
    if (1 == method)
    {
        m_buffer_len = LzmaDecompressBlock (segment.PackedSize, segment.UnpackedSize);
        return;
    }
    if (null == m_packed || segment.PackedSize > m_packed.Length)
        m_packed = new byte[segment.PackedSize];
    int packed_size = m_input.Read (m_packed, 0, (int)segment.PackedSize);
    var output = PrepareBuffer (segment.UnpackedSize);
    if (3 == method || 2 == method)
        m_buffer_len = Lz4Compressor.DecompressBlock (m_packed, packed_size, output, (int)segment.UnpackedSize);
    else
        throw new NotImplementedException ("Not supported Unity asset bundle compression.");
}
```

#### LzmaDecompressBlock

```csharp
int LzmaDecompressBlock (uint packed_size, uint unpacked_size) {
    var decoder = new LZMA.Decoder();
    var props = m_input.ReadBytes (5);
    decoder.SetDecoderProperties (props);
    var buffer = PrepareBuffer (unpacked_size);
    using (var output = new MemoryStream (buffer))
    {
        decoder.Code (m_input, output, packed_size-5, unpacked_size, null);
        return (int)output.Length;
    }
}
```

#### ReadFromSegment

```csharp
int ReadFromSegment (BundleSegment segment, byte[] buffer, int offset, int count) {
    Debug.Assert (m_position >= segment.UnpackedOffset && m_position <= segment.UnpackedOffset + segment.UnpackedSize);
    if (!segment.IsCompressed)
    {
        int available = (int)Math.Min (count, (segment.UnpackedOffset + segment.UnpackedSize) - m_position);
        return m_input.Read (buffer, offset, available);
    }
    else
    {
        if (0 == m_buffer_len)
            ReadCompressedSegment (segment);
        int available = Math.Min (count, m_buffer_len - m_buffer_pos);
        Buffer.BlockCopy (m_buffer, m_buffer_pos, buffer, offset, available);
        m_buffer_pos += available;
        return available;
    }
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    if (m_position >= m_length)
        return 0;
    int total_read = 0;
    while (count > 0)
    {
        var segment = m_segments[m_current_segment];
        int read = ReadFromSegment (segment, buffer, offset, count);
        m_position += read;
        total_read += read;
        offset += read;
        count -= read;
        if (count > 0)
        {
            if (m_current_segment+1 == m_segments.Count)
                break;
            ++m_current_segment;
            m_buffer_len = m_buffer_pos = 0;
            m_input.Position = m_segments[m_current_segment].Offset;
            Debug.Assert (m_position == m_segments[m_current_segment].UnpackedOffset);
        }
    }
    return total_read;
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    switch (origin)
    {
    case SeekOrigin.Current:    offset += m_position; break;
    case SeekOrigin.End:        offset += m_length; break;
    }
    Position = offset;
    return offset;
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("Stream.SetLength method is not supported.");
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    throw new NotSupportedException ("Stream.WriteByte method is not supported.");
}
```

## 配套算法与外部条件

- [ArcFormats/Lz4Stream.cs](../Lz4Stream.md)：本页引用的随包算法资料。
- [ArcFormats/Lzma/LzmaDecoder.cs](../Lzma/LzmaDecoder.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/ArcUnityFS.cs](ArcUnityFS.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/BundleStream.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
