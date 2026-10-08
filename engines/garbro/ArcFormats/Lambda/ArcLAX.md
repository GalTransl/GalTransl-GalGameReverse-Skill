# Lambda / ArcLAX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LAX` / `GameRes.Formats.Lambda.LaxOpener` | `lax` | `244c6170` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LaxOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "$LapI__"))` |
| `LaxOpener.TryOpen` | `int count = file.View.ReadInt32 (index_offset+8);` |
| `LaxOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (index_offset+0x10);` |
| `LaxOpener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (index_offset+0x14);` |
| `LaxOpener.TryOpen` | `index_offset = file.View.ReadUInt32 (index_offset+0xC);` |
| `LaxOpener.TryOpen` | `if (!index.AsciiEqual (pos, "$LapF__"))` |
| `LaxOpener.TryOpen` | `entry.UnpackedSize = index.ToUInt32 (pos+0x10);` |
| `LaxOpener.TryOpen` | `entry.Size         = index.ToUInt32 (pos+0x14);` |
| `LaxOpener.TryOpen` | `entry.Offset       = index.ToUInt32 (pos+0x18) + data_offset;` |
| `LaxStream.ReadSegment` | `if (!m_buffer.AsciiEqual ("_AF"))` |
| `LaxStream.ReadSegment` | `int chunk_size = m_buffer.ToUInt16 (4);` |
| `LaxStream.ReadSegment` | `int final_size = m_buffer.ToUInt16 (6);` |
| `LaxStream.ReadSegment` | `int unpacked_size = m_buffer.ToUInt16 (8);` |
| `LaxStream.LzssUnpack` | `bits = BaseStream.ReadByte();` |
| `LaxStream.LzssUnpack` | `int lo = BaseStream.ReadByte();` |
| `LaxStream.LzssUnpack` | `int hi = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lambda.LaxOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long index_offset = file.MaxOffset-0x28;
    if (!file.View.AsciiEqual (index_offset, "$LapI__"))
        return null;
    int count = file.View.ReadInt32 (index_offset+8);
    if (!IsSaneCount (count))
        return null;
    uint unpacked_size = file.View.ReadUInt32 (index_offset+0x10);
    uint packed_size = file.View.ReadUInt32 (index_offset+0x14);
    index_offset = file.View.ReadUInt32 (index_offset+0xC);
    var index = new byte[unpacked_size];
    using (var input = file.CreateStream (index_offset, packed_size))
    using (var lax = new LaxStream (input))
        lax.Read (index, 0, index.Length);

    uint data_offset = 8;
    int entry_length = 0x128;
    int pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (!index.AsciiEqual (pos, "$LapF__"))
            return null;
        var name = Binary.GetCString (index, pos+0x24, 0x104);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.UnpackedSize = index.ToUInt32 (pos+0x10);
        entry.Size         = index.ToUInt32 (pos+0x14);
        entry.Offset       = index.ToUInt32 (pos+0x18) + data_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasAnyOfExtensions (".bmx", ".b32"))
            entry.Type = "image";
        dir.Add (entry);
        pos += entry_length;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new LaxStream (input);
}
```

### GameRes.Formats.Lambda.LaxStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
byte[]  m_buffer ;

int     m_buffer_size ;

int     m_buffer_pos ;

bool m_eof = false ;

byte[]  m_frame = new byte[0x1000] ;

public override bool CanSeek { get { return false; } }

public override long Length {
    get { throw new NotSupportedException ("Stream.Length property is not supported"); }
}

public override long Position {
    get { throw new NotSupportedException ("Stream.Position property is not supported"); }
    set { throw new NotSupportedException ("Stream.Position property is not supported"); }
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int total_read = 0;
    while (count > 0)
    {
        if (m_buffer_pos == m_buffer_size)
        {
            if (m_eof)
                break;
            ReadSegment();
        }
        int available = Math.Min (count, m_buffer_size - m_buffer_pos);
        Buffer.BlockCopy (m_buffer, m_buffer_pos, buffer, offset, available);
        m_buffer_pos += available;
        offset += available;
        count -= available;
        total_read += available;
    }
    return total_read;
}
```

#### ReadSegment

```csharp
void ReadSegment () {
    if (null == m_buffer)
        m_buffer = new byte[0x8000];
    m_buffer_pos = m_buffer_size = 0;
    long chunk_start = BaseStream.Position;
    if (BaseStream.Read (m_buffer, 0, 10) < 10)
    {
        m_eof = true;
        return;
    }
    if (!m_buffer.AsciiEqual ("_AF"))
        throw new InvalidFormatException ("Invalid compressed LAX stream.");
    int method = m_buffer[3];
    int chunk_size = m_buffer.ToUInt16 (4);
    int final_size = m_buffer.ToUInt16 (6);
    if (final_size != 0)
        throw new NotImplementedException ("Double compression in LAX streams not implemented.");
    int unpacked_size = m_buffer.ToUInt16 (8);
    if (unpacked_size > m_buffer.Length)
        m_buffer = new byte[unpacked_size];

    switch (method)
    {
    case '1':
        m_buffer_size = LzssUnpack (unpacked_size);
        break;

    case '2':
        m_buffer_size = HuffmanUnpack (unpacked_size);
        break;

    default:
        m_buffer_size = BaseStream.Read (m_buffer, 0, unpacked_size);
        break;
    }
    BaseStream.Position = chunk_start + chunk_size;
}
```

#### LzssUnpack

```csharp
int LzssUnpack (int unpacked_size) {
    for (int i = 0; i < m_frame.Length; ++i)
        m_frame[i] = 0;
    int frame_pos = 0xFEE;
    int bits = 2;
    int dst = 0;
    while (dst < unpacked_size)
    {
        bits >>= 1;
        if (1 == bits)
        {
            bits = BaseStream.ReadByte();
            if (-1 == bits)
                break;
            bits |= 0x100;
        }
        int lo = BaseStream.ReadByte();
        if (-1 == lo)
            break;
        if (0 != (bits & 1))
        {
            m_buffer[dst++] = m_frame[frame_pos++ & 0xFFF] = (byte)lo;
        }
        else
        {
            int hi = BaseStream.ReadByte();
            if (-1 == hi)
                break;
            int offset = (hi & 0xF0) << 4 | lo;
            int count = Math.Min (3 + (hi & 0xF), unpacked_size - dst);
            while (count --> 0)
            {
                byte v = m_frame[offset++ & 0xFFF];
                m_buffer[dst++] = m_frame[frame_pos++ & 0xFFF] = v;
            }
        }
    }
    return dst;
}
```

#### HuffmanUnpack

```csharp
int HuffmanUnpack (int unpacked_size) {
    using (var input = new HuffmanDecompressor())
    {
        input.Initialize (BaseStream);
        return input.Continue (m_buffer, 0, unpacked_size);
    }
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException ("LzssStream.Seek method is not supported");
}
```

## 配套算法与外部条件

- [ArcFormats/HuffmanCompression.cs](../HuffmanCompression.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Lambda/ArcLAX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
