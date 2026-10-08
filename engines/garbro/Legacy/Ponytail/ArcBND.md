# Ponytail / ArcBND：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BND/NMI` / `GameRes.Formats.Ponytail.BndOpener` | `bnd` | `42696e64` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BndOpener.TryOpen` | `if (!file.View.AsciiEqual (4, " ver.0"))` |
| `BndOpener.TryOpen` | `int count = file.View.ReadInt16 (0xD);` |
| `BndOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xF);` |
| `BndOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 8).Trim();` |
| `BndOpener.TryOpen` | `var ext  = file.View.ReadString (index_offset+8, 3);` |
| `BndOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x0C);` |
| `BndOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x14);` |
| `BndOpener.TryOpen` | `if (file.View.AsciiEqual (entry.Offset, "lz1_"))` |
| `BndOpener.TryOpen` | `char last_chr =(char)file.View.ReadByte (entry.Offset+4);` |
| `BndOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+5);` |
| `BndOpener.Lz1Unpack` | `ctl = input.ReadUInt8();` |
| `BndOpener.Lz1Unpack` | `output[dst++] = input.ReadUInt8();` |
| `BndOpener.Lz1Unpack` | `int code = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ponytail.BndOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, " ver.0"))
        return null;
    int count = file.View.ReadInt16 (0xD);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (0xF);
    if (index_offset >= file.MaxOffset)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 8).Trim();
        var ext  = file.View.ReadString (index_offset+8, 3);
        name = name + '.' + ext;
        var entry = Create<PackedEntry> (name);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x0C);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    foreach (PackedEntry entry in dir.Where (e => e.Name.EndsWith ("Z") && e.Type != "image"))
    {
        if (file.View.AsciiEqual (entry.Offset, "lz1_"))
        {
            entry.IsPacked = true;
            char last_chr =(char)file.View.ReadByte (entry.Offset+4);
            entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+5);
            string name = entry.Name.Remove (entry.Name.Length-1);
            entry.Name = name + char.ToUpperInvariant (last_chr);
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    if (!pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var output = new byte[pent.UnpackedSize];
    using (var input = arc.File.CreateStream (pent.Offset+9, pent.Size-9))
        Lz1Unpack (input, output);
    return new BinMemoryStream (output, pent.Name);
}
```

#### Lz1Unpack

```csharp
internal static void Lz1Unpack (IBinaryStream input, byte[] output) {
    byte mask = 0;
    int ctl = 0;
    int dst = 0;
    while (dst < output.Length)
    {
        mask <<= 1;
        if (0 == mask)
        {
            ctl = input.ReadUInt8();
            if (ctl < 0)
                break;
            mask = 1;
        }
        if ((ctl & mask) != 0)
        {
            output[dst++] = input.ReadUInt8();
        }
        else
        {
            int code = input.ReadUInt16();
            int offset = (code >> 5) + 1;
            int count = Math.Min (3 + (code & 0x1F), output.Length - dst);
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Ponytail/ArcBND.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
