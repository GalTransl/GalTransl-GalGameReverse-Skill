# Pandora / ArcPBX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PBX` / `GameRes.Formats.Terios.PbxOpener` | `pbx` | `50616e64` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PbxOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "ora.box\0"))` |
| `PbxOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (0xC);` |
| `PbxOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0xC);` |
| `PbxOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_offset+0xC);` |
| `PbxOpener.OpenEntry` | `if (entry.Size <= 0x10 \|\| 0x6344764D != arc.File.View.ReadUInt32 (entry.Offset))` |
| `PbxOpener.OpenEntry` | `int unpacked_size = arc.File.View.ReadInt32 (entry.Offset+8);` |
| `PandoraCompression.Unpack` | `m_output[dst++] = m_input.ReadUInt8();` |
| `PandoraCompression.Unpack` | `int ctl = m_input.ReadUInt8();` |
| `PandoraCompression.Unpack` | `int offset = m_input.ReadUInt8();` |
| `PandoraCompression.Unpack` | `count = Binary.BigEndian (m_input.ReadUInt16());` |
| `PandoraCompression.Unpack` | `count = m_input.ReadByte() + ((ctl & 7) << 8) + 19;` |
| `PandoraCompression.Unpack` | `offset = Binary.BigEndian (m_input.ReadUInt16()) + 0x101;` |
| `PandoraCompression.Unpack` | `offset = m_input.ReadUInt8() + 1;` |
| `PandoraCompression.Unpack` | `count = m_input.ReadUInt8() + ((ctl & 0x1F) << 8) + 0x41;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Terios.PbxOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "ora.box\0"))
        return null;
    uint next_offset = file.View.ReadUInt32 (0xC);
    if (next_offset > file.View.Reserve (0, next_offset))
        return null;
    uint index_offset = 0x10;
    int count = (int)(next_offset-0x10) / 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0xC);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = next_offset;
        next_offset = file.View.ReadUInt32 (index_offset+0xC);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x10;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size <= 0x10 || 0x6344764D != arc.File.View.ReadUInt32 (entry.Offset))
        return base.OpenEntry (arc, entry);
    try
    {
        int unpacked_size = arc.File.View.ReadInt32 (entry.Offset+8);
        using (var input = arc.File.CreateStream (entry.Offset+0x10, entry.Size-0x10))
        using (var reader = new PandoraCompression (input, unpacked_size))
        {
            var data = reader.Unpack();
            return new BinMemoryStream (data, entry.Name);
        }
    }
    catch
    {

        return base.OpenEntry (arc, entry);
    }
}
```

### GameRes.Formats.Terios.PandoraCompression

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

byte[]          m_output ;

public byte[] Data { get { return m_output; } }
```

#### PandoraCompression

```csharp
public PandoraCompression (IBinaryStream input, int unpacked_size) {
    m_input = input;
    m_output = new byte[unpacked_size];
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    int dst = 0;
    m_output[dst++] = m_input.ReadUInt8();
    while (dst < m_output.Length)
    {
        int ctl = m_input.ReadUInt8();
        int count;
        if (ctl >= 0x80)
        {
            if (ctl >= 0xC0)
            {
                int offset = m_input.ReadUInt8();
                offset += 0x101 + ((ctl & 0x3F) << 8);
                offset = dst - offset;
                if (offset < 0)
                    throw new InvalidFormatException();
                m_output[dst++] = m_output[offset++];
                m_output[dst++] = m_output[offset++];
                m_output[dst++] = m_output[offset++];
            }
            else
            {
                if (ctl >= 0xB0)
                {
                    count = Binary.BigEndian (m_input.ReadUInt16());
                    count += 0x813 + ((ctl & 7) << 16);
                    ctl &= 8;
                }
                else if (ctl >= 0xA0)
                {
                    count = m_input.ReadByte() + ((ctl & 7) << 8) + 19;
                    ctl &= 8;
                }
                else
                {
                    count = (ctl & 0xF) + 3;
                    ctl &= 0x10;
                }
                int offset;
                if (ctl != 0)
                {
                    offset = Binary.BigEndian (m_input.ReadUInt16()) + 0x101;
                }
                else
                {
                    offset = m_input.ReadUInt8() + 1;
                }
                Binary.CopyOverlapped (m_output, dst - offset, dst, count);
                dst += count;
            }
        }
        else
        {
            if (ctl >= 0x60)
            {
                count = Binary.BigEndian (m_input.ReadUInt16());
                count += 0x2041 + ((ctl & 0x1F) << 16);
            }
            if (ctl >= 0x40)
            {
                count = m_input.ReadUInt8() + ((ctl & 0x1F) << 8) + 0x41;
            }
            else
            {
                count = ctl + 1;
            }
            count = m_input.Read (m_output, dst, count);
            dst += count;
        }
    }
    return m_output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Pandora/ArcPBX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
