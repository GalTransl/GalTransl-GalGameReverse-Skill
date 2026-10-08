# Favorite / ArcHZC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `HZC/MULTI` / `GameRes.Formats.FVP.HzcOpener` | `hzc` | `687a6331` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `HzcOpener.TryOpen` | `uint header_size = file.View.ReadUInt32 (8);` |
| `HzcOpener.TryOpen` | `if (file.View.AsciiEqual (0x2C, "TLG"))` |
| `HzcOpener.TryOpen` | `if (0x64 == file.View.ReadByte (0x2C))` |
| `HzcOpener.TryOpen` | `int count = file.View.ReadInt32 (0x20);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FVP.HzcArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly HzcMetaData ImageInfo ;
```

#### HzcArchive

```csharp
public HzcArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, HzcMetaData info)
    : base (arc, impl, dir) {
    ImageInfo = info;
}
```

### GameRes.Formats.FVP.HzcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Lazy<ImageFormat> Hzc = new Lazy<ImageFormat> (() => ImageFormat.FindByTag ("HZC")) ;
```

#### HzcOpener

```csharp
public HzcOpener () {
    Extensions = new string[] { "hzc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint header_size = file.View.ReadUInt32 (8);
    HzcMetaData image_info;
    using (var header = file.CreateStream (0, 0xC+header_size))
    {
        image_info = Hzc.Value.ReadMetaData (header) as HzcMetaData;
        if (null == image_info)
            return null;
    }

    if (file.View.AsciiEqual (0x2C, "TLG"))
        return null;

    if (0x64 == file.View.ReadByte (0x2C))
        return null;
    int count = file.View.ReadInt32 (0x20);
    if (0 == count)
        count = 1;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    int frame_size = image_info.UnpackedSize / count;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D3}", base_name, i),
            Type = "image",
            Offset = frame_size * i,
            Size = (uint)frame_size,
        };
        dir.Add (entry);
    }
    return new HzcArchive (file, this, dir, image_info);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var hzc = (HzcArchive)arc;
    using (var input = arc.File.CreateStream (0xC+hzc.ImageInfo.HeaderSize))
    using (var z = new ZLibStream (input, CompressionMode.Decompress))
    {
        uint frame_size = entry.Size;
        var pixels = new byte[frame_size];
        uint offset = 0;
        for (;;)
        {
            if (pixels.Length != z.Read (pixels, 0, pixels.Length))
                throw new EndOfStreamException();
            if (offset >= entry.Offset)
                break;
            offset += frame_size;
        }
        return new BinMemoryStream (pixels, entry.Name);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Favorite/ImageHZC.cs](ImageHZC.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Favorite/ArcHZC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
