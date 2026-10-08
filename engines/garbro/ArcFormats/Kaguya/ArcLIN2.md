# Kaguya / ArcLIN2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/LIN2` / `GameRes.Formats.Kaguya.Lin2Opener` | `arc` | `4c494e32` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Lin2Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Lin2Opener.TryOpen` | `ushort name_length = file.View.ReadUInt16 (index_offset);` |
| `Lin2Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `Lin2Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |
| `Lin2Opener.TryOpen` | `int type = file.View.ReadInt16 (index_offset+8);` |
| `Lin2Opener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |
| `Lin2Opener.UnpackLzss` | `ctl = input.ReadByte();` |
| `Lin2Opener.UnpackLzss` | `byte v = input.ReadUInt8();` |
| `Lin2Opener.UnpackLzss` | `int offset = input.ReadUInt8();` |
| `Lin2Opener.UnpackLzss` | `prev_count = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.Lin2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 8;
    var name_buffer = new byte[0x100];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        ushort name_length = file.View.ReadUInt16 (index_offset);
        if (name_length > name_buffer.Length)
            name_buffer = new byte[name_length];
        file.View.Read (index_offset+2, name_buffer, 0, name_length);
        for (int j = 0; j < name_length; ++j)
            name_buffer[j] ^= 0xFF;
        var name = Binary.GetCString (name_buffer, 0, name_length);
        if (string.IsNullOrEmpty (name))
            return null;
        index_offset += 2u + name_length;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset);
        entry.Size   = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        int type = file.View.ReadInt16 (index_offset+8);
        if (1 == type)
            entry.IsPacked = true;
        else if (2 == type)
            entry.Type = "audio";
        dir.Add (entry);
        index_offset += 10;
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
    if (0 == pent.UnpackedSize)
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
    using (var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4))
    {
        var data = UnpackLzss (input, pent.UnpackedSize);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### UnpackLzss

```csharp
internal static byte[] UnpackLzss (IBinaryStream input, uint unpacked_size) {
    var output = new byte[unpacked_size];
    var frame = new byte[0x100];
    int frame_pos = 0xEF;
    int dst = 0;
    int ctl = 0;
    int bit = 0;
    int prev_count = -1;
    while (dst < output.Length)
    {
        bit >>= 1;
        if (0 == bit)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            bit = 0x80;
        }
        if (0 != (ctl & bit))
        {
            byte v = input.ReadUInt8();
            frame[frame_pos++ & 0xFF] = v;
            output[dst++] = v;
        }
        else
        {
            int offset = input.ReadUInt8();
            int count;
            if (-1 == prev_count)
            {
                prev_count = input.ReadUInt8();
                count = prev_count & 0xF;
            }
            else
            {
                count = prev_count >> 4;
                prev_count = -1;
            }
            count += 2;
            while (count --> 0 && dst < output.Length)
            {
                byte v = frame[offset++ & 0xFF];
                frame[frame_pos++ & 0xFF] = v;
                output[dst++] = v;
            }
        }
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcLIN2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
