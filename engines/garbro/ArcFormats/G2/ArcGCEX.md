# G2 / ArcGCEX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/G2` / `GameRes.Formats.G2.PakOpener` | `pak` | `47434558` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (0 != file.View.ReadInt32 (4))` |
| `PakOpener.TryOpen` | `long index_offset = file.View.ReadInt64 (8);` |
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "GCE3"))` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (index_offset+0x18);` |
| `PakOpener.TryOpen` | `bool index_packed = 0x11 == file.View.ReadInt32 (index_offset+4);` |
| `PakOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (index_offset+8);` |
| `PakOpener.TryOpen` | `int unpacked_size = file.View.ReadInt32 (index_offset+0x20);` |
| `PakOpener.TryOpen` | `int name_length = LittleEndian.ToUInt16 (index, current_filename);` |
| `PakOpener.TryOpen` | `uint size = LittleEndian.ToUInt32 (index, current_index+0x18);` |
| `PakOpener.TryOpen` | `UnpackedSize = LittleEndian.ToUInt32 (index, current_index+0x10),` |
| `PakOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "GCE"))` |
| `GceReader.Unpack` | `int segment_length = m_input.ReadInt32();` |
| `GceReader.Unpack` | `if (Binary.AsciiEqual (id, "GCE1"))` |
| `GceReader.Unpack` | `m_input.ReadInt32();` |
| `GceReader.Unpack` | `int data_length = m_input.ReadInt32();` |
| `GceReader.Unpack` | `int cmd_len = m_input.ReadInt32();` |
| `GceReader.Unpack` | `else if (Binary.AsciiEqual (id, "GCE0"))` |
| `GceReader.UnpackGce1Segment` | `byte b = m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.G2.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0 != file.View.ReadInt32 (4))
        return null;
    long index_offset = file.View.ReadInt64 (8);
    if (index_offset >= file.MaxOffset)
        return null;
    if (!file.View.AsciiEqual (index_offset, "GCE3"))
        return null;
    int count = file.View.ReadInt32 (index_offset+0x18);
    if (!IsSaneCount (count))
        return null;
    bool index_packed = 0x11 == file.View.ReadInt32 (index_offset+4);
    uint index_size = file.View.ReadUInt32 (index_offset+8);
    byte[] index = null;
    if (index_packed)
    {
        index_size -= 0x28;
        int unpacked_size = file.View.ReadInt32 (index_offset+0x20);
        using (var input = file.CreateStream (index_offset+0x28, index_size))
        using (var reader = new GceReader (input, unpacked_size))
            index = reader.Data;
    }
    else
    {
        index_size -= 0x20;
        index = new byte[index_size];
        if (index.Length != file.View.Read (index_offset+0x20, index, 0, index_size))
            return null;
    }
    int current_index = 0;
    int current_filename = 0x20*count;
    long current_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_length = LittleEndian.ToUInt16 (index, current_filename);
        if (current_filename+2+name_length > index.Length)
            return null;
        uint size = LittleEndian.ToUInt32 (index, current_index+0x18);
        if (size != 0)
        {
            string name = Encodings.cp932.GetString (index, current_filename+2, name_length);
            var entry = new PackedEntry
            {
                Name = name,
                Type = FormatCatalog.Instance.GetTypeFromName (name),
                Offset = current_offset,
                Size = size,
                UnpackedSize = LittleEndian.ToUInt32 (index, current_index+0x10),
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = entry.Size != entry.UnpackedSize;
            current_offset += entry.Size;
            dir.Add (entry);
        }
        current_index += 0x20;
        current_filename += 2 + name_length;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pentry = entry as PackedEntry;
    if (null == pentry || !pentry.IsPacked)
        return input;
    if (!arc.File.View.AsciiEqual (entry.Offset, "GCE"))
    {
        Trace.WriteLine ("Packed entry is not GCE", entry.Name);
        return input;
    }
    using (input)
    using (var reader = new GceReader (input, (int)pentry.UnpackedSize))
    {
        return new BinMemoryStream (reader.Data, entry.Name);
    }
}
```

### GameRes.Formats.G2.GceReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

int             m_unpacked_size ;

byte[]          m_output = null ;

int             m_dst ;

public byte[] Data {
    get
    {
        if (null == m_output)
        {
            m_output = new byte[m_unpacked_size];
            Unpack();
        }
        return m_output;
    }
}

int[] m_frame = new int[0x10000] ;

byte[]  m_control ;

int     m_control_pos ;

int     m_control_len ;

int     m_bit_pos ;
```

#### GceReader

```csharp
public GceReader (IBinaryStream input, int unpacked_size) {
    m_input = input;
    m_unpacked_size = unpacked_size;
}
```

#### Unpack

```csharp
private void Unpack () {
    m_dst = 0;
    byte[] id = new byte[4];
    while (4 == m_input.Read (id, 0, 4))
    {
        int segment_length = m_input.ReadInt32();
        if (Binary.AsciiEqual (id, "GCE1"))
        {
            m_input.ReadInt32();
            int data_length = m_input.ReadInt32();

            m_input.ReadInt32();
            int cmd_len = m_input.ReadInt32();
            long cmd_pos = m_input.Position + data_length;
            ReadControlStream (cmd_pos, cmd_len);

            int next = m_dst + segment_length;
            UnpackGce1Segment (segment_length);
            m_dst = next;
            m_input.Position = cmd_pos + cmd_len;
        }
        else if (Binary.AsciiEqual (id, "GCE0"))
        {
            if (segment_length != m_input.Read (m_output, m_dst, segment_length))
                throw new EndOfStreamException();
            m_dst += segment_length;
        }
        else
        {
            throw new InvalidFormatException ("Unknown compression type in GCE stream");
        }
    }
}
```

#### UnpackGce1Segment

```csharp
void UnpackGce1Segment (int segment_length) {
    int frame_pos = 0;
    int dst_end = m_dst + segment_length;
    while (m_dst < dst_end)
    {
        int n = GetLength();
        while (n --> 0)
        {
            m_frame[frame_pos] = m_dst;
            byte b = m_input.ReadUInt8();
            frame_pos = ((frame_pos << 8) | b) & 0xFFFF;
            m_output[m_dst++] = b;
        }
        if (m_dst >= dst_end)
            break;
        n = GetLength() + 1;
        int src = m_frame[frame_pos];
        while (n --> 0)
        {
            m_frame[frame_pos] = m_dst;
            frame_pos = ((frame_pos << 8) | m_output[src]) & 0xFFFF;
            m_output[m_dst++] = m_output[src++];
        }
    }
}
```

#### GetLength

```csharp
int GetLength () {
    int v = 0;
    if (0 == GetBit())
    {
        int digits = 0;
        while (0 == GetBit())
            ++digits;
        v = 1 << digits;
        while (digits --> 0)
            v |= GetBit() << digits;
    }
    return v;
}
```

#### ReadControlStream

```csharp
void ReadControlStream (long pos, int length) {
    var data_pos = m_input.Position;
    if (null == m_control || m_control.Length < length)
        m_control = new byte[length];
    m_input.Position = pos;
    if (length != m_input.Read (m_control, 0, length))
        throw new EndOfStreamException();
    m_control_pos = 0;
    m_control_len = length;
    m_input.Position = data_pos;
    m_bit_pos = 8;
}
```

#### GetBit

```csharp
int GetBit () {
    if (0 == m_bit_pos--)
    {
        ++m_control_pos;
        m_bit_pos = 7;
        --m_control_len;
        if (0 == m_control_len)
            throw new EndOfStreamException();
    }
    return 1 & (m_control[m_control_pos] >> m_bit_pos);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/G2/ArcGCEX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
