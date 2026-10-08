# DaiSystem / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/DAI` / `GameRes.Formats.DaiSystem.PacOpener` | `pac` | `4441495f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "SYSTEM_01000"))` |
| `PacOpener.TryOpen` | `int count = Binary.BigEndian (file.View.ReadUInt16 (0x10));` |
| `PacOpener.TryOpen` | `uint index_size = Binary.BigEndian (file.View.ReadUInt32 (0x12));` |
| `PacOpener.TryOpen` | `var index = file.View.ReadBytes (0x16, index_size);` |
| `PacOpener.TryOpen` | `entry.Offset = BigEndian.ToUInt32 (index, index_offset);` |
| `PacOpener.DetectFileTypes` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `PacOpener.DetectFileTypes` | `uint encryption = file.View.ReadUInt32 (entry.Offset+8);` |
| `PacOpener.DetectFileTypes` | `uint bits = Binary.BigEndian (file.View.ReadUInt32 (offset + 8));` |
| `PacOpener.DetectFileTypes` | `if (file.View.AsciiEqual (offset+12+bits, "BM"))` |
| `PacOpener.DetectFileTypes` | `else if (file.View.AsciiEqual (entry.Offset+entry.Size-0x12, "TRUEVISION"))` |
| `PacOpener.DetectFileTypes` | `signature = file.View.ReadUInt32 (offset);` |
| `PacOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "HA0"))` |
| `PacOpener.OpenEntry` | `byte header_length = arc.File.View.ReadByte (entry.Offset+3);` |
| `PacOpener.OpenEntry` | `uint unpacked_size = Binary.BigEndian (arc.File.View.ReadUInt32 (entry.Offset+4));` |
| `PacOpener.OpenEntry` | `uint pattern = arc.File.View.ReadUInt32 (entry.Offset+8);` |
| `PacOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (entry.Offset+0x10, header_length);` |
| `PacOpener.OpenEntry` | `var input = arc.File.View.ReadBytes (entry.Offset + ha0_header_length, entry.Size - ha0_header_length);` |
| `PacOpener.Unpack4` | `int unpacked_size = BigEndian.ToInt32 (input, 0);` |
| `PacOpener.Unpack4` | `int ctl_bits = BigEndian.ToInt32 (input, 4);` |
| `PacOpener.Unpack4` | `int ctl_bytes = BigEndian.ToInt32 (input, 8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DaiSystem.PacOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "SYSTEM_01000"))
        return null;
    int count = Binary.BigEndian (file.View.ReadUInt16 (0x10));
    if (!IsSaneCount (count))
        return null;
    uint index_size = Binary.BigEndian (file.View.ReadUInt32 (0x12));
    var index = file.View.ReadBytes (0x16, index_size);
    for (int i = 0; i < index.Length; ++i)
        index[i] -= (byte)(i + 0x28);

    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_end = Array.IndexOf<byte> (index, (byte)',', index_offset);
        if (-1 == name_end)
            return null;
        var name = Encodings.cp932.GetString (index, index_offset, name_end - index_offset);
        index_offset = name_end + 1;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = BigEndian.ToUInt32 (index, index_offset);
        index_offset += 5;
        dir.Add (entry);
    }
    for (int i = 1; i < dir.Count; ++i)
    {
        var entry = dir[i-1];
        entry.Size = (uint)(dir[i].Offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
    }
    dir[dir.Count-1].Size = (uint)(file.MaxOffset - dir[dir.Count-1].Offset);
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (ArcView file, List<Entry> dir) {
    foreach (var entry in dir.Where (e => string.IsNullOrEmpty (e.Type)))
    {
        uint signature = file.View.ReadUInt32 (entry.Offset);
        if (0x05304148 == signature)
        {
            entry.Type = "image";
            continue;
        }
        else if (0x304148 == (signature & 0xFFFFFF))
        {
            uint encryption = file.View.ReadUInt32 (entry.Offset+8);
            long offset = entry.Offset + 0x10 + (signature >> 24);
            if (0 != encryption)
            {
                if (4 == encryption)
                {
                    uint bits = Binary.BigEndian (file.View.ReadUInt32 (offset + 8));
                    if (bits > entry.Size)
                        continue;
                    if (file.View.AsciiEqual (offset+12+bits, "BM"))
                    {
                        entry.ChangeType (ImageFormat.Bmp);
                    }
                    else if (file.View.AsciiEqual (entry.Offset+entry.Size-0x12, "TRUEVISION"))
                    {
                        entry.ChangeType (ImageFormat.Tga);
                    }
                }
                continue;
            }
            signature = file.View.ReadUInt32 (offset);
        }
        entry.ChangeType (AutoEntry.DetectFileType (signature));
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!arc.File.View.AsciiEqual (entry.Offset, "HA0"))
        return base.OpenEntry (arc, entry);
    byte header_length = arc.File.View.ReadByte (entry.Offset+3);
    uint ha0_header_length = 0x10u + header_length;
    if (ha0_header_length >= entry.Size)
        return base.OpenEntry (arc, entry);
    uint unpacked_size = Binary.BigEndian (arc.File.View.ReadUInt32 (entry.Offset+4));
    uint pattern = arc.File.View.ReadUInt32 (entry.Offset+8);
    var header = arc.File.View.ReadBytes (entry.Offset+0x10, header_length);
    var input = arc.File.View.ReadBytes (entry.Offset + ha0_header_length, entry.Size - ha0_header_length);
    while (pattern != 0)
    {
        uint code = pattern >> 24;
        switch (code)
        {
        case 0: break;
        case 2: input = Decrypt2 (input); break;
        case 3: input = Decrypt3 (input); break;
        case 4: input = Unpack4 (input); break;
        default:
            Trace.WriteLine (string.Format ("Unknown encryption method ({0})", code), "[DAI_SYSTEM]");
            return base.OpenEntry (arc, entry);
        }
        pattern <<= 8;
    }
    return new BinMemoryStream (input, entry.Name);
}
```

#### Decrypt2

```csharp
byte[] Decrypt2 (byte[] input) {
    var output = new byte[input.Length];
    int src = 0;
    for (int i = 0; i < 3; ++i)
    {
        for (int dst = i; dst < output.Length; dst += 3)
            output[dst] = input[src++];
    }
    return output;
}
```

#### Decrypt3

```csharp
byte[] Decrypt3 (byte[] input) {
    for (int i = 1; i < input.Length; ++i)
    {
        input[i] += input[i-1];
    }
    return input;
}
```

#### Unpack4

```csharp
byte[] Unpack4 (byte[] input) {
    int unpacked_size = BigEndian.ToInt32 (input, 0);
    var output = new byte[unpacked_size];
    int ctl_bits = BigEndian.ToInt32 (input, 4);
    int ctl_bytes = BigEndian.ToInt32 (input, 8);
    int ctl = 12;
    int src = 12 + ctl_bytes;
    int dst = 0;
    int bits = 2;
    while (dst < output.Length)
    {
        bits >>= 1;
        if (1 == bits)
        {
            bits = input[ctl++] | 0x100;
        }
        if (0 == (bits & 1))
        {
            output[dst++] = input[src++];
        }
        else
        {
            int offset = input[src++];
            int count  = input[src++];
            Binary.CopyOverlapped (output, dst-offset, dst, count);
            dst += count;
        }
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/DaiSystem/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
