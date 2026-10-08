# Logg / ArcARF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARF` / `GameRes.Formats.Logg.ArfOpener` | `arf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArfOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `ArfOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index);` |
| `ArfOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index+4);` |
| `ArfOpener.TryOpen` | `byte name_len = file.View.ReadByte (index+8);` |
| `ArfOpener.TryOpen` | `var name = file.View.ReadString (index+9, name_len);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Logg.ArfOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    uint index = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index);
        if (offset <= index || offset > file.MaxOffset)
            return null;
        uint size   = file.View.ReadUInt32 (index+4);
        byte name_len = file.View.ReadByte (index+8);
        var name = file.View.ReadString (index+9, name_len);
        var entry = Create<PackedEntry> (name);
        entry.Offset = offset;
        entry.UnpackedSize = size;
        dir.Add (entry);
        index += name_len + 9u;
        if (index > dir[0].Offset)
            return null;
    }
    long last_offset = file.MaxOffset;
    for (int i = count-1; i >= 0; --i)
    {
        var entry = dir[i] as PackedEntry;
        entry.Size = (uint)(last_offset - entry.Offset);
        last_offset = entry.Offset;
        if (string.IsNullOrEmpty (entry.Name))
            dir.RemoveAt (i);
        else
            entry.IsPacked = entry.Size != entry.UnpackedSize;
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
    var input = arc.File.CreateStream (pent.Offset, pent.Size);
    var output = new byte[pent.UnpackedSize];
    Decompress (input, output);
    return new BinMemoryStream (output, pent.Name);
}
```

#### Decompress

```csharp
void Decompress (IBinaryStream input, byte[] output) {
    using (var bits = new LsbBitStream (input.AsStream, true))
    {
        int dst = 0;
        while (dst < output.Length)
        {
            if (bits.GetNextBit() == 0)
            {
                output[dst++] = (byte)bits.GetBits (8);
            }
            else
            {
                int count;
                if (bits.GetNextBit() == 0)
                    count = 2;
                else if (bits.GetNextBit() == 0)
                    count = 3;
                else if (bits.GetNextBit() == 0)
                    count = 4;
                else if (bits.GetNextBit() == 0)
                    count = 5;
                else
                {
                    switch (bits.GetBits (2))
                    {
                    case 0: count = 6; break;
                    case 1: count = bits.GetBits (2) + 7; break;
                    case 2: count = bits.GetBits (4) + 11; break;
                    case 3: count = bits.GetBits (10) + 26; break;
                    default: throw new EndOfStreamException();
                    }
                }
                int offset;
                if (bits.GetNextBit() == 0)
                    offset = bits.GetBits (8);
                else if (bits.GetNextBit() == 0)
                    offset = bits.GetBits (10) + 0x100;
                else
                    offset = bits.GetBits (12) + 0x500;
                Binary.CopyOverlapped (output, dst - offset - 1, dst, count);
                dst += count;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../../ArcFormats/BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Logg/ArcARF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
