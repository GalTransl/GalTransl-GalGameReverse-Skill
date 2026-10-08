# Emote / ArcPSB：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PSB/EMOTE` / `GameRes.Formats.Emote.PsbOpener` | `psb`, `pimg`, `dpak`, `psbz`, `psp` | `50534200` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PsbReader.Parse` | `if (!ReadHeader (encrypted))` |
| `PsbReader.GetLayers` | `OffsetX     = Convert.ToInt32 (layer["left"]),` |
| `PsbReader.GetLayers` | `OffsetY     = Convert.ToInt32 (layer["top"]),` |
| `PsbReader.GetLayers` | `Width       = Convert.ToInt32 (layer["width"]),` |
| `PsbReader.GetLayers` | `Height      = Convert.ToInt32 (layer["height"]),` |
| `PsbReader.AddTextureEntry` | `Width           = Convert.ToInt32 (texture["width"]),` |
| `PsbReader.AddTextureEntry` | `Height          = Convert.ToInt32 (texture["height"]),` |
| `PsbReader.AddTextureEntry` | `TruncatedWidth  = Convert.ToInt32 (texture["truncated_width"]),` |
| `PsbReader.AddTextureEntry` | `TruncatedHeight = Convert.ToInt32 (texture["truncated_height"]),` |
| `PsbReader.AddIconEntry` | `Width       = Convert.ToInt32 (layer["width"]),` |
| `PsbReader.AddIconEntry` | `Height      = Convert.ToInt32 (layer["height"]),` |
| `PsbReader.AddIconEntry` | `OffsetX     = Convert.ToInt32 (layer["originX"]),` |
| `PsbReader.AddIconEntry` | `OffsetY     = Convert.ToInt32 (layer["originY"]),` |
| `PsbReader.ReadHeader` | `bool ReadHeader (bool encrypted) {` |
| `PsbReader.ReadHeader` | `m_version = m_input.ReadUInt16();` |
| `PsbReader.ReadHeader` | `m_flags = m_input.ReadUInt16();` |
| `PsbReader.ReadHeader` | `var header = m_input.ReadBytes (header_size);` |
| `PsbReader.ReadHeader` | `m_names         = LittleEndian.ToInt32 (header, 0x04);` |
| `PsbReader.ReadHeader` | `m_strings       = LittleEndian.ToInt32 (header, 0x08);` |
| `PsbReader.ReadHeader` | `m_strings_data  = LittleEndian.ToInt32 (header, 0x0C);` |
| `PsbReader.ReadHeader` | `m_chunk_offsets = LittleEndian.ToInt32 (header, 0x10);` |
| `PsbReader.ReadHeader` | `m_chunk_lengths = LittleEndian.ToInt32 (header, 0x14);` |
| `PsbReader.ReadHeader` | `m_chunk_data    = LittleEndian.ToInt32 (header, 0x18);` |
| `PsbReader.ReadHeader` | `m_root          = LittleEndian.ToInt32 (header, 0x1C);` |
| `PsbReader.ReadHeader` | `m_extra_offsets = LittleEndian.ToInt32 (header, 0x24);` |
| `PsbReader.ReadHeader` | `m_extra_lengths = LittleEndian.ToInt32 (header, 0x28);` |
| `PsbReader.ReadHeader` | `m_extra_data    = LittleEndian.ToInt32 (header, 0x2C);` |
| `PsbReader.GetArrayElem` | `return LittleEndian.ToUInt16 (m_data, a1.DataOffset + offset);` |
| `PsbReader.GetArrayElem` | `return LittleEndian.ToUInt16 (m_data, a1.DataOffset + offset) \| m_data[a1.DataOffset + offset + 2] << 16;` |
| `PsbReader.GetArrayElem` | `return LittleEndian.ToInt32 (m_data, a1.DataOffset + offset);` |
| `PsbReader.GetInteger` | `case 2: return LittleEndian.ToUInt16 (m_data, offset+1);` |
| `PsbReader.GetInteger` | `case 3: return LittleEndian.ToUInt16 (m_data, offset+1) \| m_data[offset+3] << 16;` |
| `PsbReader.GetInteger` | `case 4: return LittleEndian.ToInt32 (m_data, offset+1);` |
| `PsbReader.GetLong` | `case 0x09:  return LittleEndian.ToUInt32 (m_data, offset+1) \| (long)(sbyte)m_data[offset+5] << 32;` |
| `PsbReader.GetLong` | `case 0x0A:  return LittleEndian.ToUInt32 (m_data, offset+1)` |
| `PsbReader.GetLong` | `\| (long)LittleEndian.ToInt16 (m_data, offset+5) << 32;` |
| `PsbReader.GetLong` | `case 0x0B:  return LittleEndian.ToUInt32 (m_data, offset+1)` |
| `PsbReader.GetLong` | `\| (long)LittleEndian.ToUInt16 (m_data, offset+5) << 32` |
| `PsbReader.GetLong` | `case 0x0C:  return LittleEndian.ToInt64 (m_data, offset+1);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Emote.TexEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public string   TexType ;

public int      Width ;

public int      Height ;

public int      TruncatedWidth ;

public int      TruncatedHeight ;

public int      OffsetX ;

public int      OffsetY ;
```

### GameRes.Formats.Emote.PsbOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static uint[] KnownKeys = new uint[] { 970396437u }

ImageFormat TlgFormat { get { return s_TlgFormat.Value; } }

static ResourceInstance<ImageFormat> s_TlgFormat = new ResourceInstance<ImageFormat> ("TLG") ;
```

#### PsbOpener

```csharp
public PsbOpener () {
    Extensions = new string[] { "psb", "pimg", "dpak", "psbz", "psp" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var input = file.CreateStream())
    using (var reader = new PsbReader (input))
    {
        foreach (var key in KnownKeys)
        {
            try
            {
                if (reader.Parse (key))
                    return OpenArcFile (reader, file);
                if (!reader.IsEncrypted)
                    break;
            }
            catch {  }
        }
        if (reader.ParseNonEncrypted())
            return OpenArcFile (reader, file);
        return null;
    }
}
```

#### OpenArcFile

```csharp
ArcFile OpenArcFile (PsbReader reader, ArcView file) {
    var dir = reader.GetTextures();
    if (null == dir)
        dir = reader.GetLayers();
    if (null == dir)
        dir = reader.GetChunks();
    if (null == dir || 0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Emote.PsbReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream       m_input ;

public int      Version { get { return m_version; } }

public bool IsEncrypted { get { return 0 != (m_flags & 3); } }

public int   DataOffset { get { return m_chunk_data; } }

int m_version ;

int m_flags ;

uint[] m_key = new uint[6] ;

Dictionary<int, string> m_name_map ;

int m_names ;

int m_strings ;

int m_strings_data ;

int m_chunk_offsets ;

int m_chunk_lengths ;

int m_chunk_data ;

int m_extra_offsets ;

int m_extra_lengths ;

int m_extra_data ;

int m_root ;

byte[] m_data ;
```

#### PsbReader

```csharp
public PsbReader (IBinaryStream input) {
    m_input = input;
}
```

#### ParseNonEncrypted

```csharp
public bool ParseNonEncrypted () {
    return Parse (false);
}
```

#### Parse

```csharp
public bool Parse (uint key) {
    m_key[0] = 0x075BCD15;
    m_key[1] = 0x159A55E5;
    m_key[2] = 0x1F123BB5;
    m_key[3] = key;
    m_key[4] = 0;
    m_key[5] = 0;

    return Parse (true);
}
```

#### Parse

```csharp
bool Parse (bool encrypted) {
    if (!ReadHeader (encrypted))
        return false;
    if (Version < 2)
        throw new NotSupportedException ("Not supported PSB version");
    m_name_map = ReadNames();

    var dict = GetDict (m_root);

    return true;
}
```

#### GetLayers

```csharp
public List<Entry> GetLayers () {
    var layers = GetRootKey<IList> ("layers");
    if (null == layers || 0 == layers.Count)
        return null;
    var dir = new List<Entry> (layers.Count);
    foreach (IDictionary layer in layers)
    {
        var name = layer["layer_id"].ToString() + ".tlg";
        var layer_data = GetRootKey<EmChunk> (name);
        if (null == layer_data)
            continue;
        var entry = new TexEntry {
            Name        = name,
            Type        = "image",
            Offset      = DataOffset + layer_data.Offset,
            Size        = (uint)layer_data.Length,
            TexType     = "TLG",
            OffsetX     = Convert.ToInt32 (layer["left"]),
            OffsetY     = Convert.ToInt32 (layer["top"]),
            Width       = Convert.ToInt32 (layer["width"]),
            Height      = Convert.ToInt32 (layer["height"]),
        };
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    return dir;
}
```

#### GetTextures

```csharp
public List<Entry> GetTextures () {
    var source = GetRootKey<IDictionary> ("source");
    if (null == source || 0 == source.Count)
        return null;
    var dir = new List<Entry> (source.Count);
    foreach (DictionaryEntry item in source)
    {
        var item_value = item.Value as IDictionary;
        if (null == item_value)
            continue;
        if (item_value.Contains ("texture"))
        {
            AddTextureEntry (dir, item.Key, item_value["texture"] as IDictionary);
        }
        else if (item_value.Contains ("icon"))
        {
            AddIconEntry (dir, item.Key, item_value["icon"] as IDictionary);
        }
    }
    return dir;
}
```

#### GetChunks

```csharp
public List<Entry> GetChunks () {
    var dict = GetDict (m_root);
    if (0 == dict.Count)
        return null;
    var dir = new List<Entry> (dict.Count);
    foreach (DictionaryEntry item in dict)
    {
        var name = item.Key.ToString();
        var data = item.Value as EmChunk;
        if (string.IsNullOrEmpty (name) || null == data)
            continue;
        var entry = new Entry {
            Name   = name,
            Type   = FormatCatalog.Instance.GetTypeFromName (name),
            Offset = DataOffset + data.Offset,
            Size   = (uint)data.Length,
        };
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    return dir;
}
```

#### AddTextureEntry

```csharp
void AddTextureEntry (List<Entry> dir, object name, IDictionary texture) {
    if (null == texture)
        return;
    var pixel = texture["pixel"] as EmChunk;
    if (null == pixel)
        return;
    var entry = new TexEntry {
        Name            = name.ToString(),
        Type            = "image",
        Offset          = DataOffset + pixel.Offset,
        Size            = (uint)pixel.Length,
        TexType         = texture["type"].ToString(),
        Width           = Convert.ToInt32 (texture["width"]),
        Height          = Convert.ToInt32 (texture["height"]),
        TruncatedWidth  = Convert.ToInt32 (texture["truncated_width"]),
        TruncatedHeight = Convert.ToInt32 (texture["truncated_height"]),
    };
    dir.Add (entry);
}
```

#### AddIconEntry

```csharp
void AddIconEntry (List<Entry> dir, object name, IDictionary icon_list) {
    if (null == icon_list)
        return;
    foreach (DictionaryEntry icon in icon_list)
    {
        var layer = icon.Value as IDictionary;
        var pixel = layer["pixel"] as EmChunk;
        if (null == pixel)
            continue;
        var entry = new TexEntry {
            Name        = name.ToString()+'#'+icon.Key.ToString(),
            Type        = "image",
            Offset      = DataOffset + pixel.Offset,
            Size        = (uint)pixel.Length,
            Width       = Convert.ToInt32 (layer["width"]),
            Height      = Convert.ToInt32 (layer["height"]),
            OffsetX     = Convert.ToInt32 (layer["originX"]),
            OffsetY     = Convert.ToInt32 (layer["originY"]),
            TexType     = layer.Contains ("compress") ? layer["compress"].ToString() : "RGBA8",
        };
        entry.TruncatedWidth = entry.Width;
        entry.TruncatedHeight = entry.Height;
        dir.Add (entry);
    }
}
```

#### ReadHeader

```csharp
bool ReadHeader (bool encrypted) {
    m_input.Position = 4;

    m_version = m_input.ReadUInt16();
    m_flags = m_input.ReadUInt16();
    if (encrypted && m_version < 3)
        m_flags = 2;

    int header_size = m_version > 3 ? 0x30 : 0x20;
    var header = m_input.ReadBytes (header_size);
    if (encrypted && 0 != (m_flags & 1))
    {
        if (m_version > 3)
        {
            Decrypt (header, 0, 0x24);
            Decrypt (header, 0x24, 0xC);
        }
        else
            Decrypt (header, 0, 0x20);
    }

    m_names         = LittleEndian.ToInt32 (header, 0x04);
    m_strings       = LittleEndian.ToInt32 (header, 0x08);
    m_strings_data  = LittleEndian.ToInt32 (header, 0x0C);
    m_chunk_offsets = LittleEndian.ToInt32 (header, 0x10);
    m_chunk_lengths = LittleEndian.ToInt32 (header, 0x14);
    m_chunk_data    = LittleEndian.ToInt32 (header, 0x18);
    m_root          = LittleEndian.ToInt32 (header, 0x1C);

    if (m_version > 3)
    {
        m_extra_offsets = LittleEndian.ToInt32 (header, 0x24);
        m_extra_lengths = LittleEndian.ToInt32 (header, 0x28);
        m_extra_data    = LittleEndian.ToInt32 (header, 0x2C);
    }

    int buffer_length = (int)m_input.Length;
    if (!(m_names           >= 0x28 && m_names < m_chunk_data
          && m_strings      >= 0x28 && m_strings < m_chunk_data
          && m_strings_data >= 0x28 && m_strings_data < m_chunk_data
          && m_chunk_offsets >= 0x28 && m_chunk_offsets < m_chunk_data
          && m_chunk_lengths >= 0x28 && m_chunk_lengths < m_chunk_data
          && m_chunk_data   >= 0x28 && m_chunk_data <= buffer_length
          && m_root         >= 0x28 && m_root < m_chunk_data))
        return false;

    if (null == m_data || m_data.Length < m_chunk_data)
        m_data = new byte[m_chunk_data];
    int data_pos = (int)m_input.Position;
    m_input.Read (m_data, data_pos, m_chunk_data-data_pos);
    if (encrypted && 0 != (m_flags & 2))
        Decrypt (m_data, m_names, m_chunk_offsets-m_names);

    return 0x21 == m_data[m_root];
}
```

#### GetKey

```csharp
bool GetKey (string name, int dict_offset, out int value_offset) {
    value_offset = 0;
    int offset;
    if (!GetOffset (name, out offset))
        return false;
    var keys = GetArray (++dict_offset);
    if (0 == keys.Count)
        return false;

    int upper_bound = keys.Count;
    int lower_bound = 0;
    int key_index = 0;
    while (lower_bound < upper_bound)
    {
        key_index = (upper_bound + lower_bound) >> 1;
        int key = GetArrayElem (keys, key_index);
        if (key == offset)
            break;
        if (key >= offset)
            upper_bound = (upper_bound + lower_bound) >> 1;
        else
            lower_bound = key_index + 1;
    }
    if (lower_bound >= upper_bound)
        return false;

    var values = GetArray (dict_offset + keys.ArraySize);
    int data_offset = GetArrayElem (values, key_index);
    value_offset = dict_offset + keys.ArraySize + values.ArraySize + data_offset;
    return true;
}
```

#### GetOffset

```csharp
bool GetOffset (string name, out int offset) {

    var nm1 = GetArray (m_names);
    var nm2 = GetArray (m_names + nm1.ArraySize);
    int i = 0;
    for (int name_idx = 0; ; ++name_idx)
    {
        char symbol = name_idx < name.Length ? name[name_idx] : '\0';
        int prev_i = i;
        i = symbol + GetArrayElem (nm1, i);
        if (i >= nm1.Count || GetArrayElem (nm2, i) != prev_i)
            break;

        if (name_idx >= name.Length)
        {
            offset = GetArrayElem (nm1, i);
            return true;
        }
    }
    offset = 0;
    return false;
}
```

#### ReadNames

```csharp
Dictionary<int, string> ReadNames () {

    var lookup = new Dictionary<int, byte[]>();
    var next_lookup = new Dictionary<int, byte[]>();
    var dict = new Dictionary<int, string>();
    var nm1 = GetArray (m_names);
    var nm2 = GetArray (m_names + nm1.ArraySize);
    lookup[0] = new byte[0];
    while (lookup.Count > 0)
    {
        foreach (var item in lookup)
        {
            int first = GetArrayElem (nm1, item.Key);
            for (int i = 0; i < 256 && i + first < nm2.Count; ++i)
            {
                if (GetArrayElem (nm2, i + first) == item.Key)
                {
                    if (0 == i)
                        dict[GetArrayElem (nm1, i + first)] = Encoding.UTF8.GetString (item.Value);
                    else
                        next_lookup[i+first] = ArrayAppend (item.Value, (byte)i);
                }
            }
        }
        var tmp = lookup;
        lookup = next_lookup;
        next_lookup = tmp;
        next_lookup.Clear();
    }
    return dict;
}
```

#### ArrayAppend

```csharp
static byte[] ArrayAppend (byte[] array, byte n) {
    var new_array = new byte[array.Length+1];
    Buffer.BlockCopy (array, 0, new_array, 0, array.Length);
    new_array[array.Length] = n;
    return new_array;
}
```

#### GetArray

```csharp
EmArray GetArray (int offset) {
    int data_offset = m_data[offset] - 10;
    var array = new EmArray {
        Count = GetInteger (offset, 0xC),
        ElemSize = m_data[offset + data_offset - 1] - 12,
        DataOffset = offset + data_offset,
    };
    array.ArraySize = array.Count * array.ElemSize + data_offset;
    return array;
}
```

#### GetArrayElem

```csharp
int GetArrayElem (EmArray a1, int index) {
    int offset = index * a1.ElemSize;
    switch (a1.ElemSize)
    {
    case 1:
        return m_data[a1.DataOffset + offset];
    case 2:
        return LittleEndian.ToUInt16 (m_data, a1.DataOffset + offset);
    case 3:
        return LittleEndian.ToUInt16 (m_data, a1.DataOffset + offset) | m_data[a1.DataOffset + offset + 2] << 16;
    case 4:
        return LittleEndian.ToInt32 (m_data, a1.DataOffset + offset);
    default:
        throw new InvalidFormatException ("Invalid PSB array structure");
    }
}
```

#### GetObject

```csharp
object GetObject (int offset) {
    switch (m_data[offset])
    {
    case 1: return null;
    case 2: return true;
    case 3: return false;

    case 4:
    case 5:
    case 6:
    case 7:
    case 8: return GetInteger (offset, 4);

    case 9:
    case 0x0A:
    case 0x0B:
    case 0x0C: return GetLong (offset);

    case 0x15:
    case 0x16:
    case 0x17:
    case 0x18: return GetString (offset);

    case 0x19:
    case 0x1A:
    case 0x1B:
    case 0x1C: return GetChunk (offset);

    case 0x1D:
    case 0x1E: return GetFloat (offset);
    case 0x1F: return GetDouble (offset);
    case 0x20: return GetList (offset);
    case 0x21: return GetDict (offset);

    case 0x22:
    case 0x23:
    case 0x24:
    case 0x25: return GetExtraChunk (offset);
    default:
        throw new InvalidFormatException (string.Format ("Unknown serialized object type 0x{0:X2}", m_data[offset]));
    }
}
```

#### GetInteger

```csharp
int GetInteger (int offset, int base_type) {
    switch (m_data[offset] - base_type)
    {
    case 1: return m_data[offset+1];
    case 2: return LittleEndian.ToUInt16 (m_data, offset+1);
    case 3: return LittleEndian.ToUInt16 (m_data, offset+1) | m_data[offset+3] << 16;
    case 4: return LittleEndian.ToInt32 (m_data, offset+1);
    default: return 0;
    }
}
```

#### GetFloat

```csharp
float GetFloat (int offset) {
    if (0x1E == m_data[offset])
        return BitConverter.ToSingle (m_data, offset+1);
    else
        return 0.0f;
}
```

#### GetDouble

```csharp
double GetDouble (int offset) {
    if (0x1F == m_data[offset])
        return BitConverter.ToDouble (m_data, offset+1);
    else
        return 0.0;
}
```

#### GetLong

```csharp
long GetLong (int offset) {
    switch (m_data[offset])
    {
    case 0x09:  return LittleEndian.ToUInt32 (m_data, offset+1) | (long)(sbyte)m_data[offset+5] << 32;
    case 0x0A:  return LittleEndian.ToUInt32 (m_data, offset+1)
                       | (long)LittleEndian.ToInt16 (m_data, offset+5) << 32;
    case 0x0B:  return LittleEndian.ToUInt32 (m_data, offset+1)
                       | (long)LittleEndian.ToUInt16 (m_data, offset+5) << 32
                       | (long)(sbyte)m_data[offset+6] << 48;
    case 0x0C:  return LittleEndian.ToInt64 (m_data, offset+1);
    default:    return 0L;
    }
}
```

#### GetString

```csharp
string GetString (int obj_offset) {
    int index = GetInteger (obj_offset, 0x14);
    var array = GetArray (m_strings);
    int data_offset = m_strings_data + GetArrayElem (array, index);
    return Binary.GetCString (m_data, data_offset, m_data.Length-data_offset, Encoding.UTF8);
}
```

#### GetList

```csharp
IList GetList (int offset) {
    var array = GetArray (++offset);
    var list = new ArrayList (array.Count);
    for (int i = 0; i < array.Count; ++i)
    {
        int item_offset = offset + array.ArraySize + GetArrayElem (array, i);
        var item = GetObject (item_offset);
        list.Add (item);
    }
    return list;
}
```

#### GetDict

```csharp
IDictionary GetDict (int offset) {
    var keys = GetArray (++offset);
    if (0 == keys.Count)
        return new Dictionary<string, object>();
    var values = GetArray (offset + keys.ArraySize);
    var dict = new Dictionary<string, object> (keys.Count);
    for (int i = 0; i < keys.Count; ++i)
    {
        int key = GetArrayElem (keys, i);
        var value_offset = GetArrayElem (values, i);
        string key_name = m_name_map[key];
        dict[key_name] = GetObject (offset + value_offset + keys.ArraySize + values.ArraySize);
    }
    return dict;
}
```

#### GetChunk

```csharp
EmChunk GetChunk (int offset) {
    var chunk_index = GetInteger (offset, 0x18);
    var chunks = GetArray (m_chunk_offsets);
    if (chunk_index >= chunks.Count)
        throw new InvalidFormatException ("Invalid chunk index");
    var lengths = GetArray (m_chunk_lengths);
    return new EmChunk {
        Offset = GetArrayElem (chunks, chunk_index),
        Length = GetArrayElem (lengths, chunk_index),
    };
}
```

#### GetExtraChunk

```csharp
EmChunk GetExtraChunk (int offset) {
    var chunk_index = GetInteger (offset, 0x21);
    var chunks = GetArray (m_extra_offsets);
    if (chunk_index >= chunks.Count)
        throw new InvalidFormatException ("Invalid chunk index");
    var lengths = GetArray (m_extra_lengths);
    return new EmChunk {
        Offset = GetArrayElem (chunks, chunk_index),
        Length = GetArrayElem (lengths, chunk_index),
    };
}
```

#### Decrypt

```csharp
void Decrypt (byte[] data, int offset, int length) {
    for (int i = 0; i < length; ++i)
    {
        if (0 == m_key[4])
        {
            var v5 = m_key[3];
            var v6 = m_key[0] ^ (m_key[0] << 11);
            m_key[0] = m_key[1];
            m_key[1] = m_key[2];
            var eax = v6 ^ v5 ^ ((v6 ^ (v5 >> 11)) >> 8);
            m_key[2] = v5;
            m_key[3] = eax;
            m_key[4] = eax;
        }
        data[offset+i] ^= (byte)m_key[4];
        m_key[4] >>= 8;
    }
}
```

### GameRes.Formats.Emote.PsbReader.EmArray

#### 状态与常量

```csharp
public int  ArraySize ;

public int  Count ;

public int  ElemSize ;

public int  DataOffset ;
```

### GameRes.Formats.Emote.PsbReader.EmChunk

#### 状态与常量

```csharp
public int  Offset ;

public int  Length ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Emote/ArcPSB.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
