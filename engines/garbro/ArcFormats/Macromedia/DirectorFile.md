# Macromedia / DirectorFile：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DirectorFile.ReadAfterBurner` | `m_ilsMap[id] = ils_reader.ReadBytes ((int)chunk.Size);` |
| `CastMember.Deserialize` | `SpecificData = reader.ReadBytes (data_length);` |
| `CastInfo.Deserialize` | `Items.Add (reader.ReadBytes (next_offset - offset));` |
| `CastList.Deserialize` | `Items.Add (reader.ReadBytes (item_size));` |
| `CastList.Deserialize` | `entry.Flags = BigEndian.ToUInt16 (Items[item_idx + 3], 0);` |
| `CastList.Deserialize` | `entry.MinMember = BigEndian.ToUInt16 (Items[item_idx + 4], 0);` |
| `CastList.Deserialize` | `entry.MaxMember = BigEndian.ToUInt16 (Items[item_idx + 4], 2);` |
| `CastList.Deserialize` | `entry.Id        = BigEndian.ToInt32 (Items[item_idx + 4], 4);` |
| `Reader.SetByteOrder` | `ToU16 = () => LittleEndian.ToUInt16 (m_buffer, 0);` |
| `Reader.SetByteOrder` | `ToU32 = () => LittleEndian.ToUInt32 (m_buffer, 0);` |
| `Reader.SetByteOrder` | `ToU16 = () => BigEndian.ToUInt16 (m_buffer, 0);` |
| `Reader.SetByteOrder` | `ToU32 = () => BigEndian.ToUInt32 (m_buffer, 0);` |
| `Reader.ReadU8` | `int b = m_input.ReadByte();` |
| `Reader.ReadBytes` | `public byte[] ReadBytes (int length) {` |
| `Reader.ReadVarInt` | `int bits = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum ByteOrder
    {
        LittleEndian, BigEndian
    }

enum DataType
    {
        Null        = 0,
        Bitmap      = 1,
        FilmLoop    = 2,
        Text        = 3,
        Palette     = 4,
        Picture     = 5,
        Sound       = 6,
        Button      = 7,
        Shape       = 8,
        Movie       = 9,
        DigitalVideo = 10,
        Script      = 11,
        RTE         = 12,
    }
```

### GameRes.Formats.Macromedia.SerializationContext

#### 状态与常量

```csharp
public int          Version ;

public Encoding     Encoding ;
```

#### SerializationContext

```csharp
public SerializationContext () {
    Encoding = Encodings.cp932;
}
```

### GameRes.Formats.Macromedia.DirectorFile

#### 状态与常量

```csharp
List<DirectorEntry> m_dir ;

Dictionary<int, DirectorEntry> m_index = new Dictionary<int, DirectorEntry>() ;

MemoryMap       m_mmap = new MemoryMap() ;

KeyTable        m_keyTable = new KeyTable() ;

DirectorConfig  m_config = new DirectorConfig() ;

List<Cast>      m_casts = new List<Cast>() ;

Dictionary<int, byte[]> m_ilsMap = new Dictionary<int, byte[]>() ;

string          m_codec ;

public string Codec => m_codec;

public bool IsAfterBurned { get; private set; }

public MemoryMap        MMap => m_mmap;

public KeyTable     KeyTable => m_keyTable;

public DirectorConfig Config => m_config;

public List<Cast>      Casts => m_casts;

public List<DirectorEntry>            Directory => m_dir;

public Dictionary<int, DirectorEntry> Index => m_index;
```

#### Find

```csharp
public DirectorEntry Find (string four_cc) => Directory.Find (e => e.FourCC == four_cc);
```

#### FindById

```csharp
public DirectorEntry FindById (int id) {
    DirectorEntry entry;
    m_index.TryGetValue (id, out entry);
    return entry;
}
```

#### Deserialize

```csharp
public bool Deserialize (SerializationContext context, Reader reader) {
    reader.Skip (8);
    m_codec = reader.ReadFourCC();
    if (m_codec == "MV93" || m_codec == "MC95")
    {
        if (!ReadMMap (context, reader))
            return false;
    }
    else if (m_codec == "FGDC" || m_codec == "FGDM")
    {
        IsAfterBurned = true;
        if (!ReadAfterBurner (context, reader))
            return false;
    }
    else
    {
        Trace.WriteLine (string.Format ("Unknown m_codec '{0}'", m_codec), "DXR");
        return false;
    }
    return ReadKeyTable (context, reader)
        && ReadConfig (context, reader)
        && ReadCasts (context, reader);
}
```

#### ReadMMap

```csharp
internal bool ReadMMap (SerializationContext context, Reader reader) {
    if (reader.ReadFourCC() != "imap")
        return false;
    reader.Skip (8);
    uint mmap_pos = reader.ReadU32();
    reader.Position = mmap_pos;
    if (reader.ReadFourCC() != "mmap")
        return false;
    reader.Position = mmap_pos + 8;
    MMap.Deserialize (context, reader);
    m_dir = MMap.Dir;
    for (int i = 0; i < m_dir.Count; ++i)
    {
        m_index[i] = m_dir[i];
    }
    return true;
}
```

#### ReadAfterBurner

```csharp
bool ReadAfterBurner (SerializationContext context, Reader reader) {
    if (reader.ReadFourCC() != "Fver")
        return false;
    int length = reader.ReadVarInt();
    long next_pos = reader.Position + length;
    int version = reader.ReadVarInt();
    if (version > 0x400)
    {
        reader.ReadVarInt();
        reader.ReadVarInt();
    }
    if (version > 0x500)
    {
        int str_len = reader.ReadU8();
        reader.Skip (str_len);
    }

    reader.Position = next_pos;
    if (reader.ReadFourCC() != "Fcdr")
        return false;

    length = reader.ReadVarInt();

    reader.Position += length;
    if (reader.ReadFourCC() != "ABMP")
        return false;
    length = reader.ReadVarInt();
    next_pos = reader.Position + length;
    reader.ReadVarInt();
    int unpacked_size = reader.ReadVarInt();
    using (var abmp = new ZLibStream (reader.Source, CompressionMode.Decompress, true))
    {
        var abmp_reader = new Reader (abmp, reader.ByteOrder);
        if (!ReadABMap (context, abmp_reader))
            return false;
    }

    reader.Position = next_pos;
    if (reader.ReadFourCC() != "FGEI")
        return false;
    reader.ReadVarInt();
    long base_offset = reader.Position;
    foreach (var entry in m_dir)
    {
        m_index[entry.Id] = entry;
        if (entry.Offset >= 0)
            entry.Offset += base_offset;
    }
    var ils_chunk = FindById (2);
    if (null == ils_chunk)
        return false;
    using (var ils = new ZLibStream (reader.Source, CompressionMode.Decompress, true))
    {
        uint pos = 0;
        var ils_reader = new Reader (ils, reader.ByteOrder);
        while (pos < ils_chunk.UnpackedSize)
        {
            int id = ils_reader.ReadVarInt();
            var chunk = m_index[id];
            m_ilsMap[id] = ils_reader.ReadBytes ((int)chunk.Size);
            pos += ils_reader.GetVarIntLength ((uint)id) + chunk.Size;
        }
    }
    return true;
}
```

#### ReadABMap

```csharp
bool ReadABMap (SerializationContext context, Reader reader) {
    reader.ReadVarInt();
    reader.ReadVarInt();
    int count = reader.ReadVarInt();
    m_dir = new List<DirectorEntry> (count);
    for (int i = 0; i < count; ++ i)
    {
        var entry = new AfterBurnerEntry();
        entry.Deserialize (context, reader);
        m_dir.Add (entry);
    }
    return true;
}
```

#### GetChunkReader

```csharp
Reader GetChunkReader (DirectorEntry chunk, Reader reader) {
    if (-1 == chunk.Offset)
    {
        byte[] chunk_data;
        if (!m_ilsMap.TryGetValue (chunk.Id, out chunk_data))
            throw new InvalidFormatException (string.Format ("Can't find chunk {0} in ILS", chunk.FourCC));
        var input = new BinMemoryStream (chunk_data, null);
        reader = new Reader (input, reader.ByteOrder);
    }
    else
    {
        reader.Position = chunk.Offset;
    }
    return reader;
}
```

#### ReadKeyTable

```csharp
bool ReadKeyTable (SerializationContext context, Reader reader) {
    var key_chunk = Find ("KEY*");
    if (null == key_chunk)
        return false;
    reader = GetChunkReader (key_chunk, reader);
    KeyTable.Deserialize (context, reader);
    return true;
}
```

#### ReadConfig

```csharp
bool ReadConfig (SerializationContext context, Reader reader) {
    var config_chunk = Find ("VWCF") ?? Find ("DRCF");
    if (null == config_chunk)
        return false;
    reader = GetChunkReader (config_chunk, reader);
    Config.Deserialize (context, reader);
    context.Version = Config.Version;
    return true;
}
```

#### ReadCasts

```csharp
bool ReadCasts (SerializationContext context, Reader reader) {
    Reader cas_reader;
    if (context.Version > 1200)
    {
        var mcsl = Find ("MCsL");
        if (mcsl != null)
        {
            var mcsl_reader = GetChunkReader (mcsl, reader);
            var cast_list = new CastList();
            cast_list.Deserialize (context, mcsl_reader);
            foreach (var entry in cast_list.Entries)
            {
                var key_entry = KeyTable.FindByCast (entry.Id, "CAS*");
                if (key_entry != null)
                {
                    var cas_entry = Index[key_entry.Id];
                    cas_reader = GetChunkReader (cas_entry, reader);
                    var cast = new Cast (context, cas_reader, cas_entry);
                    if (!PopulateCast (cast, context, reader, entry))
                        return false;
                    Casts.Add (cast);
                }
            }
            return true;
        }
    }
    var cas_chunk = Find ("CAS*");
    if (null == cas_chunk)
        return false;
    var new_entry = new CastListEntry { Name = "internal", Id = 0x400, MinMember = Config.MinMember };
    cas_reader = GetChunkReader (cas_chunk, reader);
    var new_cast = new Cast (context, cas_reader, cas_chunk);
    if (!PopulateCast (new_cast, context, reader, new_entry))
        return false;
    Casts.Add (new_cast);
    return true;
}
```

#### PopulateCast

```csharp
public bool PopulateCast (Cast cast, SerializationContext context, Reader reader, CastListEntry entry) {
    cast.Name = entry.Name;
    for (int i = 0; i < cast.Index.Length; ++i)
    {
        int chunk_id = cast.Index[i];
        if (chunk_id > 0)
        {
            var chunk = this.Index[chunk_id];
            var member = new CastMember();
            member.Id = chunk_id;
            var cast_reader = GetChunkReader (chunk, reader);
            member.Deserialize (context, cast_reader);
            cast.Members[member.Id] = member;
        }
    }
    return true;
}
```

### GameRes.Formats.Macromedia.CastMember

#### 状态与常量

```csharp
public DataType     Type ;

public CastInfo     Info = new CastInfo() ;

public byte[]       SpecificData ;

public byte         Flags ;

public int          Id ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    reader = reader.CloneUnless (ByteOrder.BigEndian);
    if (context.Version > 1200)
    {
        Type = (DataType)reader.ReadI32();
        int info_length = reader.ReadI32();
        int data_length = reader.ReadI32();
        if (info_length > 0)
        {
            Info.Deserialize (context, reader);
        }
        SpecificData = reader.ReadBytes (data_length);
    }
    else
    {
        int data_length = reader.ReadU16();
        int info_length = reader.ReadI32();
        Type = (DataType)reader.ReadU8();
        --data_length;
        if (data_length > 0)
        {
            Flags = reader.ReadU8();
            --data_length;
        }
        SpecificData = reader.ReadBytes (data_length);
        if (info_length > 0)
        {
            Info.Deserialize (context, reader);
        }
    }
}
```

### GameRes.Formats.Macromedia.CastInfo

#### 状态与常量

```csharp
public uint     DataOffset ;

public uint     ScriptKey ;

public uint     Flags ;

public int      ScriptId ;

public string   Name ;

public string   SourceText ;

public List<byte[]> Items = new List<byte[]>() ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    long base_offset = reader.Position;
    DataOffset = reader.ReadU32();
    ScriptKey = reader.ReadU32();
    reader.Skip (4);
    Flags = reader.ReadU32();
    ScriptId = reader.ReadI32();
    reader.Position = base_offset + DataOffset;
    int table_len = reader.ReadU16();
    var offsets = new int[table_len];
    for (int i = 0; i < table_len; ++i)
        offsets[i] = reader.ReadI32();

    int data_length = reader.ReadI32();
    long list_offset = reader.Position;
    Items.Clear();
    Items.Capacity = offsets.Length;
    for (int i = 0; i < offsets.Length; ++i)
    {
        int offset = offsets[i];
        int next_offset = (i + 1 < offsets.Length) ? offsets[i+1] : data_length;
        reader.Position = list_offset + offset;
        Items.Add (reader.ReadBytes (next_offset - offset));
    }

    SourceText = Items.Count > 0 ? Binary.GetCString (Items[0], 0) : string.Empty;
    Name = GetString (1, context.Encoding);
}
```

#### GetString

```csharp
string GetString (int item_idx, Encoding enc) {
    if (item_idx >= Items.Count)
        return string.Empty;
    var src = Items[item_idx];
    if (src.Length <= 1 || 0 == src[0])
        return string.Empty;
    int len = src[0];
    return enc.GetString (src, 1, len);
}
```

### GameRes.Formats.Macromedia.Cast

#### 状态与常量

```csharp
public int[]    Index ;

public string   Name ;

public Dictionary<int, CastMember> Members = new Dictionary<int, CastMember>() ;
```

#### Cast

```csharp
public Cast (SerializationContext context, Reader reader, DirectorEntry entry) {
    int count = (int)(entry.Size / 4);
    Index = new int[count];
    Deserialize (context, reader);
}
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    reader = reader.CloneUnless (ByteOrder.BigEndian);
    for (int i = 0; i < Index.Length; ++i)
        Index[i] = reader.ReadI32();
}
```

### GameRes.Formats.Macromedia.CastList

#### 状态与常量

```csharp
public uint DataOffset ;

public int OffsetCount ;

public int[] OffsetTable ;

public int ItemsLength ;

public int CastCount ;

public int ItemsPerCast ;

public List<byte[]> Items = new List<byte[]>() ;

public readonly List<CastListEntry> Entries = new List<CastListEntry>() ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    long base_offset = reader.Position;
    reader = reader.CloneUnless (ByteOrder.BigEndian);
    DataOffset = reader.ReadU32();
    reader.Skip (2);
    CastCount = reader.ReadU16();
    ItemsPerCast = reader.ReadU16();
    reader.Skip (2);
    reader.Position = base_offset + DataOffset;
    OffsetCount = reader.ReadU16();
    OffsetTable = new int[OffsetCount];
    for (int i = 0; i < OffsetCount; ++i)
    {
        OffsetTable[i] = reader.ReadI32();
    }
    ItemsLength = reader.ReadI32();
    long items_offset = reader.Position;
    Items.Clear();
    Items.Capacity = OffsetCount;
    for (int i = 0; i < OffsetCount; ++i)
    {
        int offset = OffsetTable[i];
        int next_offset = (i + 1 < OffsetCount) ? OffsetTable[i + 1] : ItemsLength;
        int item_size = next_offset - offset;
        Items.Add (reader.ReadBytes (item_size));
    }

    Entries.Clear();
    Entries.Capacity = CastCount;
    int item_idx = 0;
    for (int i = 0; i < CastCount; ++i)
    {
        var entry = new CastListEntry();
        if (ItemsPerCast >= 1)
            entry.Name = GetString (item_idx + 1, context.Encoding);
        if (ItemsPerCast >= 2)
            entry.Path = GetString (item_idx + 2, context.Encoding);
        if (ItemsPerCast >= 3 && Items[item_idx + 3].Length >= 2)
            entry.Flags = BigEndian.ToUInt16 (Items[item_idx + 3], 0);
        if (ItemsPerCast >= 4 && Items[item_idx + 4].Length >= 8)
        {
            entry.MinMember = BigEndian.ToUInt16 (Items[item_idx + 4], 0);
            entry.MaxMember = BigEndian.ToUInt16 (Items[item_idx + 4], 2);
            entry.Id        = BigEndian.ToInt32 (Items[item_idx + 4], 4);
        }
        Entries.Add (entry);
    }
}
```

#### GetString

```csharp
string GetString (int item_idx, Encoding enc) {
    var src = Items[item_idx];
    if (src.Length <= 1 || 0 == src[0])
        return string.Empty;
    int len = src[0];
    return enc.GetString (src, 1, len);
}
```

### GameRes.Formats.Macromedia.CastListEntry

#### 状态与常量

```csharp
public string   Name ;

public string   Path ;

public ushort   Flags ;

public int      MinMember ;

public int      MaxMember ;

public int      Id ;
```

### GameRes.Formats.Macromedia.DirectorConfig

#### 状态与常量

```csharp
public short Length ;

public short FileVersion ;

public short StageTop ;

public short StageLeft ;

public short StageBottom ;

public short StageRight ;

public short MinMember ;

public short MaxMember ;

public ushort StageColor ;

public ushort BitDepth ;

public int Version ;

public int FrameRate ;

public int Platform ;

public int Protection ;

public uint CheckSum ;

public int DefaultPalette ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    long base_offset = reader.Position;
    reader = reader.CloneUnless (ByteOrder.BigEndian);

    reader.Position = base_offset + 0x24;
    Version = reader.ReadU16();
    reader.Position = base_offset;
    Length = reader.ReadI16();
    FileVersion = reader.ReadI16();
    StageTop = reader.ReadI16();
    StageLeft = reader.ReadI16();
    StageBottom = reader.ReadI16();
    StageRight = reader.ReadI16();
    MinMember = reader.ReadI16();
    MaxMember = reader.ReadI16();
    reader.Skip (0x0A);
    StageColor = reader.ReadU16();
    BitDepth = reader.ReadU16();
    reader.Skip (0x18);
    FrameRate = reader.ReadU16();
    Platform = reader.ReadI16();
    Protection = reader.ReadI16();
    reader.Skip (4);
    CheckSum = reader.ReadU32();
    if (Version > 1200)
    {
        reader.Position = base_offset + 0x4E;
    }
    else
    {
        reader.Position = base_offset + 0x46;
    }
    DefaultPalette = reader.ReadU16();
}
```

### GameRes.Formats.Macromedia.KeyTable

#### 状态与常量

```csharp
public int  EntrySize ;

public int  TotalCount ;

public int  UsedCount ;

public readonly List<KeyTableEntry> Table = new List<KeyTableEntry>() ;
```

#### FindByCast

```csharp
public KeyTableEntry FindByCast (int cast_id, string four_cc) {
    return Table.Find (e => e.CastId == cast_id && e.FourCC == four_cc);
}
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    EntrySize = reader.ReadU16();
    reader.Skip(2);
    TotalCount = reader.ReadI32();
    UsedCount = reader.ReadI32();

    Table.Clear();
    Table.Capacity = TotalCount;
    for (int i = 0; i < TotalCount; ++i)
    {
        var entry = new KeyTableEntry();
        entry.Deserialize (context, reader);
        Table.Add (entry);
    }
}
```

### GameRes.Formats.Macromedia.KeyTableEntry

#### 状态与常量

```csharp
public int      Id ;

public int      CastId ;

public string   FourCC ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader input) {
    Id     = input.ReadI32();
    CastId = input.ReadI32();
    FourCC = input.ReadFourCC();
}
```

### GameRes.Formats.Macromedia.MemoryMap

#### 状态与常量

```csharp
public ushort   HeaderLength ;

public ushort   EntryLength ;

public int      ChunkCountMax ;

public int      ChunkCountUsed ;

public int      FreeHead ;

public readonly List<DirectorEntry> Dir = new List<DirectorEntry>() ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    long header_pos = reader.Position;
    HeaderLength = reader.ReadU16();
    if (HeaderLength < 0x18)
        throw new InvalidFormatException ("Invalid <mmap> header length.");
    EntryLength = reader.ReadU16();
    if (EntryLength < 0x14)
        throw new InvalidFormatException ("Invalid <mmap> entry length.");
    ChunkCountMax = reader.ReadI32();
    ChunkCountUsed = reader.ReadI32();
    reader.Skip (8);
    FreeHead = reader.ReadI32();

    Dir.Clear();
    Dir.Capacity = ChunkCountUsed;
    long entry_pos = header_pos + HeaderLength;
    for (int i = 0; i < ChunkCountUsed; ++i)
    {
        reader.Position = entry_pos;
        var entry = new MemoryMapEntry (i);
        entry.Deserialize (context, reader);
        Dir.Add (entry);
        entry_pos += EntryLength;
    }
}
```

### GameRes.Formats.Macromedia.DirectorEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int      Id ;

public string   FourCC ;
```

### GameRes.Formats.Macromedia.MemoryMapEntry

继承/接口：`DirectorEntry`。

#### 状态与常量

```csharp
public ushort   Flags ;
```

#### MemoryMapEntry

```csharp
public MemoryMapEntry (int id = 0) {
    Id = id;
}
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    FourCC = reader.ReadFourCC();
    Size   = reader.ReadU32();
    Offset = reader.ReadU32() + 8;
    Flags  = reader.ReadU16();
    reader.ReadI32();
    UnpackedSize = Size;
    IsPacked = false;
}
```

### GameRes.Formats.Macromedia.AfterBurnerEntry

继承/接口：`DirectorEntry`。

#### 状态与常量

```csharp
public int      CompMethod ;
```

#### Deserialize

```csharp
public void Deserialize (SerializationContext context, Reader reader) {
    Id           = reader.ReadVarInt();
    Offset       = reader.ReadVarInt();
    Size         = (uint)reader.ReadVarInt();
    UnpackedSize = (uint)reader.ReadVarInt();
    CompMethod   = reader.ReadVarInt();
    FourCC       = reader.ReadFourCC();
    IsPacked     = Size != UnpackedSize;
}
```

### GameRes.Formats.Macromedia.Reader

#### 状态与常量

```csharp
Stream      m_input ;

byte[]      m_buffer = new byte[4] ;

public Stream Source => m_input;

public ByteOrder ByteOrder { get; private set; }

public Encoding Encoding { get; set; }

public long Position {
    get => m_input.Position;
    set => m_input.Position = value;
}

private Func<ushort> ToU16 ;

private Func<uint>   ToU32 ;

static Dictionary<uint, string> KnownFourCC = new Dictionary<uint, string>() ;
```

#### Reader

```csharp
public Reader (Stream input, Encoding enc, ByteOrder e = ByteOrder.LittleEndian) {
    m_input = input;
    Encoding = enc;
    SetByteOrder (e);
}
```

#### SetByteOrder

```csharp
public void SetByteOrder (ByteOrder e) {
    this.ByteOrder = e;
    if (ByteOrder.LittleEndian == e)
    {
        ToU16 = () => LittleEndian.ToUInt16 (m_buffer, 0);
        ToU32 = () => LittleEndian.ToUInt32 (m_buffer, 0);
    }
    else
    {
        ToU16 = () => BigEndian.ToUInt16 (m_buffer, 0);
        ToU32 = () => BigEndian.ToUInt32 (m_buffer, 0);
    }
}
```

#### ReadFourCC

```csharp
public string ReadFourCC () {
    uint signature = ReadU32();
    string four_cc;
    if (KnownFourCC.TryGetValue (signature, out four_cc))
        return four_cc;
    BigEndian.Pack (signature, m_buffer, 0);
    return KnownFourCC[signature] = Encoding.GetString (m_buffer, 0, 4);
}
```

#### Skip

```csharp
public void Skip (int amount) => m_input.Seek (amount, SeekOrigin.Current);
```

#### ReadU8

```csharp
public byte ReadU8 () {
    int b = m_input.ReadByte();
    if (-1 == b)
        throw new EndOfStreamException();
    return (byte)b;
}
```

#### ReadI8

```csharp
public sbyte ReadI8 () => (sbyte)ReadU8();
```

#### ReadU16

```csharp
public ushort ReadU16 () {
    if (m_input.Read (m_buffer, 0, 2) < 2)
        throw new EndOfStreamException();
    return ToU16();
}
```

#### ReadI16

```csharp
public short ReadI16 () => (short)ReadU16();
```

#### ReadU32

```csharp
public uint ReadU32 () {
    if (m_input.Read (m_buffer, 0, 4) < 4)
        throw new EndOfStreamException();
    return ToU32();
}
```

#### ReadI32

```csharp
public int ReadI32 () => (int)ReadU32();
```

#### ReadBytes

```csharp
public byte[] ReadBytes (int length) {
    if (0 == length)
        return Array.Empty<byte>();
    var buffer = new byte[length];
    if (m_input.Read (buffer, 0, length) < length)
        throw new EndOfStreamException();
    return buffer;
}
```

#### ReadVarInt

```csharp
public int ReadVarInt () {
    int n = 0;
    for (int i = 0; i < 5; ++i)
    {
        int bits = m_input.ReadByte();
        if (-1 == bits)
            throw new EndOfStreamException();
        n = n << 7 | bits & 0x7F;
        if (0 == (bits & 0x80))
            return n;
    }
    throw new InvalidFormatException();
}
```

#### GetVarIntLength

```csharp
public uint GetVarIntLength (uint i) {
    uint n = 1;
    while (i > 0x7F)
    {
        i >>= 7;
        ++n;
    }
    return n;
}
```

#### CloneUnless

```csharp
public Reader CloneUnless (ByteOrder order) {
    if (this.ByteOrder != order)
        return new Reader (this.Source, this.Encoding, order);
    else
        return this;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Macromedia/DirectorFile.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
