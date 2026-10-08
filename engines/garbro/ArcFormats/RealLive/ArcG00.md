# RealLive / ArcG00：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `G00/v2` / `GameRes.Formats.RealLive.G00Opener` | `g00` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `G00Opener.TryOpen` | `if (file.View.ReadByte (0) != 2)` |
| `G00Opener.TryOpen` | `uint width  = file.View.ReadUInt16 (1);` |
| `G00Opener.TryOpen` | `uint height = file.View.ReadUInt16 (3);` |
| `G00Opener.TryOpen` | `int count = file.View.ReadInt16 (5);` |
| `G00Opener.TryOpen` | `X = file.View.ReadInt32 (index_offset),` |
| `G00Opener.TryOpen` | `Y = file.View.ReadInt32 (index_offset+4),` |
| `G00Opener.TryOpen` | `if (input.ReadInt32() != count)` |
| `G00Opener.TryOpen` | `dir[i].Offset = input.ReadUInt32();` |
| `G00Opener.TryOpen` | `dir[i].Size   = input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RealLive.G00Entry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public override string Type { get { return "image"; } }

public int  X ;

public int  Y ;
```

### GameRes.Formats.RealLive.G00Archive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public ImageMetaData    ImageInfo ;

public byte[]           Bitmap ;
```

#### G00Archive

```csharp
public G00Archive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ImageMetaData info, byte[] bitmap)
    : base (arc, impl, dir) {
    ImageInfo = info;
    Bitmap = bitmap;
}
```

### GameRes.Formats.RealLive.G00Opener

继承/接口：`ArchiveFormat`。

#### G00Opener

```csharp
public G00Opener () {
    Extensions = new string[] { "g00" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".g00"))
        return null;
    if (file.View.ReadByte (0) != 2)
        return null;
    uint width  = file.View.ReadUInt16 (1);
    uint height = file.View.ReadUInt16 (3);
    if (0 == width || width > 0x8000 || 0 == height || height > 0x8000)
        return null;
    int count = file.View.ReadInt16 (5);
    if (count <= 1 || count > 0x1000)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);

    uint index_offset = 9;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new G00Entry {
            Name = string.Format ("{0}#{1:D3}", base_name, i),
            X = file.View.ReadInt32 (index_offset),
            Y = file.View.ReadInt32 (index_offset+4),
        };
        dir.Add (entry);
        index_offset += 0x18;
    }
    byte[] bitmap;
    using (var input = file.CreateStream (index_offset))
        bitmap = G00Reader.LzDecompress (input, 2, 1);

    using (var input = new BinMemoryStream (bitmap))
    {
        if (input.ReadInt32() != count)
            return null;
        for (int i = 0; i < count; ++i)
        {
            dir[i].Offset = input.ReadUInt32();
            dir[i].Size   = input.ReadUInt32();
        }
    }
    dir = dir.Where (e => e.Size != 0).ToList();
    if (0 == dir.Count)
        return null;
    var info = new ImageMetaData { Width = width, Height = height, BPP = 32 };
    return new G00Archive (file, this, dir, info, bitmap);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var g00arc = (G00Archive)arc;
    return new BinMemoryStream (g00arc.Bitmap, (int)entry.Offset, (int)entry.Size);
}
```

## 配套算法与外部条件

- [ArcFormats/RealLive/ImageG00.cs](ImageG00.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/RealLive/ArcG00.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
