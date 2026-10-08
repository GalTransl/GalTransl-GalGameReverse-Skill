# CaramelBox / ArcARC4：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC4` / `GameRes.Formats.CaramelBox.Arc4Opener` | `bin`, `dat`, `データ` | `41524334` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Arc4Opener.TryOpen` | `if (0x010000 != file.View.ReadUInt32 (4))` |
| `Arc4Opener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `Arc4Opener.TryOpen` | `uint index_length = file.View.ReadUInt32 (8);` |
| `Arc4Opener.TryOpen` | `uint alignment    = file.View.ReadUInt32 (0xC);` |
| `Arc4Opener.TryOpen` | `int index_offset  = file.View.ReadInt32 (0x14);` |
| `Arc4Opener.TryOpen` | `int names_offset  = file.View.ReadInt32 (0x1C) - index_offset;` |
| `Arc4Opener.TryOpen` | `int segment_table = file.View.ReadInt32 (0x24) - index_offset;` |
| `Arc4Opener.TryOpen` | `uint base_offset  = file.View.ReadUInt32 (0x2C);` |
| `Arc4Opener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "tZ"))` |
| `Arc4Opener.TryOpen` | `int name_pos = ReadInt24 (index, current_offset) * 2;` |
| `Arc4Opener.TryOpen` | `int offset = ReadInt24 (index, current_offset+5);` |
| `Arc4Opener.TryOpen` | `entry.Segments.Add (ReadInt24 (index, segment_pos) + base_offset);` |
| `Arc4Opener.TryOpen` | `size += Binary.BigEndian (file.View.ReadUInt32 (segment+4));` |
| `Arc4Opener.TryOpen` | `entry.IsPacked = file.View.AsciiEqual (entry.Offset, "tZ");` |
| `Arc4Opener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+2);` |
| `Arc4Opener.ReadInt24` | `static int ReadInt24 (byte[] data, int pos) {` |
| `TzCompression.Unpack` | `int signature = m_input.ReadUInt16();` |
| `TzCompression.Unpack` | `uint unpacked_size = m_input.ReadUInt32();` |
| `TzCompression.Unpack` | `signature = m_input.ReadUInt16();` |
| `TzCompression.Unpack` | `ushort block_size = m_input.ReadUInt16();` |
| `TzCompression.Unpack` | `ushort unpacked_block_size = m_input.ReadUInt16();` |
| `TzCompression.Unpack` | `ushort key = m_input.ReadUInt16();` |
| `Arc4Stream.NextSegment` | `var segment_size = Binary.BigEndian (m_file.View.ReadUInt32 (offset+4));` |
| `Arc4Stream.ReadByte` | `public override int ReadByte () {` |
| `Arc4Stream.ReadByte` | `b = m_stream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CaramelBox.Arc4Entry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public List<long>   Segments ;
```

### GameRes.Formats.CaramelBox.Arc4Opener

继承/接口：`ArchiveFormat`。

#### Arc4Opener

```csharp
public Arc4Opener () {
    Extensions = new string[] { "bin", "dat", "データ" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0x010000 != file.View.ReadUInt32 (4))
        return null;
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;
    uint index_length = file.View.ReadUInt32 (8);
    uint alignment    = file.View.ReadUInt32 (0xC);
    int index_offset  = file.View.ReadInt32 (0x14);
    int names_offset  = file.View.ReadInt32 (0x1C) - index_offset;
    int segment_table = file.View.ReadInt32 (0x24) - index_offset;
    uint base_offset  = file.View.ReadUInt32 (0x2C);
    if (0 == alignment || index_offset <= 0 || names_offset <= 0 || segment_table <= 0)
        return null;
    if (!file.View.AsciiEqual (index_offset, "tZ"))
        return null;
    byte[] index;
    using (var packed = file.CreateStream (index_offset, index_length))
    using (var tz = new TzCompression (packed))
        index = tz.Unpack();

    int current_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_pos = ReadInt24 (index, current_offset) * 2;
        int name_length = index[current_offset+3];
        int chunk_count = index[current_offset+4];
        int offset = ReadInt24 (index, current_offset+5);
        var name = Binary.GetCString (index, names_offset + name_pos, name_length);
        var entry = FormatCatalog.Instance.Create<Arc4Entry> (name);
        entry.Segments = new List<long> (chunk_count);
        if (chunk_count > 1)
        {
            int segment_pos = segment_table + 3 * offset;
            for (int j = 0; j < chunk_count; ++j)
            {
                entry.Segments.Add (ReadInt24 (index, segment_pos) + base_offset);
                segment_pos += 3;
            }
        }
        else
            entry.Segments.Add (offset + base_offset);

        for (int j = 0; j < chunk_count; ++j)
            entry.Segments[j] *= alignment;
        dir.Add (entry);
        current_offset += 8;
    }
    foreach (Arc4Entry entry in dir)
    {
        uint size = 0;
        foreach (var segment in entry.Segments)
        {
            size += Binary.BigEndian (file.View.ReadUInt32 (segment+4));
        }
        entry.Offset = entry.Segments[0] + 0x10;
        entry.Size = size;
        entry.IsPacked = file.View.AsciiEqual (entry.Offset, "tZ");
        if (entry.IsPacked)
            entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+2);
        else
            entry.UnpackedSize = size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var xent = (Arc4Entry)entry;
    Stream input;
    if (1 == xent.Segments.Count)
        input = arc.File.CreateStream (entry.Offset, entry.Size);
    else
        input = new Arc4Stream (arc.File, xent);
    if (!xent.IsPacked)
        return input;
    using (input)
    using (var tz = new TzCompression (input))
        return new BinMemoryStream (tz.Unpack(), entry.Name);
}
```

#### ReadInt24

```csharp
static int ReadInt24 (byte[] data, int pos) {
    return data[pos] << 16 | data[pos+1] << 8 | data[pos+2];
}
```

### GameRes.Formats.CaramelBox.TzCompression

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
BinaryReader        m_input ;

bool _disposed = false ;
```

#### TzCompression

```csharp
public TzCompression (Stream stream) {
    m_input = new ArcView.Reader (stream);
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    int signature = m_input.ReadUInt16();
    uint unpacked_size = m_input.ReadUInt32();
    var data = new byte[unpacked_size];
    int dst = 0;
    var buffer = new byte[0x10000];
    while (dst < data.Length)
    {
        signature = m_input.ReadUInt16();
        ushort block_size = m_input.ReadUInt16();
        ushort unpacked_block_size = m_input.ReadUInt16();
        if (0 == unpacked_block_size)
            throw new InvalidFormatException();

        ushort key = m_input.ReadUInt16();
        if (block_size != m_input.Read (buffer, 0, block_size))
            throw new EndOfStreamException();
        DecryptBlock (buffer, 0, block_size, key);
        if (0x7453 == signature)
            Buffer.BlockCopy (buffer, 0, data, dst, unpacked_block_size);
        else if (0x745A == signature)
            UnpackBlock (buffer, 0, block_size, data, dst, unpacked_block_size);
        else
            throw new InvalidFormatException();
        dst += unpacked_block_size;
    }
    return data;
}
```

#### DecryptBlock

```csharp
unsafe void DecryptBlock (byte[] data, int pos, int count, uint key) {
    fixed (byte* data8 = &data[pos])
    {
        ushort* data16 = (ushort*)data8;
        for (int i = count / 2; i > 0; --i)
        {
            key *= 0x1465D9;
            key += 0x0FB5;
            *data16++ -= (ushort)(key >> 16);
        }
    }
}
```

#### UnpackBlock

```csharp
void UnpackBlock (byte[] input, int src, int input_size,
                  byte[] output, int dst, int output_size) {
    int src_end = src + input_size;
    while (src < src_end)
    {
        int ctl = input[src++];
        if (0 == ctl)
            break;
        if (0 != (ctl & 0x80))
        {
            int offset, count;
            if (0 != (ctl & 0x40))
            {
                if (0 != (ctl & 0x20))
                {
                    ctl = (ctl << 8) | input[src++];
                    ctl = (ctl << 8) | input[src++];

                    count = (ctl & 0x3F) + 4;
                    offset = (ctl >> 6) & 0x7FFF;
                }
                else
                {
                    ctl = (ctl << 8) | input[src++];

                    count = (ctl & 7) + 3;
                    offset = (ctl >> 3) & 0x3FF;
                }
            }
            else
            {
                count = (ctl & 3) + 2;
                offset = (ctl >> 2) & 0xF;
            }
            ++offset;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
        else
        {
            Buffer.BlockCopy (input, src, output, dst, ctl);
            src += ctl;
            dst += ctl;
        }
    }
}
```

### GameRes.Formats.CaramelBox.Arc4Stream

继承/接口：`Stream`。

#### 状态与常量

```csharp
ArcView     m_file ;

IEnumerator<long> m_segment ;

Stream      m_stream ;

bool        m_eof = false ;

public override bool CanRead { get { return !_disposed; } }

public override bool CanSeek { get { return false; } }

public override long Length { get { throw new NotSupportedException ("Arc4Stream.Length not supported"); } }

public override long Position {
    get { throw new NotSupportedException ("Arc4Stream.Position not supported."); }
    set { throw new NotSupportedException ("Arc4Stream.Position not supported."); }
}

bool _disposed = false ;
```

#### Arc4Stream

```csharp
public Arc4Stream (ArcView file, Arc4Entry entry) {
    m_file = file;
    m_segment = entry.Segments.GetEnumerator();
    NextSegment();
}
```

#### NextSegment

```csharp
private void NextSegment () {
    if (!m_segment.MoveNext())
    {
        m_eof = true;
        return;
    }
    var prev_stream = m_stream;
    long offset = m_segment.Current;
    var segment_size = Binary.BigEndian (m_file.View.ReadUInt32 (offset+4));
    m_stream = m_file.CreateStream (offset+0x10, segment_size);
    if (null != prev_stream)
        prev_stream.Dispose();
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int total = 0;
    while (!m_eof && count > 0)
    {
        int read = m_stream.Read (buffer, offset, count);
        if (0 != read)
        {
            total += read;
            offset += read;
            count -= read;
        }
        if (0 != count)
            NextSegment();
    }
    return total;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = -1;
    while (!m_eof)
    {
        b = m_stream.ReadByte();
        if (-1 != b)
            break;
        NextSegment();
    }
    return b;
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException ("Arc4Stream.Seek method is not supported");
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("Arc4Stream.SetLength method is not supported");
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    throw new NotSupportedException("Arc4Stream.WriteByte method is not supported");
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/CaramelBox/ArcARC4.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
