# ArcFormats / ArcSPack：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SPACK` / `GameRes.Formats.SPack.DatOpener` | `dat` | `53506163` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `if ('k' != file.View.ReadInt16 (4))` |
| `DatOpener.TryOpen` | `int version = file.View.ReadInt16 (6);` |
| `DatOpener.TryOpen` | `uint data_size = file.View.ReadUInt32 (8);` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `DatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x20);` |
| `DatOpener.TryOpen` | `Offset = base_offset + file.View.ReadUInt32 (index_offset),` |
| `DatOpener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset+4),` |
| `DatOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+8),` |
| `DatOpener.TryOpen` | `Method = file.View.ReadByte (index_offset+12),` |
| `DatOpener.TryOpen` | `Crc    = file.View.ReadUInt16 (index_offset+14),` |
| `PackedReader.Unpack` | `ctl = m_input.ReadUInt32();` |
| `PackedReader.Unpack` | `offset = m_input.ReadUInt8();` |
| `PackedReader.Unpack` | `copy_count = m_input.ReadUInt16();` |
| `PackedReader.Unpack` | `copy_count = m_input.ReadUInt8();` |
| `PackedReader.Unpack` | `offset = ((offset - 10) << 8) \| m_input.ReadUInt8();` |
| `PackedReader.Unpack` | `m_output[dst++] = m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SPack.SPackEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte     Method ;

public ushort   Crc ;
```

### GameRes.Formats.SPack.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if ('k' != file.View.ReadInt16 (4))
        return null;
    int version = file.View.ReadInt16 (6);
    if (1 != version)
        return null;
    uint data_size = file.View.ReadUInt32 (8);
    int count = file.View.ReadInt32 (0x10);
    if (count <= 0 || count > 0xfffff)
        return null;
    uint index_size = (uint)(0x38 * count);
    long base_offset = 0x18;
    long index_offset = base_offset + data_size;
    if (index_offset >= file.MaxOffset || index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x20);
        index_offset += 0x20;
        var entry = new SPackEntry
        {
            Name   = name,
            Offset = base_offset + file.View.ReadUInt32 (index_offset),
            UnpackedSize = file.View.ReadUInt32 (index_offset+4),
            Size   = file.View.ReadUInt32 (index_offset+8),
            Method = file.View.ReadByte (index_offset+12),
            Crc    = file.View.ReadUInt16 (index_offset+14),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".dat"))
            entry.Type = "audio";
        else
            entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
        entry.IsPacked = entry.Method != 0;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var packed_entry = entry as SPackEntry;
    if (null == packed_entry || !packed_entry.IsPacked)
        return input;
    if (1 == packed_entry.Method)
        return new InputCryptoStream (input, new NotTransform());
    if (2 == packed_entry.Method)
    {
        using (var reader = new PackedReader (packed_entry, input))
        {
            reader.Unpack();
            return new BinMemoryStream (reader.Data, entry.Name);
        }
    }
    return input;
}
```

### GameRes.Formats.SPack.PackedReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

uint            m_packed_size ;

byte[]          m_output ;

public byte[] Data { get { return m_output; } }

bool disposed = false ;
```

#### PackedReader

```csharp
public PackedReader (SPackEntry entry, IBinaryStream input) {
    m_input = input;
    m_packed_size = entry.Size;
    m_output = new byte[entry.UnpackedSize];
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    int dst = 0;
    uint src = 0;
    uint ctl = 0;
    uint mask = 0;

    while (dst < m_output.Length && src < m_packed_size)
    {
        if (0 == mask)
        {
            ctl = m_input.ReadUInt32();
            src += 4;
            mask = 0x80000000;
        }
        if (0 != (ctl & mask))
        {
            int copy_count, offset;

            offset = m_input.ReadUInt8();
            src++;
            copy_count = offset >> 4;
            offset &= 0x0f;
            if (15 == copy_count)
            {
                copy_count = m_input.ReadUInt16();
                src += 2;
            }
            else if (14 == copy_count)
            {
                copy_count = m_input.ReadUInt8();
                src++;
            }
            else
                copy_count++;

            if (offset < 10)
                offset++;
            else
            {
                offset = ((offset - 10) << 8) | m_input.ReadUInt8();
                src++;
            }

            if (dst + copy_count > m_output.Length)
                copy_count = m_output.Length - dst;
            Binary.CopyOverlapped (m_output, dst-offset, dst, copy_count);
            dst += copy_count;
        }
        else
        {
            m_output[dst++] = m_input.ReadUInt8();
            src++;
        }
        mask >>= 1;
    }
    return m_output;
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ArcSPack.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
