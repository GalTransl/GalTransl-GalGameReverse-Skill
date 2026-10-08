# SplushWave / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/FLK` / `GameRes.Formats.SplushWave.DatOpener` | `dat` | `464c4b00` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint arc_size = file.View.ReadUInt32 (0x14);` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0x18);` |
| `DatOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `DatOpener.TryOpen` | `Size = file.View.ReadUInt32 (index_offset+4),` |
| `DatOpener.TryOpen` | `Flags = file.View.ReadByte (index_offset+0xF),` |
| `DatOpener.TryOpen` | `var type = file.View.ReadUInt32 (entry.Offset);` |
| `DatOpener.LzssUnpack` | `ctl = input.ReadByte() \| 0xFF00;` |
| `DatOpener.LzssUnpack` | `int next = input.ReadByte();` |
| `DatOpener.LzssUnpack` | `int lo = input.ReadByte();` |
| `DatOpener.LzssUnpack` | `int hi = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SplushWave.FlkEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte Flags ;
```

### GameRes.Formats.SplushWave.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<SwgFormat> s_swg = new ResourceInstance<SwgFormat> ("SWG") ;

internal static SwgFormat Swg { get => s_swg.Value; }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint arc_size = file.View.ReadUInt32 (0x14);
    if (arc_size != file.MaxOffset)
        return null;
    int count = file.View.ReadInt32 (0x18);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x20;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new FlkEntry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Offset = file.View.ReadUInt32 (index_offset),
            Size = file.View.ReadUInt32 (index_offset+4),
            Flags = file.View.ReadByte (index_offset+0xF),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x10;
    }
    foreach (var entry in dir)
    {
        var type = file.View.ReadUInt32 (entry.Offset);
        if (0x475753 == type || 0x475753 == (type >> 8))
            entry.Type = "image";
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var fent = (FlkEntry)entry;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if ((fent.Flags & 1) != 0)
    {
        using (input)
        {
            return LzssUnpack (input);
        }
    }
    return input;
}
```

#### LzssUnpack

```csharp
internal Stream LzssUnpack (IBinaryStream input) {
    var frame = new byte[0x400];
    var output = new byte[0x200000];
    int dst = 0;
    int frame_pos = 0x3BE;
    int ctl = 0;
    while (input.PeekByte() != -1)
    {
        ctl >>= 1;
        if (0 == (ctl & 0x100))
        {
            ctl = input.ReadByte() | 0xFF00;
        }
        if (0 == (ctl & 1))
        {
            int next = input.ReadByte();
            if (-1 == next)
                break;
            output[dst++] = frame[frame_pos++ & 0x3FF] = (byte)next;
        }
        else
        {
            int lo = input.ReadByte();
            int hi = input.ReadByte();
            if (lo == -1 || hi == -1)
                break;
            int offset = lo + ((hi & 0xC0) << 2);
            int count = (hi & 0x3F) + 3;
            while (count --> 0)
            {
                output[dst++] = frame[frame_pos++ & 0x3FF] = frame[offset++ & 0x3FF];
            }
        }
    }
    return new BinMemoryStream (output, 0, dst);
}
```

## 配套算法与外部条件

- [Legacy/SplushWave/ImageSWG.cs](ImageSWG.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/SplushWave/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
