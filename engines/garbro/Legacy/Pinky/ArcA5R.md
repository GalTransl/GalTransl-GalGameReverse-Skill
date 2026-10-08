# Pinky / ArcA5R：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `A5R` / `GameRes.Formats.Pinky.A5rOpener` | `a5r`, `a5e` | `50435253`, `504c4942` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `A5rOpener.TryOpen` | `uint id = file.View.ReadUInt32 (0);` |
| `A5rOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != ~id)` |
| `A5rOpener.TryOpen` | `int count = file.View.ReadInt32 (0x30);` |
| `A5rOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0x34);` |
| `A5rOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `A5rOpener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset+4),` |
| `A5rOpener.TryOpen` | `Type = file.View.ReadByte (index_offset+8),` |
| `A5rOpener.TryOpen` | `Compression = file.View.ReadByte (index_offset+9),` |
| `A5rOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_offset+0xA);` |
| `A5rOpener.TryOpen` | `if (8 == input.Read (riff_buffer, 0, 8) && riff_buffer.AsciiEqual ("RIFF"))` |
| `A5rOpener.TryOpen` | `uint riff_size = riff_buffer.ToUInt32 (4);` |
| `A5rStream.ReadByte` | `public override int ReadByte () {` |
| `A5rStream.ReadByte` | `b = m_stream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Pinky.A5Segment

#### 状态与常量

```csharp
public uint     Offset ;

public uint     Size ;

public uint     UnpackedSize ;

public byte     Type ;

public byte     Compression ;

public bool IsCompressed { get { return 3 == Compression; } }
```

### GameRes.Formats.Pinky.A5rEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public IEnumerable<A5Segment>   Segments ;
```

### GameRes.Formats.Pinky.A5rOpener

继承/接口：`ArchiveFormat`。

#### A5rOpener

```csharp
public A5rOpener () {
    Signatures = new uint[] { 0x53524350, 0x42494C50 };
    Extensions = new string[] { "a5r", "a5e" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint id = file.View.ReadUInt32 (0);
    if (file.View.ReadUInt32 (4) != ~id)
        return null;
    int count = file.View.ReadInt32 (0x30);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (0x34);
    if (index_offset >= file.MaxOffset)
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint next_offset = file.View.ReadUInt32 (index_offset);
    var segments = new A5Segment[count];
    for (int i = 0; i < count; ++i)
    {
        var segment = new A5Segment {
            Offset = next_offset,
            UnpackedSize = file.View.ReadUInt32 (index_offset+4),
            Type = file.View.ReadByte (index_offset+8),
            Compression = file.View.ReadByte (index_offset+9),
        };
        next_offset = file.View.ReadUInt32 (index_offset+0xA);
        if (next_offset > file.MaxOffset || next_offset < segment.Offset)
            return null;
        segment.Size = (uint)(next_offset - segment.Offset);
        segments[i] = segment;
        index_offset += 0xA;
    }
    var dir = new List<Entry> (count);
    var riff_buffer = new byte[8];
    for (int i = 0; i < count; )
    {
        A5rEntry entry;
        var segment = segments[i];
        var name = string.Format ("{0}#{1:D5}", base_name, i);
        if (0x3C == segment.Type)
        {
            Stream input = file.CreateStream (segment.Offset, segment.Size);
            if (3 == segment.Compression)
                input = new ZLibStream (input, CompressionMode.Decompress);
            using (input)
            {
                if (8 == input.Read (riff_buffer, 0, 8) && riff_buffer.AsciiEqual ("RIFF"))
                {
                    uint riff_size = riff_buffer.ToUInt32 (4);
                    entry = new A5rEntry {
                        Name = name + ".wav",
                        Type = "audio",
                        Offset = segment.Offset,
                        Size = 0,
                        UnpackedSize = 0,
                    };
                    var segment_list = new List<A5Segment>();
                    for (;;)
                    {
                        entry.Size += segment.Size;
                        entry.UnpackedSize += segment.UnpackedSize;
                        entry.IsPacked |= segment.Compression == 3;
                        segment_list.Add (segment);
                        ++i;
                        if (i >= count || entry.UnpackedSize >= riff_size)
                            break;
                        segment = segments[i];
                        if (segment.Type != 0x3C)
                            break;
                    }
                    entry.Segments = segment_list;
                    dir.Add (entry);
                    continue;
                }
            }
        }
        if (0x3E == segment.Type)
            name += ".bmp";
        entry = new A5rEntry {
            Name = name,
            Type = 0x3E == segment.Type ? "image" : "",
            Offset = segment.Offset,
            Size = segment.Size,
            UnpackedSize = segment.UnpackedSize,
            IsPacked = segment.Compression == 3,
            Segments = new A5Segment[1] { segment },
        };
        dir.Add (entry);
        ++i;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var a5ent = (A5rEntry)entry;
    Stream input;
    if (a5ent.Segments.Count() == 1)
    {
        input = arc.File.CreateStream (entry.Offset, entry.Size);
        if (a5ent.IsPacked)
            input = new ZLibStream (input, CompressionMode.Decompress);
    }
    else
    {
        input = new A5rStream (arc.File, a5ent);
    }
    return input;
}
```

### GameRes.Formats.Pinky.A5rStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
ArcView     m_file ;

A5rEntry    m_entry ;

IEnumerator<A5Segment> m_segment ;

Stream      m_stream ;

long        m_offset = 0 ;

bool        m_eof = false ;

public override bool CanRead { get { return !disposed; } }

public override bool CanSeek { get { return false; } }

public override long Length { get { return m_entry.UnpackedSize; } }

public override long Position {
    get { return m_offset; }
    set { throw new NotSupportedException ("A5rStream.Position not supported."); }
}

bool disposed = false ;
```

#### A5rStream

```csharp
public A5rStream (ArcView file, A5rEntry entry) {
    m_file = file;
    m_entry = entry;
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
    if (null != m_stream)
        m_stream.Dispose();
    var segment = m_segment.Current;
    m_stream = m_file.CreateStream (segment.Offset, segment.Size);
    if (segment.IsCompressed)
        m_stream = new ZLibStream (m_stream, CompressionMode.Decompress);
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
            m_offset += read;
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
    throw new NotSupportedException ("A5rStream.Seek method is not supported");
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("A5rStream.SetLength method is not supported");
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    throw new NotSupportedException("A5rStream.WriteByte method is not supported");
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Pinky/ArcA5R.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
