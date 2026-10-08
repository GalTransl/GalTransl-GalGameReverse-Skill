# UMeSoft / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/UME` / `GameRes.Formats.UMeSoft.BinOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `BinOpener.TryOpen` | `var name = file.View.ReadUInt32 (index_offset).ToString ("D5");` |
| `BinOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+4) << 11,` |
| `BinOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+8),` |
| `BinOpener.TryOpen` | `if (entry.Size > 13 && file.View.AsciiEqual (entry.Offset+2, "ike"))` |
| `BinOpener.TryOpen` | `int unpacked_size = IkeReader.DecodeSize (file.View.ReadByte (entry.Offset+10),` |
| `BinOpener.TryOpen` | `file.View.ReadByte (entry.Offset+11),` |
| `BinOpener.TryOpen` | `file.View.ReadByte (entry.Offset+12));` |
| `BinOpener.TryOpen` | `signature = file.View.ReadUInt32 (entry.Offset+0xF);` |
| `BinOpener.TryOpen` | `signature = file.View.ReadUInt32 (entry.Offset);` |
| `IkeReader.Unpack` | `m_output[dst++] = m_input.ReadUInt8();` |
| `IkeReader.Unpack` | `offset = m_input.ReadUInt8() \| -0x100;` |
| `IkeReader.Unpack` | `count = m_input.ReadUInt8() + 17;` |
| `IkeReader.GetBit` | `m_bits = m_input.ReadUInt16() \| 0x10000;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.UMeSoft.BinOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if ((count & 0xFFFF) != 0)
        return null;
    count = (count >> 16) - 1;
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadUInt32 (index_offset).ToString ("D5");
        var entry = new PackedEntry {
            Name   = name,
            Offset = file.View.ReadUInt32 (index_offset+4) << 11,
            Size   = file.View.ReadUInt32 (index_offset+8),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 12;
    }
    foreach (PackedEntry entry in dir)
    {
        uint signature;
        if (entry.Size > 13 && file.View.AsciiEqual (entry.Offset+2, "ike"))
        {
            int unpacked_size = IkeReader.DecodeSize (file.View.ReadByte (entry.Offset+10),
                                                      file.View.ReadByte (entry.Offset+11),
                                                      file.View.ReadByte (entry.Offset+12));
            entry.IsPacked = true;
            entry.UnpackedSize = (uint)unpacked_size;
            signature = file.View.ReadUInt32 (entry.Offset+0xF);
            entry.Offset += 13;
            entry.Size   -= 13;
        }
        else
            signature = file.View.ReadUInt32 (entry.Offset);
        entry.ChangeType (AutoEntry.DetectFileType (signature));
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var reader = new IkeReader (input, (int)pent.UnpackedSize);
        var data = reader.Unpack();
        return new BinMemoryStream (data, entry.Name);
    }
}
```

### GameRes.Formats.UMeSoft.IkeReader

#### 状态与常量

```csharp
IBinaryStream   m_input ;

byte[]          m_output ;

int m_bits ;
```

#### IkeReader

```csharp
public IkeReader (IBinaryStream input, int unpacked_size) {
    m_input = input;
    m_output = new byte[unpacked_size];
}
```

#### DecodeSize

```csharp
public static int DecodeSize (byte a, byte b, byte c) {
    return b + ((c + (a >> 2 << 8)) << 8);
}
```

#### CreateStream

```csharp
public static IBinaryStream CreateStream (IBinaryStream input, int unpacked_size) {
    input.Position = 0xD;
    var ike = new IkeReader (input, unpacked_size);
    var data = ike.Unpack();
    return new BinMemoryStream (data);
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    m_bits = 2;
    GetBit();
    int dst = 0;
    while (dst < m_output.Length)
    {
        int offset, shift, count;
        if (GetBit() != 0)
        {
            m_output[dst++] = m_input.ReadUInt8();
            continue;
        }
        if (GetBit() != 0)
        {
            offset = m_input.ReadUInt8() | -0x100;
            shift = 0;
            if (GetBit() == 0)
                shift += 0x100;
            if (GetBit() == 0)
            {
                offset -= 0x200;
                if (GetBit() == 0)
                {
                    shift <<= 1;
                    if (GetBit() == 0)
                        shift += 0x100;
                    offset -= 0x200;
                    if (GetBit() == 0)
                    {
                        shift <<= 1;
                        if (GetBit() == 0)
                            shift += 0x100;
                        offset -= 0x400;
                        if (GetBit() == 0)
                        {
                            offset -= 0x800;
                            shift <<= 1;
                            if (GetBit() == 0)
                                shift += 0x100;
                        }
                    }
                }
            }
            offset -= shift;
            if (GetBit() != 0)
            {
                count = 3;
            }
            else if (GetBit() != 0)
            {
                count = 4;
            }
            else if (GetBit() != 0)
            {
                count = 5;
            }
            else if (GetBit() != 0)
            {
                count = 6;
            }
            else if (GetBit() != 0)
            {
                if (GetBit() != 0)
                    count = 8;
                else
                    count = 7;
            }
            else if (GetBit() != 0)
            {
                count = m_input.ReadUInt8() + 17;
            }
            else
            {
                count = 9;
                if (GetBit() != 0)
                    count = 13;
                if (GetBit() != 0)
                    count += 2;
                if (GetBit() != 0)
                    count++;
            }
        }
        else
        {
            offset = m_input.ReadUInt8() | -0x100;
            if (GetBit() != 0)
            {
                offset -= 0x100;
                if (GetBit() == 0)
                    offset -= 0x400;
                if (GetBit() == 0)
                    offset -= 0x200;
                if (GetBit() == 0)
                    offset -= 0x100;
            }
            else if (offset == -1)
            {
                if (GetBit() == 0)
                    break;
                else
                    continue;
            }
            count = 2;
        }
        count = Math.Min (count, m_output.Length - dst);
        Binary.CopyOverlapped (m_output, dst+offset, dst, count);
        dst += count;
    }
    return m_output;
}
```

#### GetBit

```csharp
int GetBit () {
    int bit = m_bits & 1;
    m_bits >>= 1;
    if (1 == m_bits)
    {
        m_bits = m_input.ReadUInt16() | 0x10000;
    }
    return bit;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/UMeSoft/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
