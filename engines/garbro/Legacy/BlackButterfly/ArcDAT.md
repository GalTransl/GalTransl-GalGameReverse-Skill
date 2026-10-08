# BlackButterfly / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PITA` / `GameRes.Formats.BlackButterfly.DatOpener` | `dat` | `50495441` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `DatOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_pos);` |
| `DatOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_pos);` |
| `DatOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (pent.Offset);` |
| `DatOpener.Unpack` | `byte ctl = input.ReadUInt8();` |
| `DatOpener.Unpack` | `int offset = (ctl & 3) << 8 \| input.ReadUInt8();` |
| `DatOpener.Unpack` | `count = input.ReadUInt8() + 32;` |
| `DatOpener.Unpack` | `byte fill = input.ReadUInt8();` |
| `DatOpener.Unpack` | `output[dst++] = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackButterfly.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_pos = 0x10;
    uint next_offset = file.View.ReadUInt32 (index_pos);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_pos += 4;
        var entry = new PackedEntry {
            Name = string.Format ("{0:D5}.bmp", i),
            Type = "image",
            Offset = next_offset,
        };
        next_offset = file.View.ReadUInt32 (index_pos);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    if (!pent.IsPacked)
    {
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (pent.Offset);
    }
    using (var input = arc.File.CreateStream (pent.Offset+4, pent.Size-4))
    {
        var data = new byte[pent.UnpackedSize];
        Unpack (input, data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### Unpack

```csharp
void Unpack (IBinaryStream input, byte[] output) {
    int dst = 0;
    while (input.PeekByte() != -1)
    {
        byte ctl = input.ReadUInt8();
        if (0x7F == ctl)
        {
            if (input.PeekByte() == 0xFF)
                break;
        }
        int count;
        if (ctl <= 0x7F)
        {
            count = (ctl >> 2) + 2;
            int offset = (ctl & 3) << 8 | input.ReadUInt8();
            offset = (offset ^ 0x3FF) + 1;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
        else if (ctl > 0xFE)
        {
            count = input.ReadUInt8() + 32;
            while (count --> 0)
                output[dst++] = 0;
        }
        else if (ctl > 0xDF)
        {
            count = (ctl & 0x1F) + 1;
            while (count --> 0)
                output[dst++] = 0;
        }
        else if (ctl > 0xBF)
        {
            count = (ctl & 0x1F) + 2;
            byte fill = input.ReadUInt8();
            while (count --> 0)
                output[dst++] = fill;
        }
        else if (ctl > 0x9F)
        {
            count = (ctl & 0x1F) + 1;
            while (count --> 0)
            {
                output[dst++] = 0;
                output[dst++] = input.ReadUInt8();
            }
        }
        else
        {
            count = (ctl & 0x1F) + 1;
            input.Read (output, dst, count);
            dst += count;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/BlackButterfly/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
