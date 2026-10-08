# Kaguya / ArcPLT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PLT/KAGUYA` / `GameRes.Formats.Kaguya.Pl00Opener` | `plt` | `504c3030` | `False` |
| `PL10` / `GameRes.Formats.Kaguya.Pl10Opener` | `plt` | `504c3130` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Pl00Opener.GetFramesList` | `int count = file.ReadInt16();` |
| `Pl00Opener.GetFramesList` | `uint width  = file.ReadUInt32();` |
| `Pl00Opener.GetFramesList` | `uint height = file.ReadUInt32();` |
| `Pl00Opener.GetFramesList` | `uint depth  = file.ReadUInt32();` |
| `Pl10Opener.GetFramesList` | `int count = file.ReadInt16();` |
| `Pl10Opener.GetFramesList` | `OffsetX = file.ReadInt32(),` |
| `Pl10Opener.GetFramesList` | `OffsetY = file.ReadInt32(),` |
| `Pl10Opener.GetFramesList` | `Width  = file.ReadUInt32(),` |
| `Pl10Opener.GetFramesList` | `Height = file.ReadUInt32(),` |
| `Pl10Opener.GetFramesList` | `BPP    = file.ReadInt32() * 8,` |
| `Pl10Opener.GetFramesList` | `byte rle_step = file.ReadUInt8();` |
| `Pl10Opener.GetFramesList` | `uint packed_size = file.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.Pl00Opener

继承/接口：`AnmOpenerBase`。

#### Pl00Opener

```csharp
public Pl00Opener () {
    Extensions = new string[] { "plt" };
}
```

#### GetFramesList

```csharp
public override List<Entry> GetFramesList (IBinaryStream file) {
    file.Position = 4;
    int count = file.ReadInt16();
    if (!IsSaneCount (count))
        return null;
    file.Position = 0x16;
    var current_offset = file.Position;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.Position = current_offset + 8;
        uint width  = file.ReadUInt32();
        uint height = file.ReadUInt32();
        uint depth  = file.ReadUInt32();
        uint image_size = depth*width*height;
        var entry = new AnmEntry
        {
            Offset = current_offset,
            Size = 0x14 + image_size,
            ImageDataOffset = current_offset + 0x14,
            ImageDataSize = image_size,
        };
        dir.Add (entry);
        current_offset += entry.Size;
    }
    return dir;
}
```

### GameRes.Formats.Kaguya.Pl10Entry

继承/接口：`An21Entry`。

#### 状态与常量

```csharp
public ImageMetaData Info ;
```

### GameRes.Formats.Kaguya.Pl10Opener

继承/接口：`An21Opener`。

#### Pl10Opener

```csharp
public Pl10Opener () {
    Extensions = new string[] { "plt" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var input = file.CreateStream())
    {
        var base_info = GetBaseInfo (input);
        var dir = GetFramesList (input);
        if (null == dir)
            return null;
        string base_name = Path.GetFileNameWithoutExtension (file.Name);
        foreach (Pl10Entry entry in dir)
        {
            entry.Name = string.Format ("{0}#{1:D2}", base_name, entry.FrameIndex);
            entry.Type = "image";
        }
        var first = (Pl10Entry)dir[0];
        base_info.BPP = first.Info.BPP;
        return new An21Archive (file, this, dir, base_info);
    }
}
```

#### GetFramesList

```csharp
internal List<Entry> GetFramesList (IBinaryStream file) {
    file.Position = 4;
    int count = file.ReadInt16();
    if (!IsSaneCount (count))
        return null;
    var dir = new List<Entry> (count);
    long current_offset = 0x16;
    file.Position = current_offset;
    var frame_info = new ImageMetaData {
        OffsetX = file.ReadInt32(),
        OffsetY = file.ReadInt32(),
        Width  = file.ReadUInt32(),
        Height = file.ReadUInt32(),
        BPP    = file.ReadInt32() * 8,
    };
    uint depth = (uint)frame_info.BPP / 8;
    uint image_size = depth * frame_info.Width * frame_info.Height;
    var entry = new Pl10Entry
    {
        Offset = current_offset + 0x14,
        Size = image_size,
        FrameIndex = 0,
        RleStep = 0,
        Info = frame_info,
    };
    dir.Add (entry);
    for (int i = 1; i < count; ++i)
    {
        current_offset = entry.Offset + entry.Size;
        file.Position = current_offset;
        byte rle_step = file.ReadUInt8();
        uint packed_size = file.ReadUInt32();
        entry = new Pl10Entry
        {
            Offset = current_offset + 5,
            Size = packed_size,
            UnpackedSize = image_size,
            IsPacked = true,
            FrameIndex = i,
            RleStep = rle_step,
            Info = frame_info,
        };
        dir.Add (entry);
    }
    return dir;
}
```

## 配套算法与外部条件

- [ArcFormats/Kaguya/ArcAN21.cs](ArcAN21.md)：本页引用的随包算法资料。
- [ArcFormats/Kaguya/ArcANM.cs](ArcANM.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcPLT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
