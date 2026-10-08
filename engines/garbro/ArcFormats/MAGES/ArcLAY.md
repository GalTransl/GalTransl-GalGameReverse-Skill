# MAGES / ArcLAY：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LAY/MAGES` / `GameRes.Formats.MAGES.LayOpener` | `lay` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LayOpener.TryOpen` | `int tile_count = file.View.ReadInt32 (0);` |
| `LayOpener.TryOpen` | `int coord_count = file.View.ReadInt32 (4);` |
| `LayOpener.TryOpen` | `uint id = index.ReadUInt32();` |
| `LayOpener.TryOpen` | `int first = index.ReadInt32();` |
| `LayOpener.TryOpen` | `int count = index.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MAGES.LayEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Id ;

public int  First ;

public int  Count ;
```

### GameRes.Formats.MAGES.LayCoord

#### 状态与常量

```csharp
public float TargetX, TargetY ;

public float SourceX, SourceY ;
```

### GameRes.Formats.MAGES.LayArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IList<LayCoord>     Tiles ;

public readonly IDictionary<uint, LayEntry> LayerMap ;
```

#### GetTiles

```csharp
public IEnumerable<LayCoord> GetTiles (LayEntry layer) {
    return Tiles.Skip (layer.First).Take (layer.Count);
}
```

### GameRes.Formats.MAGES.LayOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const int DefaultWidth  = 1920 ;

const int DefaultHeight = 1080 ;

const int BlockSize     = 32 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".lay"))
        return null;
    int tile_count = file.View.ReadInt32 (0);
    int coord_count = file.View.ReadInt32 (4);
    if (!IsSaneCount (tile_count) || !IsSaneCount (coord_count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name).TrimEnd ('_');
    var png_name = VFS.ChangeFileName (file.Name, base_name + ".png");
    if (!VFS.FileExists (png_name))
        return null;
    ImageData image;
    var png_entry = VFS.FindFile (png_name);
    using (var decoder = VFS.OpenImage (png_entry))
        image = decoder.Image;
    using (var input = file.CreateStream())
    using (var index = new BinaryReader (input))
    {
        input.Position = 8;
        var dir = new List<Entry> (tile_count);
        for (int i = 0; i < tile_count; ++i)
        {
            uint id = index.ReadUInt32();
            int first = index.ReadInt32();
            int count = index.ReadInt32();
            var name = string.Format ("{0}#{1:X8}", base_name, id);
            var entry = new LayEntry {
                Name = name, Type = "image", Offset = 0,
                Id = id, First = first, Count = count
            };
            dir.Add (entry);
        }
        var tiles = new List<LayCoord> (coord_count);
        for (int i = 0; i < coord_count; ++i)
        {
            var tile = new LayCoord();
            tile.TargetX = index.ReadSingle() + 1;
            tile.TargetY = index.ReadSingle() + 1;
            tile.SourceX = index.ReadSingle() - 1;
            tile.SourceY = index.ReadSingle() - 1;
            tiles.Add (tile);
        }
        return new LayArchive (file, this, dir, image.Bitmap, tiles);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MAGES/ArcLAY.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
