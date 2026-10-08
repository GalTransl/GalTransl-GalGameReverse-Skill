# Peach / ArcNIJI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/NIJI` / `GameRes.Formats.Peach.NijiDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NijiDatOpener.TryOpen` | `uint index_end = file.View.ReadUInt32 (0xC);` |
| `NijiDatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0xC);` |
| `NijiDatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset + 0xC);` |
| `NijiDatOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset + 0x10);` |
| `NijiDatOpener.OpenEntry` | `uint unpacked_size = input.ReadUInt32();` |
| `NijiDatOpener.OpenEntry` | `uint t = input.ReadUInt32();` |
| `NijiDatOpener.OpenEntry` | `var bits = arc.File.View.ReadBytes (entry.Offset + bits_offset, entry.Size - bits_offset);` |
| `NijiDatOpener.LzUnpack` | `ctl = input.ReadUInt16() \| 0xFFFF0000;` |
| `NijiDatOpener.LzUnpack` | `ushort v = input.ReadUInt16();` |
| `NijiDatOpener.LzUnpack` | `offset = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Peach.NijiDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    uint index_offset = 0;
    uint index_end = file.View.ReadUInt32 (0xC);
    var dir = new List<Entry> ();
    while (index_offset < index_end)
    {
        var name = file.View.ReadString (index_offset, 0xC);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset + 0xC);
        entry.Size = file.View.ReadUInt32 (index_offset + 0x10);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".ESB"))
            entry.Type = "image";
        else if (name.HasExtension (".EST"))
            entry.Type = "script";
        dir.Add (entry);
        index_offset += 0x14;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    uint unpacked_size = input.ReadUInt32();
    uint t = input.ReadUInt32();
    uint bits_offset = (t & 0xFFFFFF) + 4;
    byte flags = (byte)(t >> 24);
    if (flags == 0xFF)
        return input;
    var bits = arc.File.View.ReadBytes (entry.Offset + bits_offset, entry.Size - bits_offset);
    var output = new byte[unpacked_size];
    LzUnpack (input, output, bits, flags);
    return new BinMemoryStream (output);
}
```

#### LzUnpack

```csharp
void LzUnpack (IBinaryStream input, byte[] output, byte[] bits, byte flags) {
    int dst = 0;
    int bitsrc = 0;
    byte shift = (byte)(flags & 0xF);
    uint ctl = 0xFFFF;
    uint mask = (1u << shift) - 1u;
    uint mask2 = ((flags & 0x80) == 0) ? 0xFFFFFFFF : mask;

    while (dst < output.Length)
    {
        if (ctl == 0xFFFF)
            ctl = input.ReadUInt16() | 0xFFFF0000;
        if ((ctl & 1) == 0)
        {
            ushort v = input.ReadUInt16();
            int count = (int)(v & mask);
            int offset = (int)(v >> shift);
            if (shift == 0 && count == 0 || shift != 0 && offset == 0)
                offset = input.ReadUInt16();
            if (count == mask2)
                count += bits[bitsrc++];
            count += 3;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
        else
        {
            output[dst++] = bits[bitsrc++];
        }
        ctl >>= 1;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Peach/ArcNIJI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
