# SHSystem / ArcHXP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `HIM4` / `GameRes.Formats.SHSystem.Him4Opener` | `hxp` | `48696d34`, `53485336` | `False` |
| `HIM5` / `GameRes.Formats.SHSystem.Him5Opener` | `hxp` | `48696d35`, `53485337` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Him4Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Him4Opener.TryOpen` | `long next_offset = file.View.ReadUInt32 (8);` |
| `Him4Opener.TryOpen` | `next_offset = i + 1 == count ? file.MaxOffset : file.View.ReadUInt32 (index_offset);` |
| `Him4Opener.DetectFileTypes` | `uint packed_size   = file.View.ReadUInt32 (entry.Offset);` |
| `Him4Opener.DetectFileTypes` | `uint unpacked_size = file.View.ReadUInt32 (entry.Offset+4);` |
| `Him4Opener.DetectFileTypes` | `signature = LittleEndian.ToUInt32 (signature_buffer, 0);` |
| `Him4Opener.DetectFileTypes` | `signature = file.View.ReadUInt32 (entry.Offset);` |
| `Him5Opener.TryOpen` | `int version = file.View.ReadByte (3) - '0';` |
| `Him5Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Him5Opener.TryOpen` | `int entry_size = file.View.ReadByte (index_offset);` |
| `Him5Opener.TryOpen` | `Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset+1)),` |
| `Him5Opener.TryOpen` | `Name = file.View.ReadString (index_offset+5, (uint)entry_size-5),` |
| `Him5Opener.ReadIndex` | `int size   = file.View.ReadInt32 (index_offset);` |
| `Him5Opener.ReadIndex` | `int offset = file.View.ReadInt32 (index_offset+4);` |
| `ShsCompression.Unpack` | `int ctl = m_input.ReadUInt8();` |
| `ShsCompression.Unpack` | `count = m_input.ReadUInt8() + 0x1E;` |
| `ShsCompression.Unpack` | `count = Binary.BigEndian (m_input.ReadUInt16()) + 0x11E;` |
| `ShsCompression.Unpack` | `count = Binary.BigEndian (m_input.ReadInt32());` |
| `ShsCompression.Unpack` | `offset = m_input.ReadUInt8();` |
| `ShsCompression.Unpack` | `ctl = m_input.ReadUInt8();` |
| `ShsCompression.Unpack` | `count = Binary.BigEndian (m_input.ReadUInt16()) + 0x102;` |
| `ShsCompression.Unpack` | `offset = ((ctl & 0x1F) << 8) \| m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SHSystem.Him4Opener

继承/接口：`ArchiveFormat`。

#### Him4Opener

```csharp
public Him4Opener () {
    Signatures = new uint[] { 0x346D6948, 0x36534853 };
    Extensions = new string[] { "hxp" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    long next_offset = file.View.ReadUInt32 (8);
    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (next_offset > file.MaxOffset)
            return null;
        var entry = new PackedEntry {
            Name = i.ToString ("D5"),
            Offset = next_offset,
        };
        next_offset = i + 1 == count ? file.MaxOffset : file.View.ReadUInt32 (index_offset);
        index_offset += 4;
        entry.Size = (uint)(next_offset - entry.Offset);
        dir.Add (entry);
    }
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### DetectFileTypes

```csharp
static protected void DetectFileTypes (ArcView file, List<Entry> dir) {
    byte[] signature_buffer = new byte[4];
    foreach (PackedEntry entry in dir)
    {
        uint packed_size   = file.View.ReadUInt32 (entry.Offset);
        uint unpacked_size = file.View.ReadUInt32 (entry.Offset+4);
        entry.IsPacked = 0 != packed_size;
        if (!entry.IsPacked)
            packed_size = unpacked_size;
        entry.Size = packed_size;
        entry.UnpackedSize = unpacked_size;
        entry.Offset += 8;
        uint signature;
        if (entry.IsPacked)
        {
            using (var input = file.CreateStream (entry.Offset, Math.Min (packed_size, 0x20u)))
            using (var reader = new ShsCompression (input))
            {
                reader.Unpack (signature_buffer);
                signature = LittleEndian.ToUInt32 (signature_buffer, 0);
            }
        }
        else
        {
            signature = file.View.ReadUInt32 (entry.Offset);
        }
        if (0 != signature)
        {
            IResource res;
            if (0x020000 == signature || 0x0A0000 == signature)
                res = ImageFormat.Tga;
            else
                res = AutoEntry.DetectFileType (signature);
            if (res != null)
                entry.ChangeType (res);
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size, entry.Name);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    var data = new byte[pent.UnpackedSize];
    using (var reader = new ShsCompression (input))
    {
        reader.Unpack (data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

### GameRes.Formats.SHSystem.Him5Opener

继承/接口：`Him4Opener`。

#### Him5Opener

```csharp
public Him5Opener () {
    Signatures = new uint[] { 0x356D6948, 0x37534853 };
    Extensions = new string[] { "hxp" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadByte (3) - '0';
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var index = ReadIndex (file, 8, count);
    var dir = new List<Entry>();
    foreach (var section in index)
    {
        int index_offset = section.Item1;
        for (int section_size = section.Item2; section_size > 0; )
        {
            int entry_size = file.View.ReadByte (index_offset);
            if (entry_size < 5)
                break;
            var entry = new PackedEntry {
                Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset+1)),
                Name = file.View.ReadString (index_offset+5, (uint)entry_size-5),
            };
            if (entry.Offset > file.MaxOffset)
                return null;
            index_offset += entry_size;
            section_size -= entry_size;
            dir.Add (entry);
        }
    }
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### ReadIndex

```csharp
internal static List<Tuple<int, int>> ReadIndex (ArcView file, uint index_offset, int count) {
    var index = new List<Tuple<int, int>> (count);
    for (int i = 0; i < count; ++i)
    {
        int size   = file.View.ReadInt32 (index_offset);
        int offset = file.View.ReadInt32 (index_offset+4);
        index_offset += 8;
        if (size != 0)
            index.Add (Tuple.Create (offset, size));
    }
    return index;
}
```

### GameRes.Formats.SHSystem.ShsCompression

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;
```

#### ShsCompression

```csharp
public ShsCompression (IBinaryStream input) {
    m_input = input;
}
```

#### Unpack

```csharp
public int Unpack (byte[] output) {
    int dst = 0;
    while (dst < output.Length)
    {
        int count;
        int ctl = m_input.ReadUInt8();
        if (ctl < 32)
        {
            switch (ctl)
            {
            case 0x1D:
                count = m_input.ReadUInt8() + 0x1E;
                break;
            case 0x1E:
                count = Binary.BigEndian (m_input.ReadUInt16()) + 0x11E;
                break;
            case 0x1F:
                count = Binary.BigEndian (m_input.ReadInt32());
                break;
            default:
                count = ctl + 1;
                break;
            }
            count = Math.Min (count, output.Length - dst);
            m_input.Read (output, dst, count);
        }
        else
        {
            int offset;
            if (0 == (ctl & 0x80))
            {
                if (0x20 == (ctl & 0x60))
                {
                    offset = (ctl >> 2) & 7;
                    count = ctl & 3;
                }
                else
                {
                    offset = m_input.ReadUInt8();
                    if (0x40 == (ctl & 0x60))
                        count = (ctl & 0x1F) + 4;
                    else
                    {
                        offset |= (ctl & 0x1F) << 8;
                        ctl = m_input.ReadUInt8();
                        if (0xFE == ctl)
                            count = Binary.BigEndian (m_input.ReadUInt16()) + 0x102;
                        else if (0xFF == ctl)
                            count = Binary.BigEndian (m_input.ReadInt32());
                        else
                            count = ctl + 4;
                    }
                }
            }
            else
            {
                count = (ctl >> 5) & 3;
                offset = ((ctl & 0x1F) << 8) | m_input.ReadUInt8();
            }
            count += 3;
            offset++;
            count = Math.Min (count, output.Length-dst);
            Binary.CopyOverlapped (output, dst-offset, dst, count);
        }
        dst += count;
    }
    return dst;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/SHSystem/ArcHXP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
