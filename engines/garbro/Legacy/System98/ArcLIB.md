# System98 / ArcLIB：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LIB/SYSTEM98` / `GameRes.Formats.System98.LibOpener` | `lib` | `4c696230` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LibOpener.TryOpen` | `count = cat.View.ReadInt16 (4);` |
| `LibOpener.TryOpen` | `if (cat.View.AsciiEqual (0, "Cat0"))` |
| `LibOpener.TryOpen` | `index = file.View.ReadBytes (6, (uint)index_size);` |
| `LibOpener.TryOpen` | `else if (cat.View.AsciiEqual (0, "Cat1"))` |
| `LibOpener.TryOpen` | `entry.Size   = index.ToUInt32 (pos+0xE);` |
| `LibOpener.TryOpen` | `entry.Offset = index.ToUInt32 (pos+0x12);` |
| `LibOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+6);` |
| `LibOpener.LzssUnpack` | `ctl = input.ReadByte();` |
| `LibOpener.LzssUnpack` | `output[dst++] = frame[frame_pos++ & 0xFFF] = input.ReadUInt8();` |
| `LibOpener.LzssUnpack` | `int lo = input.ReadByte();` |
| `LibOpener.LzssUnpack` | `int hi = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.System98.LibOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var cat_name = Path.ChangeExtension (file.Name, ".CAT");
    if (!VFS.FileExists (cat_name))
        return null;
    int count;
    byte[] index;
    using (var cat = VFS.OpenView (cat_name))
    {
        count = cat.View.ReadInt16 (4);
        if (!IsSaneCount (count))
            return null;
        int index_size = count * 0x16;
        if (cat.View.AsciiEqual (0, "Cat0"))
        {
            index = file.View.ReadBytes (6, (uint)index_size);
        }
        else if (cat.View.AsciiEqual (0, "Cat1"))
        {
            index = new byte[index_size];
            using (var input = cat.CreateStream (6))
                LzssUnpack (input, index);
        }
        else
            return null;
    }
    int pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, pos, 0xC).TrimEnd();
        var entry = Create<PackedEntry> (name);
        entry.Size   = index.ToUInt32 (pos+0xE);
        entry.Offset = index.ToUInt32 (pos+0x12);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = index[pos+0xC] != 0;
        dir.Add (entry);
        pos += 0x16;
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
    if (pent.UnpackedSize == 0)
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+6);
    var data = new byte[pent.UnpackedSize];
    using (var input = arc.File.CreateStream (entry.Offset+10, entry.Size-10))
    {
        int length = LzssUnpack (input, data);
        return new BinMemoryStream (data, 0, length, entry.Name);
    }
}
```

#### LzssUnpack

```csharp
internal static int LzssUnpack (IBinaryStream input, byte[] output) {
    var frame = new byte[0x1000];
    int frame_pos = 1;
    int ctl = 0;
    byte mask = 0;
    int dst = 0;
    while (dst < output.Length)
    {
        mask <<= 1;
        if (0 == mask)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            mask = 1;
        }
        if (input.PeekByte() == -1)
            break;
        if ((ctl & mask) != 0)
        {
            output[dst++] = frame[frame_pos++ & 0xFFF] = input.ReadUInt8();
        }
        else
        {
            int lo = input.ReadByte();
            int hi = input.ReadByte();
            if (-1 == hi)
                break;
            int count = (lo & 0xF) + 3;
            int off = hi << 4 | lo >> 4;
            while (count --> 0)
            {
                byte b = frame[off++ & 0xFFF];
                output[dst++] = frame[frame_pos++ & 0xFFF] = b;
            }
        }
    }
    return dst;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/System98/ArcLIB.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
