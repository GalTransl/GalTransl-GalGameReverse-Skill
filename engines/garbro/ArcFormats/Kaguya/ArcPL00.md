# Kaguya / ArcPL00：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PL00/KAGUYA` / `GameRes.Formats.Kaguya.PL00Opener` | `plt` | `504c3030` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PL00Opener.TryOpen` | `int frame_count = file.View.ReadUInt16(current_offset);` |
| `PL00Opener.TryOpen` | `OffsetX = file.View.ReadInt32(current_offset),` |
| `PL00Opener.TryOpen` | `OffsetY = file.View.ReadInt32(current_offset + 4),` |
| `PL00Opener.TryOpen` | `Width = file.View.ReadUInt32(current_offset + 8),` |
| `PL00Opener.TryOpen` | `Height = file.View.ReadUInt32(current_offset + 12),` |
| `PL00Opener.TryOpen` | `int channels = file.View.ReadInt32(38);` |
| `PL00Opener.TryOpen` | `int offsetx = file.View.ReadInt32(current_offset);` |
| `PL00Opener.TryOpen` | `int offsety = file.View.ReadInt32(current_offset + 4);` |
| `PL00Opener.TryOpen` | `uint width = file.View.ReadUInt32(current_offset + 8);` |
| `PL00Opener.TryOpen` | `uint height = file.View.ReadUInt32(current_offset + 12);` |
| `PL00Opener.TryOpen` | `channels = file.View.ReadInt32(current_offset + 16);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.PL00Entry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int FrameIndex ;

public ImageMetaData ImageInfo ;
```

### GameRes.Formats.Kaguya.PL00Opener

继承/接口：`ArchiveFormat`。

#### PL00Opener

```csharp
public PL00Opener() {
    Extensions = new string[] { "plt" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    uint current_offset = 4;
    int frame_count = file.View.ReadUInt16(current_offset);
    if (!IsSaneCount(frame_count))
        return null;
    current_offset += 2;
    string base_name = Path.GetFileNameWithoutExtension(file.Name);
    var dir = new List<Entry>(frame_count);
    var info = new ImageMetaData
    {
        OffsetX = file.View.ReadInt32(current_offset),
        OffsetY = file.View.ReadInt32(current_offset + 4),
        Width = file.View.ReadUInt32(current_offset + 8),
        Height = file.View.ReadUInt32(current_offset + 12),
    };
    int channels = file.View.ReadInt32(38);
    info.BPP = channels * 8;
    current_offset += 16;
    for (int i = 0; i < frame_count; ++i)
    {
        int offsetx = file.View.ReadInt32(current_offset);
        int offsety = file.View.ReadInt32(current_offset + 4);
        uint width = file.View.ReadUInt32(current_offset + 8);
        uint height = file.View.ReadUInt32(current_offset + 12);
        channels = file.View.ReadInt32(current_offset + 16);
        uint size = (uint)(width * height * channels);
        current_offset += 20;
        var entry = new PL00Entry
        {
            FrameIndex = i,
            Name = string.Format("{0}#{1:D2}", base_name, i),
            Type = "image",
            Offset = current_offset,
            Size = size,
            IsPacked = false,
            ImageInfo = new ImageMetaData
            {
                OffsetX = offsetx,
                OffsetY = offsety,
                Width = width,
                Height = height,
                BPP = channels * 8,
            }
        };
        dir.Add(entry);
        current_offset += size;
    }
    return new PL00Archive(file, this, dir, info);
}
```

### GameRes.Formats.Kaguya.PL00Archive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly ImageMetaData ImageInfo ;
```

#### PL00Archive

```csharp
public PL00Archive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ImageMetaData base_info)
    : base(arc, impl, dir) {
    ImageInfo = base_info;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcPL00.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
