# Speed / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/REC` / `GameRes.Formats.Speed.ArcOpener` | `arc` | `ff000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `ArcOpener.TryOpen` | `uint rec_length = file.View.ReadUInt32 (0);` |
| `ArcOpener.TryOpen` | `int rec_count = file.View.ReadInt32 (4);` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (index_offset, rec_length);` |
| `ArcOpener.TryOpen` | `rec_length = file.View.ReadUInt32 (index_offset);` |
| `ArcOpener.TryOpen` | `rec_count = file.View.ReadInt32 (index_offset+4);` |
| `ArcOpener.TryOpen` | `if (rec_length != 4 \|\| count != file.View.ReadInt32 (index_offset+8))` |
| `ArcOpener.TryOpen` | `entry.Offset = data_offset + file.View.ReadUInt32 (index_offset);` |
| `ArcOpener.OpenEntry` | `uint size = arc.File.View.ReadUInt32 (entry.Offset-4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Speed.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint rec_length = file.View.ReadUInt32 (0);
    if (rec_length < 0x10 || rec_length > 0x200)
        return null;
    int rec_count = file.View.ReadInt32 (4);
    if (rec_count < count || rec_length * rec_count >= file.MaxOffset)
        return null;
    long index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, rec_length);
        var entry = Create<Entry> (name);
        dir.Add (entry);
        index_offset += rec_length;
    }
    index_offset = 0x10 + rec_length * (rec_count + 2);
    rec_length = file.View.ReadUInt32 (index_offset);
    rec_count = file.View.ReadInt32 (index_offset+4);
    if (rec_length != 4 || count != file.View.ReadInt32 (index_offset+8))
        return null;
    index_offset += 0x10;
    long data_offset = index_offset + rec_length * (rec_count + 2) + 4;
    foreach (var entry in dir)
    {
        entry.Offset = data_offset + file.View.ReadUInt32 (index_offset);
        if (entry.Type == "image")
            entry.Offset += 16;
        else
            entry.Offset += 4;
        if (entry.Offset > file.MaxOffset)
            return null;
        index_offset += rec_length;
    }
    for (int i = 1; i < count; ++i)
        dir[i-1].Size = (uint)(dir[i].Offset - 4 - dir[i-1].Offset);
    dir[count-1].Size = (uint)(file.MaxOffset - dir[count-1].Offset);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    uint size = arc.File.View.ReadUInt32 (entry.Offset-4);
    return arc.File.CreateStream (entry.Offset, size, entry.Name);
}
```

#### LzUnpack

```csharp
void LzUnpack (Stream input, byte[] output) {
    using (var bits = new MsbBitStream (input, true))
    {
        int dst = 0;
        while (dst < output.Length)
        {
            int ctl = bits.GetNextBit();
            if (-1 == ctl)
                break;
            if (0 == ctl)
            {
                output[dst++] = (byte)bits.GetBits (8);
            }
            else
            {
                int offset = bits.GetBits (8);
                int count = bits.GetBits (8);
                if (offset <= 0)
                    break;
                Binary.CopyOverlapped (output, dst - offset, dst, count);
                dst += count;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Speed/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
