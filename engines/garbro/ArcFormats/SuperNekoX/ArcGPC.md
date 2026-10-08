# SuperNekoX / ArcGPC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GPC7` / `GameRes.Formats.SuperNekoX.GpcOpener` | `gpc` | `47706337` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GpcOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `GpcOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `GpcOpener.TryOpen` | `next_offset = i + 1 < count ? file.View.ReadUInt32 (index_offset) : (uint)file.MaxOffset;` |
| `GpcOpener.OpenEntry` | `int unpacked_size = input.ReadUInt16();` |
| `GpcOpener.OpenEntry` | `int packed_size = input.ReadUInt16();` |
| `GpcOpener.DetectFileTypes` | `uint packed_size = input.ReadUInt32();` |
| `GpcOpener.DetectFileTypes` | `entry.UnpackedSize = input.ReadUInt32();` |
| `GpcOpener.DetectFileTypes` | `signature = LittleEndian.ToUInt32 (buffer, 0);` |
| `GpcOpener.DetectFileTypes` | `signature = input.ReadUInt32();` |
| `GpcOpener.UnpackEntry` | `int ctl = input.ReadByte();` |
| `GpcOpener.UnpackEntry` | `offset \|= input.ReadByte();` |
| `GpcOpener.UnpackEntry` | `count = input.ReadByte() + 4;` |
| `GpcOpener.UnpackEntry` | `offset = (ctl & 0x1F) << 8 \| input.ReadByte();` |
| `GpcOpener.UnpackEntry` | `count  = input.ReadByte() << 24;` |
| `GpcOpener.UnpackEntry` | `count \|= input.ReadByte() << 16;` |
| `GpcOpener.UnpackEntry` | `count \|= input.ReadByte() << 8;` |
| `GpcOpener.UnpackEntry` | `count \|= input.ReadByte();` |
| `GpcOpener.UnpackEntry` | `count = input.ReadByte() + 0x1E;` |
| `GpcOpener.UnpackEntry` | `count  = input.ReadByte() << 8;` |
| `GpcOpener.UnpackLz77` | `bits = input.ReadByte();` |
| `GpcOpener.UnpackLz77` | `int count = input.ReadByte();` |
| `GpcOpener.UnpackLz77` | `int offset = input.ReadByte() << 4 \| count >> 4;` |
| `GpcOpener.UnpackLz77` | `output[dst++] = (byte)input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SuperNekoX.GpcOpener

继承/接口：`ArchiveFormat`。

#### GpcOpener

```csharp
public GpcOpener () {
    Extensions = new string[] { "gpc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    int index_offset = 8;
    long data_offset = count * 4 + 8;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new PackedEntry { Offset = next_offset };
        next_offset = i + 1 < count ? file.View.ReadUInt32 (index_offset) : (uint)file.MaxOffset;
        entry.Size = next_offset - (uint)entry.Offset;
        if (entry.Offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Name = string.Format ("{0}#{1:D4}", base_name, i);
        dir.Add (entry);
    }
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    IBinaryStream input = arc.File.CreateStream (entry.Offset, entry.Size, entry.Name);
    if (null != pent && pent.IsPacked)
    {
        IBinaryStream unpacked;
        using (input)
        {
            var data = new byte[pent.UnpackedSize];
            UnpackEntry (input.AsStream, data);
            unpacked = new BinMemoryStream (data, entry.Name);
        }
        input = unpacked;
    }
    if (input.Length > 4 && input.Length < 0x10000)
    {
        int unpacked_size = input.ReadUInt16();
        int packed_size = input.ReadUInt16();
        if (packed_size == input.Length-4)
        {
            using (input)
            {
                var data = new byte[unpacked_size];
                UnpackLz77 (input.AsStream, data);
                return new BinMemoryStream (data, entry.Name);
            }
        }
        input.Position = 0;
    }
    return input.AsStream;
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (ArcView file, List<Entry> dir) {
    using (var input = file.CreateStream())
    {
        var buffer = new byte[0x10];
        foreach (PackedEntry entry in dir)
        {
            input.Position = entry.Offset;
            uint packed_size = input.ReadUInt32();
            entry.UnpackedSize = input.ReadUInt32();
            entry.Offset += 8;
            if (0 == packed_size)
            {
                entry.Size = entry.UnpackedSize;
            }
            else
            {
                entry.IsPacked = true;
                entry.Size = packed_size;
            }
            if (entry.Size < 0x10)
                continue;
            uint signature;
            if (entry.IsPacked)
            {
                UnpackEntry (input, buffer);
                signature = LittleEndian.ToUInt32 (buffer, 0);
            }
            else
                signature = input.ReadUInt32();
            IResource res;
            if (0x020000 == signature || 0x0A0000 == signature)
                res = ImageFormat.Tga;
            else
                res = AutoEntry.DetectFileType (signature);
            if (null != res)
                entry.ChangeType (res);
        }
    }
}
```

#### UnpackEntry

```csharp
void UnpackEntry (Stream input, byte[] output) {
    int dst = 0;
    while (dst < output.Length)
    {
        int ctl = input.ReadByte();
        if (-1 == ctl)
            break;
        int count, offset;
        if (ctl >= 0x20)
        {
            if (ctl >= 0x80)
            {
                count = (ctl >> 5) & 3;
                offset = (ctl & 0x1F) << 8;
                offset |= input.ReadByte();
            }
            else if ((ctl & 0x60) == 0x20)
            {
                offset = (ctl >> 2) & 7;
                count = ctl & 3;
            }
            else if ((ctl & 0x60) == 0x40)
            {
                offset = (ctl & 0x1F) << 8;
                offset |= input.ReadByte();
                count = input.ReadByte() + 4;
            }
            else
            {
                offset = (ctl & 0x1F) << 8 | input.ReadByte();
                count  = input.ReadByte() << 24;
                count |= input.ReadByte() << 16;
                count |= input.ReadByte() << 8;
                count |= input.ReadByte();
            }
            count = Math.Min (count + 3, output.Length-dst);
            Binary.CopyOverlapped (output, dst-offset-1, dst, count);
        }
        else
        {
            if (ctl < 0x1D)
            {
                count = ctl + 1;
            }
            else if (0x1D == ctl)
            {
                count = input.ReadByte() + 0x1E;
            }
            else if (0x1E == ctl)
            {
                count  = input.ReadByte() << 8;
                count |= input.ReadByte();
                count += 286;
            }
            else
            {
                count  = input.ReadByte() << 24;
                count |= input.ReadByte() << 16;
                count |= input.ReadByte() << 8;
                count |= input.ReadByte();
            }
            count = Math.Min (count, output.Length-dst);
            input.Read (output, dst, count);
        }
        dst += count;
    }
}
```

#### UnpackLz77

```csharp
void UnpackLz77 (Stream input, byte[] output) {
    int dst = 0;
    int mask = 0;
    int bits = 0;
    while (dst < output.Length)
    {
        mask >>= 1;
        if (0 == mask)
        {
            bits = input.ReadByte();
            if (-1 == bits)
                break;
            mask = 0x80;
        }
        if (0 != (bits & mask))
        {
            int count = input.ReadByte();
            int offset = input.ReadByte() << 4 | count >> 4;
            count = Math.Min ((count & 0xf) + 3, output.Length - dst);
            Binary.CopyOverlapped (output, dst-offset-1, dst, count);
            dst += count;
        }
        else
        {
            output[dst++] = (byte)input.ReadByte();
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/SuperNekoX/ArcGPC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
