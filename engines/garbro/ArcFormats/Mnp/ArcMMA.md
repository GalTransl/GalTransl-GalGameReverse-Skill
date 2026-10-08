# Mnp / ArcMMA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MMA` / `GameRes.Formats.Mnp.MmaOpener` | `mma` | `41524321` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MmaOpener.TryOpen` | `int version = file.View.ReadInt32 (0xC);` |
| `MmaOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `MmaOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (4);` |
| `MmaOpener.TryOpen` | `Offset       = file.View.ReadUInt32 (index_offset),` |
| `MmaOpener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset+4),` |
| `MmaOpener.TryOpen` | `Size         = file.View.ReadUInt32 (index_offset+8),` |
| `MmaOpener.TryOpen` | `HeaderSize   = file.View.ReadUInt32 (index_offset+0x0C),` |
| `MmaOpener.TryOpen` | `Flags        = file.View.ReadUInt32 (index_offset+0x10),` |
| `MmaOpener.UnpackEntry` | `var data = input.ReadBytes ((int)entry.UnpackedSize);` |
| `MmaOpener.UnpackLz` | `byte id = input.ReadUInt8();` |
| `MmaOpener.UnpackLz` | `ctl = input.ReadByte();` |
| `MmaOpener.UnpackLz` | `int offset = input.ReadUInt8() << 8;` |
| `MmaOpener.UnpackLz` | `offset \|= input.ReadUInt8();` |
| `MmaOpener.UnpackLz` | `output[dst++] = Binary.RotByteL (input.ReadUInt8(), 5);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum MnpMethod : int
    {
        Scheme03,
        Scheme06,
    }
```

### GameRes.Formats.Mnp.MmaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint HeaderSize ;

public uint Flags ;
```

### GameRes.Formats.Mnp.MmaOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] DefaultKey = {
    0x77, 0x2C, 0x6F, 0x7A, 0x71, 0x4F, 0x25, 0x74, 0x6C, 0x28, 0x7A, 0x81, 0x4C, 0x31, 0x81, 0x5B,
    0x77, 0x81, 0x4D, 0x79, 0x29, 0x69, 0x45, 0x6B, 0x79, 0x7A, 0x68, 0x2D, 0x69, 0x66, 0x29, 0x39,
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (0xC);
    if (version != 1)
        return null;
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (4);
    if (index_offset >= file.MaxOffset)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new MmaEntry {
            Name         = string.Format ("{0}#{1:D5}", base_name, i),
            Offset       = file.View.ReadUInt32 (index_offset),
            UnpackedSize = file.View.ReadUInt32 (index_offset+4),
            Size         = file.View.ReadUInt32 (index_offset+8),
            HeaderSize   = file.View.ReadUInt32 (index_offset+0x0C),
            Flags        = file.View.ReadUInt32 (index_offset+0x10),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        switch (entry.Flags & 0x38)
        {
        case 8:
        case 0x10:
        case 0x18:
        case 0x38:
            entry.Type = "image";
            break;
        default:
            if (0x2D == entry.Flags)
                entry.Type = "audio";
            break;
        }
        dir.Add (entry);
        index_offset += 0x14;
    }
    var list_entry = dir[0] as MmaEntry;
    if (0x2F == list_entry.Flags)
    {
        ReadMmaList (file, dir, list_entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### ReadMmaList

```csharp
void ReadMmaList (ArcView file, List<Entry> dir, MmaEntry index_entry) {
    using (var packed = file.CreateStream (index_entry.Offset, index_entry.Size))
    using (var unpacked = UnpackEntry (packed, index_entry))
    using (var index = new StreamReader (unpacked, Encodings.cp932))
    {
        for (int i = 0; i < dir.Count; ++i)
        {

            var name = index.ReadLine();
            if (null == name)
                break;
            dir[i].Name = Path.GetFileName (name);
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var ment = entry as MmaEntry;
    if (null == ment)
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return UnpackEntry (input, ment);
}
```

#### UnpackEntry

```csharp
Stream UnpackEntry (IBinaryStream input, MmaEntry entry) {
    uint flags = entry.Flags & 6;
    if (6 == flags && 0 == entry.HeaderSize)
    {
        using (input)
        {
            var data = new byte[entry.UnpackedSize];
            UnpackLz (input, data, 0);
            return new BinMemoryStream (data, entry.Name);
        }
    }
    else if (4 == flags)
    {
        using (input)
        {
            input.Position = (int)entry.HeaderSize;
            var data = input.ReadBytes ((int)entry.UnpackedSize);
            Decrypt (data, 0, data.Length);
            return new BinMemoryStream (data, entry.Name);
        }
    }
    return input.AsStream;
}
```

#### Decrypt

```csharp
internal static void Decrypt (byte[] data, int offset, int length) {
    int key_mask = DefaultKey.Length - 1;
    for (int i = 0; i < length; ++i)
    {
        byte x = (byte)(data[offset+i] ^ DefaultKey[i & key_mask]);
        data[offset+i] = Binary.RotByteR (x, 3);
    }
}
```

#### UnpackLz

```csharp
internal static void UnpackLz (IBinaryStream input, byte[] output, int dst = 0) {
    byte id = input.ReadUInt8();
    if (id != 0xC0)
    {
        if ((id ^ DefaultKey[0]) == 0xC0)
        {
            Stream decrypted = input.AsStream;
            long start_pos = input.Position;
            if (start_pos != 1)
                decrypted = new StreamRegion (decrypted, start_pos - 1);
            decrypted = new ByteStringEncryptedStream (decrypted, DefaultKey);
            input = new BinaryStream (decrypted, input.Name);
            input.Position = 1;
        }
        else
        {
            if (id != 0)
                throw new InvalidFormatException();
            input.Read (output, 0, output.Length);
            return;
        }
    }
    int ctl = 0;
    int mask = 0;
    while (dst < output.Length)
    {
        if (0 == mask)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            mask = 0x80;
        }
        if ((ctl & mask) != 0)
        {
            int offset = input.ReadUInt8() << 8;
            offset |= input.ReadUInt8();
            int count = (offset & 0x1F) + 3;
            offset = (offset >> 5) + 1;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
        else
        {
            output[dst++] = Binary.RotByteL (input.ReadUInt8(), 5);
        }
        mask >>= 1;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Mnp/ArcMMA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
