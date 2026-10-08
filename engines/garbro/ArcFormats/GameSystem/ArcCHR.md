# GameSystem / ArcCHR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CHR/GAMESYSTEM` / `GameRes.Formats.GameSystem.ChrOpener` | `chr` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ChrOpener.TryOpen` | `\|\| file.View.ReadUInt32 (0) != file.MaxOffset)` |
| `ChrOpener.TryOpen` | `uint overlay_size = input.ReadUInt32();` |
| `ChrOpener.TryOpen` | `input.ReadInt32();` |
| `ChrOpener.TryOpen` | `int count = input.ReadInt32();` |
| `ChrOpener.TryOpen` | `int x = input.ReadInt16();` |
| `ChrOpener.TryOpen` | `int y = input.ReadInt16();` |
| `ChrOpener.TryOpen` | `int w = input.ReadInt16();` |
| `ChrOpener.TryOpen` | `int h = input.ReadInt16() * count;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.GameSystem.ChrOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Lazy<ImageFormat> s_ChrFormat = new Lazy<ImageFormat> (() => ImageFormat.FindByTag ("CHR")) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".CHR")
        || file.View.ReadUInt32 (0) != file.MaxOffset)
        return null;
    using (var input = file.CreateStream())
    {
        var info = s_ChrFormat.Value.ReadMetaData (input) as ChrMetaData;
        if (null == info)
            return null;
        input.Position = info.RgbSize;
        uint overlay_size = input.ReadUInt32();
        if (0 == overlay_size)
            return null;
        input.ReadInt32();
        int count = input.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        int x = input.ReadInt16();
        int y = input.ReadInt16();
        int w = input.ReadInt16();
        int h = input.ReadInt16() * count;
        var frame_info = new ImageMetaData
        {
            Width = (uint)w, Height = (uint)h, OffsetX = x, OffsetY = y, BPP = 32
        };

        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        var dir = new List<Entry> (2);
        var entry = new ChrEntry
        {
            Name = string.Format ("{0}#00", base_name),
            Offset = 0,
            Size = (uint)info.RgbSize,
            Info = info,
        };
        dir.Add (entry);
        entry = new ChrEntry
        {
            Name = string.Format ("{0}#01", base_name),
            Offset = info.RgbSize+4,
            Size = overlay_size,
            Info = frame_info,
        };
        dir.Add (entry);
        return new ArcFile (file, this, dir);
    }
}
```

### GameRes.Formats.GameSystem.ChrEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public override string Type { get { return "image"; } }

public ImageMetaData    Info ;
```

## 配套算法与外部条件

- [ArcFormats/GameSystem/ImageCHR.cs](ImageCHR.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/GameSystem/ArcCHR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
