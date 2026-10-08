# Kogado / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/KOGADO` / `GameRes.Formats.Kogado.ArcOpener` | `arc` | `beadbca8` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcIndexReader.ArcIndexReader` | `m_base_offset = arc.View.ReadUInt32 (0xC);` |
| `ArcIndexReader.ReadIndex` | `int section_count = m_index.ToInt32 (0);` |
| `ArcIndexReader.ReadIndex` | `int count = m_index.ToInt32 (pos+8);` |
| `ArcIndexReader.ReadIndex` | `int section_size = m_index.ToInt32 (pos+0xC);` |
| `ArcIndexReader.ReadIndex` | `if (m_index.AsciiEqual (pos, "DDS\0"))` |
| `ArcIndexReader.ReadIndex` | `else if (m_index.AsciiEqual (pos, "OVA\0"))` |
| `ArcIndexReader.ReadSection` | `var name = ReadFileName (m_index.ToInt32 (name_pos));` |
| `ArcIndexReader.ReadSection` | `entry.Offset = m_index.ToUInt32 (layout_pos) + m_base_offset;` |
| `ArcIndexReader.ReadSection` | `entry.Size = m_index.ToUInt32 (layout_pos+4);` |
| `ArcIndexReader.ReadSection` | `entry.UnpackedSize = m_index.ToUInt32 (layout_pos+0xC);` |
| `ArcIndexReader.ReadDdsSection` | `int header_count = m_index.ToInt32 (layout_pos);` |
| `ArcIndexReader.ReadDdsSection` | `Width  = m_index.ToUInt32 (layout_pos+4),` |
| `ArcIndexReader.ReadDdsSection` | `Height = m_index.ToUInt32 (layout_pos+8),` |
| `ArcIndexReader.ReadDdsSection` | `Flags  = (DdsPF)m_index.ToUInt32 (layout_pos),` |
| `ArcIndexReader.ReadDdsSection` | `var name = ReadFileName (m_index.ToInt32 (name_pos));` |
| `ArcIndexReader.ReadDdsSection` | `entry.Offset = m_index.ToUInt32 (layout_pos) + m_base_offset;` |
| `ArcIndexReader.ReadDdsSection` | `entry.Size = m_index.ToUInt32 (layout_pos+4);` |
| `ArcIndexReader.ReadDdsSection` | `entry.UnpackedSize = m_index.ToUInt32 (layout_pos+0xC);` |
| `ArcIndexReader.ReadDdsSection` | `int header_id = m_index.ToInt32 (layout_pos+0x10);` |
| `ArcIndexReader.ReadOvaSection` | `int header_count = m_index.ToInt32 (layout_pos+4);` |
| `ArcIndexReader.ReadOvaSection` | `int header_len = m_index.ToInt32 (layout_pos+8);` |
| `ArcIndexReader.ReadOvaSection` | `var name = ReadFileName (m_index.ToInt32 (name_pos));` |
| `ArcIndexReader.ReadOvaSection` | `entry.Offset = m_index.ToUInt32 (layout_pos) + m_base_offset;` |
| `ArcIndexReader.ReadOvaSection` | `entry.UnpackedSize = m_index.ToUInt32 (layout_pos+4);` |
| `ArcIndexReader.ReadOvaSection` | `int header_id = m_index.ToInt32 (layout_pos+8);` |
| `ArcIndexReader.ReadChunk` | `int size = m_input.ReadInt32();` |
| `ArcIndexReader.ReadChunk` | `int type = m_input.ReadInt32();` |
| `ArcIndexReader.ReadChunk` | `int unpacked_size = m_input.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kogado.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var reader = new ArcIndexReader (file))
    {
        var dir = reader.ReadIndex();
        return new ArcFile(file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    input = new XoredStream (input, 0xFF);
    var ova = entry as OvaEntry;
    if (ova != null)
        return new PrefixStream (ova.Header, input);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new LimitStream (new LzssStream (input), pent.UnpackedSize);
}
```

### GameRes.Formats.Kogado.OvaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte[] Header ;
```

### GameRes.Formats.Kogado.DdsEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public DdsInfo Info ;
```

### GameRes.Formats.Kogado.DdsInfo

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public DdsPF    Flags ;
```

### GameRes.Formats.Kogado.ArcIndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

uint            m_base_offset ;

long            m_max_offset ;

byte[]  m_filenames ;

byte[]  m_index ;

List<Entry> m_dir ;

bool _disposed = false ;
```

#### ArcIndexReader

```csharp
public ArcIndexReader (ArcView arc) {
    m_base_offset = arc.View.ReadUInt32 (0xC);
    m_max_offset = arc.MaxOffset;
    m_input = arc.CreateStream();
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    m_input.Position = 0x10;
    m_filenames = ReadChunk();
    m_index = ReadChunk();
    m_dir = new List<Entry>();
    int section_count = m_index.ToInt32 (0);
    int pos = 4;
    for (int i = 0; i < section_count; ++i)
    {
        int count = m_index.ToInt32 (pos+8);
        if (m_dir.Capacity < m_dir.Count + count)
            m_dir.Capacity = m_dir.Count + count;
        int section_size = m_index.ToInt32 (pos+0xC);
        int name_pos = pos + 0x10;
        int layout_pos = name_pos + 4 * count;
        if (m_index.AsciiEqual (pos, "DDS\0"))
            ReadDdsSection (name_pos, layout_pos, count);
        else if (m_index.AsciiEqual (pos, "OVA\0"))
            ReadOvaSection (name_pos, layout_pos, count);
        else
            ReadSection (name_pos, layout_pos, count);
        pos += 0x10 + section_size;
    }
    return m_dir;
}
```

#### ReadSection

```csharp
void ReadSection (int name_pos, int layout_pos, int count) {
    for (int j = 0; j < count; ++j)
    {
        var name = ReadFileName (m_index.ToInt32 (name_pos));
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);

        entry.Offset = m_index.ToUInt32 (layout_pos) + m_base_offset;
        entry.Size = m_index.ToUInt32 (layout_pos+4);
        entry.UnpackedSize = m_index.ToUInt32 (layout_pos+0xC);
        entry.IsPacked = true;
        if (!entry.CheckPlacement (m_max_offset+0x14))
            throw new InvalidFormatException();

        m_dir.Add (entry);
        name_pos += 4;
        layout_pos += 0x10;
    }
}
```

#### ReadDdsSection

```csharp
void ReadDdsSection (int name_pos, int layout_pos, int count) {
    int header_count = m_index.ToInt32 (layout_pos);
    var headers = new DdsInfo[header_count];
    layout_pos += 4;
    for (int i = 0; i < header_count; ++i)
    {
        headers[i] = new DdsInfo {
            Width  = m_index.ToUInt32 (layout_pos+4),
            Height = m_index.ToUInt32 (layout_pos+8),
            BPP    = 32,
            Flags  = (DdsPF)m_index.ToUInt32 (layout_pos),
        };
        layout_pos += 0xC;
    }
    for (int j = 0; j < count; ++j)
    {
        var name = ReadFileName (m_index.ToInt32 (name_pos));
        var entry = FormatCatalog.Instance.Create<DdsEntry> (name);

        entry.Offset = m_index.ToUInt32 (layout_pos) + m_base_offset;
        entry.Size = m_index.ToUInt32 (layout_pos+4);
        entry.UnpackedSize = m_index.ToUInt32 (layout_pos+0xC);
        int header_id = m_index.ToInt32 (layout_pos+0x10);
        entry.Info = headers[header_id];
        entry.IsPacked = true;
        if (!entry.CheckPlacement (m_max_offset+0x14))
            throw new InvalidFormatException();

        m_dir.Add (entry);
        name_pos += 4;
        layout_pos += 0x14;
    }
}
```

#### ReadOvaSection

```csharp
void ReadOvaSection (int name_pos, int layout_pos, int count) {
    int header_count = m_index.ToInt32 (layout_pos+4);
    var headers = new byte[header_count][];
    layout_pos += 8;
    for (int i = 0; i < header_count; ++i)
    {
        int header_len = m_index.ToInt32 (layout_pos+8);
        int header_pos = layout_pos + 12;
        headers[i] = new CowArray<byte> (m_index, header_pos, header_len).ToArray();
        layout_pos = header_pos + header_len;
    }
    for (int j = 0; j < count; ++j)
    {
        var name = ReadFileName (m_index.ToInt32 (name_pos));
        var entry = FormatCatalog.Instance.Create<OvaEntry> (name);

        entry.Offset = m_index.ToUInt32 (layout_pos) + m_base_offset;
        entry.UnpackedSize = m_index.ToUInt32 (layout_pos+4);
        int header_id = m_index.ToInt32 (layout_pos+8);
        entry.Header = headers[header_id];
        entry.Size = entry.UnpackedSize - (uint)entry.Header.Length;
        entry.IsPacked = true;
        if (!entry.CheckPlacement (m_max_offset))
            throw new InvalidFormatException();

        m_dir.Add (entry);
        name_pos += 4;
        layout_pos += 0xC;
    }
}
```

#### ReadFileName

```csharp
string ReadFileName (int pos) {
    int i;
    for (i = pos; i+1 < m_filenames.Length; i += 2)
    {
        if (m_filenames[i] == 0 && m_filenames[i+1] == 0)
            break;
    }
    return Encoding.Unicode.GetString (m_filenames, pos, i - pos);
}
```

#### ReadChunk

```csharp
byte[] ReadChunk () {
    long start_pos = m_input.Position;
    int size = m_input.ReadInt32();
    int type = m_input.ReadInt32();
    int unpacked_size = m_input.ReadInt32();
    if (size <= 0 || unpacked_size <= 0)
        throw new InvalidFormatException();
    var data = new byte[unpacked_size];
    using (var decrypted = new XoredStream (m_input.AsStream, 0xFF, true))
    using (var lzss = new LzssStream (decrypted))
    {
        lzss.Read (data, 0, data.Length);
    }
    m_input.Position = start_pos + size;
    return data;
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kogado/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
