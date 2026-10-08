# Hypatia / ArcKogado：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/HyPack` / `GameRes.Formats.Hypatia.PakOpener` | `pak`, `dat` | `48795061` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "HyPack"))` |
| `PakOpener.TryOpen` | `int version = file.View.ReadUInt16 (6);` |
| `PakOpener.TryOpen` | `long index_offset = 0x10 + file.View.ReadUInt32 (8);` |
| `PakOpener.TryOpen` | `int entry_count = file.View.ReadInt32 (12);` |
| `PakOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x15);` |
| `PakOpener.TryOpen` | `string ext  = file.View.ReadString (index_offset+0x15, 3);` |
| `PakOpener.TryOpen` | `entry.Offset        = data_offset + file.View.ReadUInt32 (index_offset + 0x18);` |
| `PakOpener.TryOpen` | `entry.UnpackedSize  = file.View.ReadUInt32 (index_offset + 0x1c);` |
| `PakOpener.TryOpen` | `entry.Size          = file.View.ReadUInt32 (index_offset + 0x20);` |
| `PakOpener.TryOpen` | `entry.CompressionType = file.View.ReadByte (index_offset + 0x24);` |
| `PakOpener.TryOpen` | `entry.HasCheckSum = 0 != file.View.ReadByte (index_offset + 0x25);` |
| `PakOpener.TryOpen` | `entry.CheckSum  = file.View.ReadUInt16 (index_offset + 0x26);` |
| `PakOpener.TryOpen` | `entry.FileTime  = file.View.ReadInt64 (index_offset + 0x28);` |
| `PakOpener.TryOpen` | `entry.Size          = file.View.ReadUInt32 (index_offset + 0x1c);` |
| `MarielEncoder.Unpack` | `bits = input.ReadUInt32();` |
| `MarielEncoder.Unpack` | `int b = input.ReadByte();` |
| `MarielEncoder.Unpack` | `b = input.ReadByte();` |
| `MarielEncoder.Unpack` | `count = input.ReadUInt16();` |
| `MarielEncoder.Unpack` | `offset \|= input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Hypatia.HypEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte     CompressionType ;

public bool     HasCheckSum ;

public ushort   CheckSum ;

public long     FileTime ;
```

### GameRes.Formats.Hypatia.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak", "dat" };
    ContainedFormats = new[] {
        "PNG", "BMP", "JPEG", "WBM/HYPATIA",
        "OGG", "WAV", "ADP/HYPATIA",
        "TXT", "SCR"
    };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "HyPack"))
        return null;
    int version = file.View.ReadUInt16 (6);
    int entry_size;
    switch (version)
    {
    case 0x100: entry_size = 32; break;
    case 0x200: entry_size = 40; break;
    case 0x300:
    case 0x301: entry_size = 48; break;
    default: return null;
    }
    long index_offset = 0x10 + file.View.ReadUInt32 (8);
    if (index_offset >= file.MaxOffset)
        return null;
    int entry_count = file.View.ReadInt32 (12);
    if (entry_count <= 0 || entry_count > 0xfffff)
        return null;
    uint index_size = (uint)(entry_count * entry_size);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    long data_offset = 0x10;

    var dir = new List<Entry> (entry_count);
    for (int i = 0; i < entry_count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x15);
        string ext  = file.View.ReadString (index_offset+0x15, 3);
        if (0 == name.Length)
            name = i.ToString ("D5");
        if (0 != ext.Length)
            name += '.'+ext;
        var entry = Create<HypEntry> (name);
        entry.Offset        = data_offset + file.View.ReadUInt32 (index_offset + 0x18);
        if (version >= 0x200)
        {
            entry.UnpackedSize  = file.View.ReadUInt32 (index_offset + 0x1c);
            entry.Size          = file.View.ReadUInt32 (index_offset + 0x20);
            entry.CompressionType = file.View.ReadByte (index_offset + 0x24);
            entry.IsPacked      = 0 != entry.CompressionType;
            if (version >= 0x300)
            {
                entry.HasCheckSum = 0 != file.View.ReadByte (index_offset + 0x25);
                entry.CheckSum  = file.View.ReadUInt16 (index_offset + 0x26);
                entry.FileTime  = file.View.ReadInt64 (index_offset + 0x28);
            }
        }
        else
            entry.Size          = file.View.ReadUInt32 (index_offset + 0x1c);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var packed_entry = entry as HypEntry;
    if (null == packed_entry || !packed_entry.IsPacked)
        return input;
    if (packed_entry.CompressionType > 3)
    {
        Trace.WriteLine (string.Format ("{1}: Unknown compression type {0}",
                                        packed_entry.CompressionType, packed_entry.Name),
                         "Kogado.PakOpener.OpenEntry");
        return input;
    }
    if (3 == packed_entry.CompressionType)
        return new InputCryptoStream (input, new NotTransform());
    try
    {
        if (2 == packed_entry.CompressionType)
        {
            var decoded = new MemoryStream ((int)packed_entry.UnpackedSize);
            try
            {
                var cocotte = new CocotteEncoder();
                if (!cocotte.Decode (input, decoded))
                    throw new InvalidFormatException ("Invalid Cocotte-encoded stream");
                decoded.Position = 0;
                return decoded;
            }
            catch
            {
                decoded.Dispose();
                throw;
            }
        }

        var unpacked = new byte[packed_entry.UnpackedSize];
        var mariel = new MarielEncoder();
        mariel.Unpack (input, unpacked, unpacked.Length);
        return new BinMemoryStream (unpacked, entry.Name);
    }
    finally
    {
        input.Dispose();
    }
}
```

### GameRes.Formats.Hypatia.MarielEncoder

#### Unpack

```csharp
public void Unpack (IBinaryStream input, byte[] dest, int dest_size) {
    int out_pos = 0;
    uint bits = 0;
    while (dest_size > 0)
    {
        bool carry = 0 != (bits & 0x80000000);
        bits <<= 1;
        if (0 == bits)
        {
            bits = input.ReadUInt32();
            carry = 0 != (bits & 0x80000000);
            bits = (bits << 1) | 1u;
        }
        int b = input.ReadByte();
        if (-1 == b)
            break;
        if (!carry)
        {
            dest[out_pos++] = (byte)b;
            dest_size--;
            continue;
        }
        int offset = (b & 0x0f) + 1;
        int count = ((b >> 4) & 0x0f) + 1;
        if (0x0f == count)
        {
            b = input.ReadByte();
            if (-1 == b)
                break;
            count = (byte)b;
        }
        else if (count > 0x0f)
        {
            count = input.ReadUInt16();
        }
        if (offset >= 0x0b)
        {
            offset -= 0x0b;
            offset <<= 8;
            offset |= input.ReadUInt8();
        }
        if (count > dest_size)
            count = dest_size;
        int src = out_pos - offset;
        if (src < 0 || src >= out_pos)
            break;
        Binary.CopyOverlapped (dest, src, out_pos, count);
        out_pos += count;
        dest_size -= count;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/KogadoCocotte.cs](../KogadoCocotte.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Hypatia/ArcKogado.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
