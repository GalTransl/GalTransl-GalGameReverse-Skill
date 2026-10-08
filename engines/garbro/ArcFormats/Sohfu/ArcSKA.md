# Sohfu / ArcSKA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SKA/SOHFU` / `GameRes.Formats.Sohfu.SkaOpener` | `ska` | `49504632` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SkaOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `SkaOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_pos+0x10);` |
| `SkaOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_pos+0x14);` |
| `SkaOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (pent.Offset+4);` |
| `SkaOpener.LzssUnpack` | `ctl = input.ReadByte();` |
| `SkaOpener.LzssUnpack` | `int b = input.ReadByte();` |
| `SkaOpener.LzssUnpack` | `int lo = input.ReadByte();` |
| `SkaOpener.LzssUnpack` | `int hi = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sohfu.SkaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_pos = 8;
    var name_buffer = new byte[0x10];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_pos, name_buffer, 0, 0x10);
        int name_len = 0;
        while (name_len < name_buffer.Length && name_buffer[name_len] != 0)
            ++name_len;
        var name = Encodings.cp932.GetString (name_buffer, 0, name_len);
        ++name_len;
        string ext = null;
        if (name_len < 0x10)
            ext  = Binary.GetCString (name_buffer, name_len, 0x10 - name_len);
        if (!string.IsNullOrEmpty (ext))
            name = Path.ChangeExtension (name, ext);
        var entry = Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_pos+0x10);
        entry.Size   = file.View.ReadUInt32 (index_pos+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (!pent.IsPacked)
    {
        if (input.Signature != 0x4238534C)
            return input;
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (pent.Offset+4);
    }
    using (input)
    {
        var data = new byte[pent.UnpackedSize];
        input.Position = 0xC;
        LzssUnpack (input, data);
        return new BinMemoryStream (data);
    }
}
```

#### LzssUnpack

```csharp
void LzssUnpack (IBinaryStream input, byte[] output) {
    byte[] frame = new byte[0x1000];
    int frame_pos = 0xFFF;
    const int frame_mask = 0xFFF;
    int ctl = 1;
    int dst = 0;
    while (dst < output.Length)
    {
        if (1 == ctl)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            ctl |= 0x100;
        }
        if (0 == (ctl & 1))
        {
            int b = input.ReadByte();
            if (-1 == b)
                break;
            frame[++frame_pos & frame_mask] = (byte)b;
            output[dst++] = (byte)b;
        }
        else
        {
            int lo = input.ReadByte();
            if (-1 == lo)
                break;
            int hi = input.ReadByte();
            if (-1 == hi)
                break;
            int offset = hi << 4 | lo >> 4;
            for (int count = 3 + (lo & 0xF); count != 0; --count)
            {
                byte v = frame[(offset + frame_pos++ - 0xFFF) & frame_mask];
                frame[frame_pos & frame_mask] = v;
                output[dst++] = v;
            }
        }
        ctl >>= 1;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Sohfu/ArcSKA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
