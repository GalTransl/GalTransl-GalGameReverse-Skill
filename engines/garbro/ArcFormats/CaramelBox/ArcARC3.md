# CaramelBox / ArcARC3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC3` / `GameRes.Formats.CaramelBox.Arc3Opener` | `bin`, `ar3`, `ac3` | `61726333` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Arc3Opener.TryOpen` | `int  version      = Binary.BigEndian (file.View.ReadInt32 (4));` |
| `Arc3Opener.TryOpen` | `uint cluster_size = Binary.BigEndian (file.View.ReadUInt32 (0x08));` |
| `Arc3Opener.TryOpen` | `uint base_offset  = Binary.BigEndian (file.View.ReadUInt32 (0x0C));` |
| `Arc3Opener.TryOpen` | `uint index_offset = Binary.BigEndian (file.View.ReadUInt32 (0x18));` |
| `Arc3Opener.TryOpen` | `uint index_size   = Binary.BigEndian (file.View.ReadUInt32 (0x1C));` |
| `Arc3Opener.TryOpen` | `byte name_length = file.View.ReadByte (current_offset++);` |
| `Arc3Opener.TryOpen` | `uint offset = BigEndian24 (file.View.ReadUInt32 (current_offset));` |
| `Arc3Opener.TryOpen` | `last_entry_offset = BigEndian24 (file.View.ReadUInt32 (current_offset));` |
| `Arc3Opener.TryOpen` | `entry.Size  = Binary.BigEndian (file.View.ReadUInt32 (entry.Offset+8));` |
| `Arc3Opener.TryOpen` | `entry.Flags = Binary.BigEndian (file.View.ReadUInt32 (entry.Offset+0x14));` |
| `Arc3Opener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `Arc3Opener.TryOpen` | `entry.UnpackedSize = Binary.BigEndian (file.View.ReadUInt32 (entry.Offset+2));` |
| `Arc3Opener.UnpackLze` | `if (!Binary.AsciiEqual (header, "ze"))` |
| `Arc3Opener.UnpackLze` | `int chunk_length = BigEndian.ToUInt16 (header, 2);` |
| `Arc3Opener.ReadNameMap` | `int count = LittleEndian.ToInt32 (table, 0);` |
| `Arc3Opener.ReadNameMap` | `int key_pos   = names_pos + LittleEndian.ToInt32 (table, index_pos);` |
| `Arc3Opener.ReadNameMap` | `int value_pos = names_pos + LittleEndian.ToInt32 (table, index_pos+4);` |
| `LzBitStream.GetBits` | `int b = m_input.ReadByte();` |
| `LzBitStream.GetBits` | `b = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CaramelBox.Arc3Entry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint Flags ;

public bool IsEncrypted ;
```

### GameRes.Formats.CaramelBox.Arc3Opener

继承/接口：`ArchiveFormat`。

#### Arc3Opener

```csharp
public Arc3Opener () {
    Extensions = new string[] { "bin", "ar3", "ac3" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int  version      = Binary.BigEndian (file.View.ReadInt32 (4));
    uint cluster_size = Binary.BigEndian (file.View.ReadUInt32 (0x08));
    uint base_offset  = Binary.BigEndian (file.View.ReadUInt32 (0x0C));
    uint index_offset = Binary.BigEndian (file.View.ReadUInt32 (0x18));
    uint index_size   = Binary.BigEndian (file.View.ReadUInt32 (0x1C));
    if (0 == index_size)
        return null;

    bool new_name = false;
    var dir = new List<Entry>();
    var name_buffer = new byte[0x10];
    long current_offset = (long)index_offset * cluster_size;
    long index_end = current_offset + index_size;
    if (index_end > file.MaxOffset)
        return null;

    uint last_entry_offset = 0x7FFFFFFF;
    int current_name_length = 0;
    Arc3Entry prev_entry = null;
    Arc3Entry long_info = null;
    while (current_offset < index_end)
    {
        byte name_length = file.View.ReadByte (current_offset++);
        int name_offset = name_length >> 4;
        name_length &= 0xF;
        if (name_offset != 0xF)
        {
            file.View.Read (current_offset, name_buffer, name_offset, name_length);
            current_offset += name_length;
            current_name_length = name_offset+name_length;
        }
        else if (0xF == name_length)
        {
            name_buffer[current_name_length-1]++;
        }
        else if (name_length != 0)
        {
            file.View.Read (current_offset, name_buffer, 0, name_length);
            current_offset += name_length;
            current_name_length = name_length;
            new_name = true;
        }
        else
        {
            uint offset = BigEndian24 (file.View.ReadUInt32 (current_offset));
            offset = (uint)Math.Abs ((int)(offset - index_offset));
            if (offset < last_entry_offset)
                last_entry_offset = offset;

            if (prev_entry != null)
                prev_entry.Offset = (long)(last_entry_offset + base_offset) * cluster_size;
        }
        last_entry_offset = BigEndian24 (file.View.ReadUInt32 (current_offset));
        current_offset += 3;
        if (new_name)
        {
            current_offset += 3;
            new_name = false;
        }
        string name;
        if (current_name_length > 3)
        {
            name = Encodings.cp932.GetString (name_buffer, 3, current_name_length-3);
            string ext = Encodings.cp932.GetString (name_buffer, 0, 3);
            name = name + '.' + ext;
        }
        else
            name = Encodings.cp932.GetString (name_buffer, 0, current_name_length);

        var entry = new Arc3Entry { Name = name };
        entry.Offset = (long)(last_entry_offset + base_offset) * cluster_size;
        if (entry.Offset >= file.MaxOffset)
            return null;
        dir.Add (entry);
        prev_entry = entry;
        if (null == long_info && "longinfo.$$$" == name)
            long_info = entry;
        if (name.HasExtension ("lze"))
            entry.Type = "image";
    }

    foreach (Arc3Entry entry in dir)
    {
        entry.Size  = Binary.BigEndian (file.View.ReadUInt32 (entry.Offset+8));
        entry.Flags = Binary.BigEndian (file.View.ReadUInt32 (entry.Offset+0x14));
        entry.UnpackedSize = entry.Size;
        entry.IsEncrypted = 2 == entry.Flags;
        entry.Offset += 0x20;
        uint signature = file.View.ReadUInt32 (entry.Offset);
        if (entry.IsEncrypted)
            signature = ~signature;
        entry.IsPacked = (signature & 0xFFFF) == 0x7A6C;
        if (entry.IsPacked)
        {
            entry.UnpackedSize = Binary.BigEndian (file.View.ReadUInt32 (entry.Offset+2));
            if (entry.IsEncrypted)
                entry.UnpackedSize ^= 0xFFFFFFFF;
            entry.Offset += 6;
            entry.Size -= 6;
        }
        else
        {
            var res = AutoEntry.DetectFileType (signature);
            if (res != null)
                entry.Type = res.Type;
        }
    }
    var arc = new ArcFile (file, this, dir);
    try
    {
        if (version > 1 && long_info != null)
        {
            var name_map = ReadNameMap (arc, long_info);
            foreach (var entry in dir)
            {
                string orig_name;
                if (name_map.TryGetValue (entry.Name, out orig_name))
                    entry.Name = orig_name;
            }
        }
    }
    catch {  }

    foreach (var entry in dir.Where (e => e.Name.Contains ('*')))
        entry.Name = entry.Name.Replace ('*', '＊');
    return arc;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var a3ent = entry as Arc3Entry;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null == entry)
        return input;
    if (a3ent.IsEncrypted)
    {
        input = new InputCryptoStream (input, new NotTransform());
    }
    if (!a3ent.IsPacked)
        return input;
    using (input)
    {
        var data = UnpackLze (input, a3ent.UnpackedSize);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### BigEndian24

```csharp
static uint BigEndian24 (uint x) {
    return (x & 0xFFu) << 16 | x & 0xFF00u | (x >> 16) & 0xFFu;
}
```

#### UnpackLze

```csharp
byte[] UnpackLze (Stream input, uint unpacked_size) {
    var data = new byte[unpacked_size];
    var header = new byte[4];
    int dst = 0;
    using (var bits = new LzBitStream (input, true))
    {
        while (dst < data.Length)
        {
            if (4 != input.Read (header, 0, 4))
                break;
            if (!Binary.AsciiEqual (header, "ze"))
                throw new InvalidFormatException ("Malformed compressed stream");
            int chunk_length = BigEndian.ToUInt16 (header, 2);
            bits.Reset();
            UnpackZeChunk (bits, data, dst, chunk_length);
            dst += chunk_length;
        }
        return data;
    }
}
```

#### UnpackZeChunk

```csharp
void UnpackZeChunk (IBitStream bits, byte[] output, int dst, int unpacked_size) {
    int output_end = dst + unpacked_size;
    while (dst < output_end)
    {
        int count = LzeGetInteger (bits);
        if (-1 == count)
            break;

        while (--count > 0)
        {
            int data = bits.GetBits (8);
            if (-1 == data)
                break;

            if (dst < output_end)
                output[dst++] = (byte)data;
        }
        if (count > 0 || dst >= output_end)
            break;

        int offset = LzeGetInteger (bits);
        if (-1 == offset)
            break;
        count = LzeGetInteger (bits);
        if (-1 == count)
            break;

        Binary.CopyOverlapped (output, dst-offset, dst, count);
        dst += count;
    }
    if (dst < output_end)
        throw new EndOfStreamException ("Premature end of compressed stream");
}
```

#### LzeGetInteger

```csharp
int LzeGetInteger (IBitStream bits) {
    int length = 0;
    for (int i = 0; i < 16; ++i)
    {
        if (0 != bits.GetNextBit())
            break;
        ++length;
    }
    int v = 1 << length;
    if (length > 0)
        v |= bits.GetBits (length);
    return v;
}
```

#### ReadNameMap

```csharp
IDictionary<string, string> ReadNameMap (ArcFile file, Arc3Entry entry) {
    byte[] table = new byte[entry.UnpackedSize];
    using (var input = OpenEntry (file, entry))
    {
        input.Read (table, 0, table.Length);
    }
    int count = LittleEndian.ToInt32 (table, 0);
    if (!IsSaneCount (count))
        throw new InvalidFormatException ("Invalid longinfo map format");
    var map = new Dictionary<string, string> (count);
    int index_pos = 4;
    int names_pos = index_pos + count * 8;
    for (int i = 0; i < count; ++i)
    {
        int key_pos   = names_pos + LittleEndian.ToInt32 (table, index_pos);
        int value_pos = names_pos + LittleEndian.ToInt32 (table, index_pos+4);
        index_pos += 8;
        string key = Binary.GetCString (table, key_pos, table.Length - key_pos);
        map[key] = Binary.GetCString (table, value_pos, table.Length - value_pos);
    }
    return map;
}
```

### GameRes.Formats.CaramelBox.LzBitStream

继承/接口：`BitStream`, `IBitStream`。

#### GetBits

```csharp
public int GetBits (int count) {
    Debug.Assert (count <= 24, "LzBitStream does not support sequences longer than 24 bits");
    while (m_cached_bits < count)
    {
        int b = m_input.ReadByte();
        if (-1 == b)
            return -1;
        m_bits = (m_bits << 8) | b;
        m_cached_bits += 8;
        b = m_input.ReadByte();
        if (b != -1)
        {
            m_bits = (m_bits << 8) | b;
            m_cached_bits += 8;
        }
    }
    int mask = (1 << count) - 1;
    m_cached_bits -= count;
    return (m_bits >> m_cached_bits) & mask;
}
```

#### GetNextBit

```csharp
public int GetNextBit () {
    return GetBits (1);
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/CaramelBox/ArcARC3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
