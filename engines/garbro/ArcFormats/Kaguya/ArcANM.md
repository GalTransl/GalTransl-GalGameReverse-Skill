# Kaguya / ArcANM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AN10/KAGUYA` / `GameRes.Formats.Kaguya.An10Opener` | `anm` | `414e3130` | `False` |
| `AN20/KAGUYA` / `GameRes.Formats.Kaguya.An20Opener` | `anm` | `414e3230` | `False` |
| `ANM/KAGUYA` / `GameRes.Formats.Kaguya.AnmOpener` | `anm` | `414e3030` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AnmOpener.GetFramesList` | `int frame_count = file.ReadInt16();` |
| `AnmOpener.GetFramesList` | `int count = file.ReadInt16();` |
| `AnmOpener.GetFramesList` | `uint width  = file.ReadUInt32();` |
| `AnmOpener.GetFramesList` | `uint height = file.ReadUInt32();` |
| `An10Opener.GetFramesList` | `int frame_count = file.ReadInt16();` |
| `An10Opener.GetFramesList` | `int count = file.ReadInt16();` |
| `An10Opener.GetFramesList` | `uint width  = file.ReadUInt32();` |
| `An10Opener.GetFramesList` | `uint height = file.ReadUInt32();` |
| `An10Opener.GetFramesList` | `uint channels = file.ReadUInt32();` |
| `An20Opener.GetFramesList` | `int count = file.ReadInt16();` |
| `An20Opener.GetFramesList` | `uint width  = file.ReadUInt32();` |
| `An20Opener.GetFramesList` | `uint height = file.ReadUInt32();` |
| `An20Opener.GetFramesList` | `uint depth  = file.ReadUInt32();` |
| `An20Opener.SkipFrameTable` | `int table_count = file.ReadInt16();` |
| `An20Opener.SkipFrameTable` | `switch (file.ReadByte())` |
| `An20Opener.SkipFrameTable` | `int count = file.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.AnmArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly ImageMetaData   ImageInfo ;
```

#### AnmArchive

```csharp
public AnmArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ImageMetaData base_info)
    : base (arc, impl, dir) {
    ImageInfo = base_info;
}
```

### GameRes.Formats.Kaguya.AnmEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public long ImageDataOffset ;

public uint ImageDataSize ;
```

### GameRes.Formats.Kaguya.AnmOpenerBase

继承/接口：`ArchiveFormat`, `IAnmReader`。

#### AnmOpenerBase

```csharp
public AnmOpenerBase () {
    Extensions = new string[] { "anm" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var input = file.CreateStream())
    {
        var dir = GetFramesList (input);
        if (null == dir)
            return null;
        var base_info = GetBaseInfo (input);
        string base_name = Path.GetFileNameWithoutExtension (file.Name);
        int i = 0;
        foreach (var entry in dir)
        {
            entry.Name = string.Format ("{0}#{1:D2}", base_name, i++);
            entry.Type = "image";
        }
        return new AnmArchive (file, this, dir, base_info);
    }
}
```

#### GetFramesList

```csharp
public abstract List<Entry> GetFramesList (IBinaryStream input) ;
```

### GameRes.Formats.Kaguya.AnmOpener

继承/接口：`AnmOpenerBase`。

#### GetFramesList

```csharp
public override List<Entry> GetFramesList (IBinaryStream file) {
    file.Position = 0x14;
    int frame_count = file.ReadInt16();
    file.Position = 0x18 + frame_count * 4;
    int count = file.ReadInt16();
    if (!IsSaneCount (count))
        return null;
    var current_offset = file.Position;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.Position = current_offset + 8;
        uint width  = file.ReadUInt32();
        uint height = file.ReadUInt32();
        uint image_size = 4*width*height;
        var entry = new AnmEntry
        {
            Offset = current_offset,
            Size = 0x10 + image_size,
            ImageDataOffset = current_offset + 0x10,
            ImageDataSize = image_size,
        };
        dir.Add (entry);
        current_offset += entry.Size;
    }
    return dir;
}
```

### GameRes.Formats.Kaguya.An10Opener

继承/接口：`AnmOpenerBase`, `IAnmReader`。

#### GetFramesList

```csharp
public override List<Entry> GetFramesList (IBinaryStream file) {
    file.Position = 0x14;
    int frame_count = file.ReadInt16();
    file.Position = 0x18 + frame_count * 4;
    int count = file.ReadInt16();
    if (!IsSaneCount (count))
        return null;
    var current_offset = file.Position;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.Position = current_offset + 8;
        uint width  = file.ReadUInt32();
        uint height = file.ReadUInt32();
        uint channels = file.ReadUInt32();
        uint image_size = channels*width*height;
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

### GameRes.Formats.Kaguya.An20Opener

继承/接口：`AnmOpenerBase`。

#### GetFramesList

```csharp
public override List<Entry> GetFramesList (IBinaryStream file) {
    if (!SkipFrameTable (file))
        return null;
    int count = file.ReadInt16();
    if (!IsSaneCount (count))
        return null;
    long current_offset = file.Position + 0x10;
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

#### SkipFrameTable

```csharp
bool SkipFrameTable (IBinaryStream file) {
    file.Position = 4;
    int table_count = file.ReadInt16();
    file.Position = 8;
    for (int i = 0; i < table_count; ++i)
    {
        switch (file.ReadByte())
        {
        case 0: break;
        case 1: file.Seek (8, SeekOrigin.Current); break;
        case 2:
        case 3:
        case 4:
        case 5: file.Seek (4, SeekOrigin.Current); break;
        default: return false;
        }
    }
    int count = file.ReadUInt16();
    file.Seek (count * 8, SeekOrigin.Current);
    return true;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcANM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
