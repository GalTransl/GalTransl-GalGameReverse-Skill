# Sogna / ArcSGS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/SGS` / `GameRes.Formats.Sogna.SgsDatOpener` | `dat` | `5347532e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SgsDatOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "DAT 1.00"))` |
| `SgsDatOpener.TryOpen` | `int count = file.View.ReadInt32 (12);` |
| `SgsDatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `SgsDatOpener.TryOpen` | `entry.IsPacked      = file.View.ReadByte (index_offset+0x13) != 0;` |
| `SgsDatOpener.TryOpen` | `entry.Size          = file.View.ReadUInt32 (index_offset+0x14);` |
| `SgsDatOpener.TryOpen` | `entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0x18);` |
| `SgsDatOpener.TryOpen` | `entry.Offset        = file.View.ReadUInt32 (index_offset+0x1C);` |
| `SgsDatOpener.LzUnpack` | `bits = input.ReadByte();` |
| `SgsDatOpener.LzUnpack` | `int offset = input.ReadUInt16();` |
| `SgsDatOpener.LzUnpack` | `output[dst++] = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sogna.SgsDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "DAT 1.00"))
        return null;
    int count = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.IsPacked      = file.View.ReadByte (index_offset+0x13) != 0;
        entry.Size          = file.View.ReadUInt32 (index_offset+0x14);
        entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0x18);
        entry.Offset        = file.View.ReadUInt32 (index_offset+0x1C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x20;
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
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var output = new byte[pent.UnpackedSize];
        LzUnpack (input, output);
        return new BinMemoryStream (output, entry.Name);
    }
}
```

#### LzUnpack

```csharp
void LzUnpack (IBinaryStream input, byte[] output) {
    int dst = 0;
    int bits = 0;
    byte mask = 0;
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
        if ((mask & bits) != 0)
        {
            int offset = input.ReadUInt16();
            int count = (offset >> 12) + 1;
            offset &= 0xFFF;
            Binary.CopyOverlapped (output, dst-offset, dst, count);
            dst += count;
        }
        else
        {
            output[dst++] = input.ReadUInt8();
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Sogna/ArcSGS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
