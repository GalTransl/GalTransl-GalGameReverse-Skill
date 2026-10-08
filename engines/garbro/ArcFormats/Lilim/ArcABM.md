# Lilim / ArcABM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ABM` / `GameRes.Formats.Lilim.AbmOpener` | `abm` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AbmOpener.TryOpen` | `if ('B' != file.View.ReadByte (0) \|\| 'M' != file.View.ReadByte (1))` |
| `AbmOpener.TryOpen` | `int count = file.View.ReadInt16 (0x3A);` |
| `AbmOpener.TryOpen` | `uint width = file.View.ReadUInt32 (0x12);` |
| `AbmOpener.TryOpen` | `uint height = file.View.ReadUInt32 (0x16);` |
| `AbmOpener.TryOpen` | `long next_offset = file.View.ReadUInt32 (0x42);` |
| `AbmOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (current_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lilim.AbmArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly AbmImageData FrameInfo ;
```

#### AbmArchive

```csharp
public AbmArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, AbmImageData info)
    : base (arc, impl, dir) {
    FrameInfo = info;
}
```

### GameRes.Formats.Lilim.AbmImageData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int      Mode ;

public uint     BaseOffset ;

public uint     FrameOffset ;
```

#### Clone

```csharp
public AbmImageData Clone () {
    return this.MemberwiseClone() as AbmImageData;
}
```

### GameRes.Formats.Lilim.AbmEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int Index ;
```

### GameRes.Formats.Lilim.AbmOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if ('B' != file.View.ReadByte (0) || 'M' != file.View.ReadByte (1))
        return null;
    int type = file.View.ReadSByte (0x1C);
    if (type != 1 && type != 2)
        return null;

    int count = file.View.ReadInt16 (0x3A);
    if (!IsSaneCount (count))
        return null;

    uint width = file.View.ReadUInt32 (0x12);
    uint height = file.View.ReadUInt32 (0x16);
    int pixel_size = 2 == type ? 4 : 3;
    uint bitmap_data_size = width*height*(uint)pixel_size;

    var dir = new List<Entry> (count);
    long next_offset = file.View.ReadUInt32 (0x42);
    uint current_offset = 0x46;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    for (int i = 0; i < count; ++i)
    {
        var entry = new AbmEntry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Type = "image",
            Offset = next_offset,
            Index = i,
        };
        if (i + 1 != count)
        {
            next_offset = file.View.ReadUInt32 (current_offset);
            current_offset += 4;
        }
        else
            next_offset = file.MaxOffset;
        if (next_offset <= entry.Offset)
            return null;
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.UnpackedSize = 0x12 + bitmap_data_size;
        dir.Add (entry);
    }
    var image_info = new AbmImageData
    {
        Width = (uint)width,
        Height = (uint)height,
        BPP = pixel_size * 8,
        Mode = type,
        BaseOffset = (uint)dir[0].Offset,
    };
    return new AbmArchive (file, this, dir, image_info);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Lilim/ArcABM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
