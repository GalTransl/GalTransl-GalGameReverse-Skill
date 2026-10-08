# Foster / ArcFA2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FA2` / `GameRes.Formats.Foster.Fa2Opener` | `fa2` | `46413200` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Fa2Opener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `Fa2Opener.TryOpen` | `bool is_packed = (file.View.ReadByte (4) & 1) != 0;` |
| `Fa2Opener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `Fa2Opener.TryOpen` | `index = input.ReadBytes ((int)(file.MaxOffset - index_offset));` |
| `Fa2Opener.TryOpen` | `entry.UnpackedSize = index.ToUInt32 (index_pos);` |
| `Fa2Opener.TryOpen` | `entry.Size         = index.ToUInt32 (index_pos+4);` |
| `Fa2Compression.Unpack` | `m_output[dst++] = m_input.ReadUInt8();` |
| `Fa2Compression.Unpack` | `offset = m_input.ReadUInt8() << 3;` |
| `Fa2Compression.Unpack` | `offset = m_input.ReadUInt8();` |
| `Fa2Compression.Unpack` | `offset = m_input.ReadUInt8() << 1;` |
| `Fa2Compression.Unpack` | `offset \|= m_input.ReadUInt8();` |
| `Fa2Compression.Unpack` | `count = 27 + m_input.ReadUInt8();` |
| `Fa2Compression.FetchBits` | `m_bits = m_input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Foster.Fa2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    bool is_packed = (file.View.ReadByte (4) & 1) != 0;
    uint index_offset = file.View.ReadUInt32 (8);
    byte[] index;
    using (var input = file.CreateStream (index_offset))
    {
        if (is_packed)
            index = Decompress (input, (uint)count * 0x20);
        else
            index = input.ReadBytes ((int)(file.MaxOffset - index_offset));
    }

    uint data_offset = 0x10;
    int index_pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, index_pos, 0xF);
        index_pos += 0xF;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.IsPacked = (index[index_pos] & 2) != 0;
        entry.Offset = data_offset;
        index_pos += 9;
        entry.UnpackedSize = index.ToUInt32 (index_pos);
        entry.Size         = index.ToUInt32 (index_pos+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += 8;
        data_offset += (entry.Size + 0xFu) & ~0xFu;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    var data = Decompress (input, pent.UnpackedSize);
    return new BinMemoryStream (data, entry.Name);
}
```

#### Decompress

```csharp
byte[] Decompress (IBinaryStream input, uint unpacked_size) {
    var comp = new Fa2Compression (input, unpacked_size);
    return comp.Unpack();
}
```

### GameRes.Formats.Foster.Fa2Compression

#### 状态与常量

```csharp
IBinaryStream   m_input ;

byte[]          m_output ;

uint    m_bits ;

int     m_bit_count ;
```

#### Fa2Compression

```csharp
public Fa2Compression (IBinaryStream input, uint unpacked_size) {
    m_input = input;
    m_output = new byte[unpacked_size];
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    m_bit_count = 0;
    int dst = 0;
    while (dst < m_output.Length)
    {
        if (GetNextBit() != 0)
        {
            m_output[dst++] = m_input.ReadUInt8();
            continue;
        }
        int offset;
        if (GetNextBit() != 0)
        {
            if (GetNextBit() != 0)
            {
                offset = m_input.ReadUInt8() << 3;
                offset |= GetBits (3);
                offset += 0x100;
                if (offset >= 0x8FF)
                    break;
            }
            else
            {
                offset = m_input.ReadUInt8();
            }
            m_output[dst  ] = m_output[dst-offset-1];
            m_output[dst+1] = m_output[dst-offset  ];
            dst += 2;
        }
        else
        {
            if (GetNextBit() != 0)
            {
                offset = m_input.ReadUInt8() << 1;
                offset |= GetNextBit();
            }
            else
            {
                offset = 0x100;
                if (GetNextBit() != 0)
                {
                    offset |= m_input.ReadUInt8();
                    offset <<= 1;
                    offset |= GetNextBit();
                }
                else if (GetNextBit() != 0)
                {
                    offset |= m_input.ReadUInt8();
                    offset <<= 2;
                    offset |= GetBits (2);
                }
                else if (GetNextBit() != 0)
                {
                    offset |= m_input.ReadUInt8();
                    offset <<= 3;
                    offset |= GetBits (3);
                }
                else
                {
                    offset |= m_input.ReadUInt8();
                    offset <<= 4;
                    offset |= GetBits (4);
                }
            }
            int count = 0;
            if (GetNextBit() != 0)
            {
                count = 3;
            }
            else if (GetNextBit() != 0)
            {
                count = 4;
            }
            else if (GetNextBit() != 0)
            {
                count = 5 + GetNextBit();
            }
            else if (GetNextBit() != 0)
            {
                count = 7 + GetBits (2);
            }
            else if (GetNextBit() != 0)
            {
                count = 11 + GetBits (4);
            }
            else
            {
                count = 27 + m_input.ReadUInt8();
            }
            Binary.CopyOverlapped (m_output, dst - offset - 1, dst, count);
            dst += count;
        }
    }
    return m_output;
}
```

#### FetchBits

```csharp
void FetchBits () {
    m_bits = m_input.ReadUInt32();
    m_bit_count = 32;
}
```

#### GetNextBit

```csharp
int GetNextBit () {
    if (0 == m_bit_count)
        FetchBits();
    int bit = (int)((m_bits >> 31) & 1);
    m_bits <<= 1;
    --m_bit_count;
    return bit;
}
```

#### GetBits

```csharp
int GetBits (int count) {
    uint bits = 0;
    int avail_bits = Math.Min (count, m_bit_count);
    if (avail_bits > 0)
    {
        bits = m_bits >> (32 - avail_bits);
        m_bits <<= avail_bits;
        m_bit_count -= avail_bits;
        count -= avail_bits;
    }
    if (count > 0)
    {
        FetchBits();
        bits = bits << count | m_bits >> (32 - count);
        m_bits <<= count;
        m_bit_count -= count;
    }
    return (int)bits;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Foster/ArcFA2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
