# Entis / ArcERI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ERI/MULTI` / `GameRes.Formats.Entis.EriOpener` | `eri` | `456e7469` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `EriOpener.TryOpen` | `if (!file.View.AsciiEqual (0x10, "Entis Rasterized Image")` |
| `EriOpener.TryOpen` | `&& !file.View.AsciiEqual (0x10, "Moving Entis Image"))` |
| `EriOpener.TryOpen` | `long section_size = file.View.ReadInt64 (current_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Entis.EriOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Lazy<ImageFormat> s_EriFormat = new Lazy<ImageFormat> (() => ImageFormat.FindByTag ("ERI")) ;
```

#### EriOpener

```csharp
public EriOpener () {
    Extensions = new string[] { "eri" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0x10, "Entis Rasterized Image")
        && !file.View.AsciiEqual (0x10, "Moving Entis Image"))
        return null;
    EriMetaData info;
    using (var eris = file.CreateStream())
        info = s_EriFormat.Value.ReadMetaData (eris) as EriMetaData;

    if (null == info || null == info.Header || !IsSaneCount (info.Header.FrameCount))
        return null;
    info.FileName = file.Name;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);

    int count = info.Header.FrameCount;
    long current_offset = info.StreamPos;
    var dir = new List<Entry> (count);
    var id = new AsciiString (8);
    Color[] palette = null;
    int i = 0;
    while (i < count && current_offset < file.MaxOffset)
    {
        if (file.View.Read (current_offset, id.Value, 0, 8) < 8)
            break;
        if ("Stream  " == id)
        {
            current_offset += 0x10;
            continue;
        }
        long section_size = file.View.ReadInt64 (current_offset+8);
        if (section_size < 0 || section_size > int.MaxValue)
            throw new FileSizeException();
        current_offset += 0x10;
        if (0 == section_size)
            continue;
        if ("Palette " == id)
        {
            using (var stream = file.CreateStream (current_offset, (uint)section_size))
                palette = EriFormat.ReadPalette (stream, (int)section_size);
        }
        else if ("ImageFrm" == id || "DiffeFrm" == id)
        {
            var entry = new EriEntry {
                Name    = string.Format ("{0}#{1:D4}", base_name, i++),
                Type    = "image",
                Offset  = current_offset,
                Size    = (uint)section_size,
                FrameIndex = dir.Count,
                IsDiff  = "DiffeFrm" == id,
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        current_offset += section_size;
    }
    if (0 == dir.Count)
        return null;
    return new EriMultiImage (file, this, dir, info, palette);
}
```

### GameRes.Formats.Entis.EriMultiImage

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly EriMetaData     Info ;

public readonly Color[]         Palette ;

public readonly PixelFormat     Format ;

byte[][]        Frames ;
```

#### EriMultiImage

```csharp
public EriMultiImage (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, EriMetaData info, Color[] palette)
    : base (arc, impl, dir) {
    Info = info;
    Palette = palette;
    Frames = new byte[dir.Count][];
    if (8 == Info.BPP)
    {
        if (null == Palette)
            Format = PixelFormats.Gray8;
        else
            Format = PixelFormats.Indexed8;
    }
    else if (32 == Info.BPP)
    {
        if (0 == (Info.FormatType & EriType.WithAlpha))
            Format = PixelFormats.Bgr32;
        else
            Format = PixelFormats.Bgra32;
    }
    else if (16 == Info.BPP)
        Format = PixelFormats.Bgr555;
    else
        Format = PixelFormats.Bgr24;
}
```

#### GetFrame

```csharp
public byte[] GetFrame (int index) {
    if (index >= Frames.Length)
        throw new ArgumentException ("index");
    if (null != Frames[index])
        return Frames[index];

    var entry = Dir.ElementAt (index) as EriEntry;
    byte[] prev_frame = null;
    if (index > 0 && entry.IsDiff)
    {
        prev_frame = GetFrame (index-1);
    }
    using (var stream = File.CreateStream (entry.Offset, entry.Size))
    {
        var reader = new EriReader (stream, Info, Palette, prev_frame);
        reader.DecodeImage();
        Frames[index] = reader.Data;
    }
    return Frames[index];
}
```

### GameRes.Formats.Entis.EriEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  FrameIndex ;

public bool IsDiff ;
```

## 配套算法与外部条件

- [ArcFormats/Entis/EriReader.cs](EriReader.md)：本页引用的随包算法资料。
- [ArcFormats/Entis/ImageERI.cs](ImageERI.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Entis/ArcERI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
