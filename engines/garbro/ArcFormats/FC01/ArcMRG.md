# FC01 / ArcMRG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MRG/2` / `GameRes.Formats.FC01.Mrg2Opener` | `mrg` | `4d524700` | `False` |
| `MRG` / `GameRes.Formats.FC01.MrgOpener` | `mrg` | `4d524700` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MrgOpener.TryOpen` | `int count = file.View.ReadInt32 (12);` |
| `MrgOpener.TryOpen` | `int key1index = file.View.ReadUInt16 (4);` |
| `MrgOpener.TryOpen` | `int key2index = file.View.ReadUInt16 (6);` |
| `MrgOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (8) - 0x10;` |
| `MrgOpener.TryOpen` | `var index = file.View.ReadBytes (0x10, index_size);` |
| `MrgOpener.TryOpen` | `uint next_offset = LittleEndian.ToUInt32 (index, current_offset+0x1C);` |
| `MrgOpener.TryOpen` | `next_offset = LittleEndian.ToUInt32 (index, current_offset+0x3C);` |
| `MrgOpener.TryOpen` | `entry.UnpackedSize = LittleEndian.ToUInt32 (index, current_offset+0x0E);` |
| `MrgOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Mrg2Opener.TryOpen` | `int count = file.View.ReadInt32 (12);` |
| `Mrg2Opener.TryOpen` | `int version = file.View.ReadUInt16 (6);` |
| `Mrg2Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (8) - 0x10;` |
| `Mrg2Opener.TryOpen` | `var index = file.View.ReadBytes (0x10, index_size);` |
| `Mrg2Opener.TryOpen` | `uint next_offset = LittleEndian.ToUInt32 (index, current_offset+0x4F);` |
| `Mrg2Opener.TryOpen` | `next_offset = LittleEndian.ToUInt32 (index, current_offset+0xA6);` |
| `Mrg2Opener.TryOpen` | `entry.Method = LittleEndian.ToUInt16 (index, current_offset+0x45);` |
| `Mrg2Opener.TryOpen` | `entry.UnpackedSize = LittleEndian.ToUInt32 (index, current_offset+0x41);` |
| `Mrg2Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `MrgLzssReader.Unpack` | `int ctl = m_input.ReadUInt8();` |
| `MrgLzssReader.Unpack` | `byte b = m_input.ReadUInt8();` |
| `MrgLzssReader.Unpack` | `int offset = m_input.ReadUInt16();` |
| `MrgDecoder.MrgDecoder` | `uint unpacked_size = LittleEndian.ToUInt32 (data, m_src);` |
| `MrgDecoder.MrgDecoder` | `unpacked_size ^= LittleEndian.ToUInt32 (data, m_src+0x104);` |
| `MrgDecoder.Unpack` | `uint a = BigEndian.ToUInt32 (m_input, m_src);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FC01.MrgEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int  Method ;
```

### GameRes.Formats.FC01.MrgOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;
    int key1index = file.View.ReadUInt16 (4);
    int key2index = file.View.ReadUInt16 (6);
    if (key2index != 0 && key1index == 0)
        return null;
    uint index_size = file.View.ReadUInt32 (8) - 0x10;
    if (index_size < 0x40 || index_size >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0x10, index_size);
    if (index.Length != index_size)
        return null;

    if (key2index >= 2)
        return null;
    var key = GuessKey (file, index);
    if (null == key)
        throw new UnknownEncryptionScheme();
    Decrypt (index, 0, index.Length, key.Value);

    int current_offset = 0;
    uint next_offset = LittleEndian.ToUInt32 (index, current_offset+0x1C);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = Binary.GetCString (index, current_offset, 0x0E);
        var entry = FormatCatalog.Instance.Create<MrgEntry> (name);
        entry.Offset = next_offset;
        entry.Method = index[current_offset+0x12];

        next_offset = LittleEndian.ToUInt32 (index, current_offset+0x3C);
        entry.Size = next_offset - (uint)entry.Offset;
        if (entry.Offset < index_size || !entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.Method != 0;
        entry.UnpackedSize = LittleEndian.ToUInt32 (index, current_offset+0x0E);
        dir.Add (entry);
        current_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var packed_entry = entry as MrgEntry;
    if (null == packed_entry || !packed_entry.IsPacked || packed_entry.Method > 3)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    IBinaryStream input;
    if (packed_entry.Method >= 2)
    {
        if (entry.Size < 0x108)
            return arc.File.CreateStream (entry.Offset, entry.Size);
        var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
        var reader = new MrgDecoder (data);
        reader.Unpack();
        input = new BinMemoryStream (reader.Data, entry.Name);
    }
    else
        input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (packed_entry.Method < 3)
    {
        using (input)
        using (var reader = new MrgLzssReader (input, (int)input.Length, (int)packed_entry.UnpackedSize))
        {
            reader.Unpack();
            return new BinMemoryStream (reader.Data, entry.Name);
        }
    }
    return input.AsStream;
}
```

#### Decrypt

```csharp
static public void Decrypt (byte[] data, int index, int length, int key) {
    while (length > 0)
    {
        var v = data[index];
        data[index++] = (byte)(Binary.RotByteL (v, 1) ^ key);
        key += length--;
    }
}
```

#### GuessKey

```csharp
private byte? GuessKey (ArcView file, byte[] index) {
    uint actual_offset = (uint)file.MaxOffset;

    byte v = index[index.Length-1];
    v = (byte)(v << 1 | v >> 7);
    byte key = (byte)(v ^ (actual_offset >> 24));

    int remaining = 1;
    uint last_offset = (byte)(v ^ key);
    for (int i = index.Length-2; i >= index.Length-4; --i)
    {
        key -= (byte)++remaining;
        v = index[i];
        v = (byte)(v << 1 | v >> 7);
        last_offset = (last_offset << 8) | (uint)(v ^ key);
    }
    if (last_offset != actual_offset)
        return null;

    while (remaining++ < index.Length)
        key -= (byte)remaining;

    return key;
}
```

### GameRes.Formats.FC01.Mrg2Entry

继承/接口：`MrgEntry`。

#### 状态与常量

```csharp
public uint ArcKey ;

public uint Key ;
```

### GameRes.Formats.FC01.Mrg2Opener

继承/接口：`ArchiveFormat`。

#### Mrg2Opener

```csharp
public Mrg2Opener () {
    Extensions = new string[] { "mrg" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;
    int version = file.View.ReadUInt16 (6);
    if (version < 2)
        return null;
    uint index_size = file.View.ReadUInt32 (8) - 0x10;
    if (index_size < 0x40 || index_size >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0x10, index_size);
    if (index.Length != index_size)
        return null;

    uint arc_checksum = GetNameChecksum (Path.GetFileName (file.Name));
    Decrypt (index, 0, index.Length, arc_checksum, 0x285EE76F);
    int current_offset = 0;
    uint next_offset = LittleEndian.ToUInt32 (index, current_offset+0x4F);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = Binary.GetCString (index, current_offset, 0x40);
        var entry = FormatCatalog.Instance.Create<Mrg2Entry> (name);
        entry.Offset = next_offset;
        next_offset = LittleEndian.ToUInt32 (index, current_offset+0xA6);
        entry.Size = next_offset - (uint)entry.Offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Method = LittleEndian.ToUInt16 (index, current_offset+0x45);
        if (0 == entry.Method)
        {
            entry.ArcKey = arc_checksum;
            entry.Key = GetNameChecksum (entry.Name);
        }
        entry.IsPacked = entry.Method != 0;
        entry.UnpackedSize = LittleEndian.ToUInt32 (index, current_offset+0x41);
        dir.Add (entry);
        current_offset += 0x57;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var mrg_entry = entry as Mrg2Entry;
    if (null == mrg_entry || mrg_entry.Method > 3)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    IBinaryStream input;
    if (0 == mrg_entry.Method)
    {
        var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
        Decrypt (data, 0, data.Length, mrg_entry.Key, mrg_entry.ArcKey);
        input = new BinMemoryStream (data, entry.Name);
    }
    else if (mrg_entry.Method >= 2)
    {
        var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
        var reader = new MrgDecoder (data);
        reader.Unpack();
        input = new BinMemoryStream (reader.Data, entry.Name);
    }
    else
        input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (1 == mrg_entry.Method || 3 == mrg_entry.Method)
    {
        using (input)
        using (var reader = new MrgLzssReader (input, (int)input.Length, (int)mrg_entry.UnpackedSize))
        {
            reader.Unpack();
            return new BinMemoryStream (reader.Data, entry.Name);
        }
    }
    return input.AsStream;
}
```

#### Decrypt

```csharp
void Decrypt (byte[] data, int index, int length, uint checksum, uint key) {
    var table = new byte[0x100];
    for (int i = 0; i < 0x100; ++i)
    {
        uint n = key + Binary.RotL (checksum, 16);
        key = checksum;
        checksum += n;
        table[i] = (byte)checksum;
    }
    for (int i = 0; i < length; ++i)
    {
        data[index+i] ^= table[i & 0xFF];
    }
}
```

#### GetNameChecksum

```csharp
uint GetNameChecksum (string name) {
    if (string.IsNullOrEmpty (name))
        return 0;
    uint checksum = char.ToUpper (name[0]);
    for (int i = 0; i < name.Length; ++i)
    {
        if (name[i] != '.')
            checksum += char.ToUpper (name[i]) + (checksum << 6);
    }
    return checksum;
}
```

### GameRes.Formats.FC01.MrgLzssReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

byte[]          m_output ;

int             m_size ;

public byte[]        Data { get { return m_output; } }
```

#### MrgLzssReader

```csharp
public MrgLzssReader (IBinaryStream input, int input_length, int output_length) {
    m_input = input;
    m_output = new byte[output_length];
    m_size = input_length;
}
```

#### Unpack

```csharp
public void Unpack () {
    int dst = 0;
    var frame = new byte[0x1000];
    int frame_pos = 0xfee;
    int frame_mask = 0xfff;
    int remaining = m_size;
    while (remaining > 0)
    {
        int ctl = m_input.ReadUInt8();
        --remaining;
        for (int bit = 1; remaining > 0 && bit != 0x100; bit <<= 1)
        {
            if (dst >= m_output.Length)
                return;
            if (0 != (ctl & bit))
            {
                byte b = m_input.ReadUInt8();
                --remaining;
                frame[frame_pos++] = b;
                frame_pos &= frame_mask;
                m_output[dst++] = b;
            }
            else
            {
                if (remaining < 2)
                    return;
                int offset = m_input.ReadUInt16();
                remaining -= 2;
                int count = (offset >> 12) + 3;
                for ( ; count != 0; --count)
                {
                    if (dst >= m_output.Length)
                        break;
                    offset &= frame_mask;
                    byte v = frame[offset++];
                    frame[frame_pos++] = v;
                    frame_pos &= frame_mask;
                    m_output[dst++] = v;
                }
            }
        }
    }
}
```

### GameRes.Formats.FC01.MrgDecoder

#### 状态与常量

```csharp
byte[]      m_input ;

byte[]      m_output ;

int         m_start_index ;

int         m_src ;

public byte[] Data { get { return m_output; } }

public byte    Key { get; set; }

ushort[] word_10036650 = new ushort[0x200] ;

byte[] byte_table = new byte[0xff00] ;
```

#### MrgDecoder

```csharp
public MrgDecoder (byte[] data, int index = 0) {
    m_input = data;
    m_src = index;
    uint unpacked_size = LittleEndian.ToUInt32 (data, m_src);
    unpacked_size ^= LittleEndian.ToUInt32 (data, m_src+0x104);
    m_src += 4;
    m_start_index = m_src;
    m_output = new byte[unpacked_size];
}
```

#### MrgDecoder

```csharp
public MrgDecoder (byte[] data, int index, uint unpacked_size) {
    m_input = data;
    m_start_index = index;
    m_src = index;
    m_output = new byte[unpacked_size];
}
```

#### ResetKey

```csharp
public void ResetKey (byte key) {
    m_src = m_start_index;
    Key = key;
}
```

#### Unpack

```csharp
public int Unpack ()
    uint quant = InitTable();
    if (0 == quant || quant > 0x10000)
        throw new InvalidFormatException();
    uint mask = GetMask (quant);
    uint scale = 0x10000 / quant;
    uint b = 0;
    uint c = 0xffffffff;
    int dst = 0;
    uint a = BigEndian.ToUInt32 (m_input, m_src);
    m_src += 4;
    while (dst < m_output.Length)
    {
        c = ((c >> 8) * scale) >> 8;
        uint v = (a - b) / c;
        if (v > quant)
            throw new InvalidFormatException();
        v = byte_table[v];
        m_output[dst++] = (byte)v;
        b += word_10036650[v*2] * c;
        c *= word_10036650[v*2+1];
        while (0 == (((c + b) ^ b) & 0xFF000000))
        {
            if (m_src >= m_input.Length)
                return dst;
            a <<= 8;
            b <<= 8;
            c <<= 8;
            a |= m_input[m_src++];
        }
        while (c <= mask)
        {
            if (m_src >= m_input.Length)
                return dst;
            c = (~b & mask) << 8;
            a <<= 8;
            b <<= 8;
            a |= m_input[m_src++];
        }
    }
    return dst;
}
```

#### InitTable

```csharp
ushort InitTable ()
    ushort d = 0;
    int t = 0;
    byte key = Key;
    for (int i = 0; i < 0x100; i++)
    {
        byte c = m_input[m_src++];
        if (0 != Key)
        {
            c = (byte)(Binary.RotByteL (c, 1) ^ key);
            key -= (byte)i;
        }
        word_10036650[i*2] = d;
        word_10036650[i*2+1] = c;
        d += c;
        for (int j = 0; j < c; ++j)
            byte_table[t++] = (byte)i;
    }
    return d;
}
```

#### GetMask

```csharp
uint GetMask (uint d)
    d--;
    d >>= 8;
    uint result = 0xff;
    while (d > 0)
    {
        d >>= 1;
        result = (result << 1) | 1;
    }
    return result;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/FC01/ArcMRG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
