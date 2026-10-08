# AnimeGameSystem / ArcANI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ANI` / `GameRes.Formats.Ags.AniOpener` | `ani` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AniOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0);` |
| `AniOpener.TryOpen` | `var offset = file.View.ReadUInt32 (index_offset);` |
| `AniOpener.TryOpen` | `byte frame_type = file.View.ReadByte (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ags.AniEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  FrameIndex ;

public int  FrameType ;

public int  KeyFrame ;
```

### GameRes.Formats.Ags.AniOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static Lazy<ImageFormat> s_Cg = new Lazy<ImageFormat> (() => ImageFormat.FindByTag ("CG")) ;

ImageFormat Cg { get { return s_Cg.Value; } }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".ani"))
        return null;
    uint first_offset = file.View.ReadUInt32 (0);
    if (first_offset < 4 || file.MaxOffset > int.MaxValue || first_offset >= file.MaxOffset || 0 != (first_offset & 3))
        return null;
    int frame_count = (int)(first_offset / 4);
    if (frame_count > 10000)
        return null;
    long index_offset = 4;

    var frame_table = new uint[frame_count];
    frame_table[0] = first_offset;
    for (int i = 1; i < frame_count; ++i)
    {
        var offset = file.View.ReadUInt32 (index_offset);
        index_offset += 4;
        if (offset < first_offset || offset >= file.MaxOffset)
            return null;
        frame_table[i] = offset;
    }

    var frame_map = new Dictionary<uint, byte>();
    foreach (var offset in frame_table)
    {
        if (!frame_map.ContainsKey (offset))
        {
            byte frame_type = file.View.ReadByte (offset);
            if (frame_type >= 0x20)
                return null;
            frame_map[offset] = frame_type;
        }
    }

    int last_key_frame = 0;
    var dir = new List<Entry>();
    for (int i = 0; i < frame_count; ++i)
    {
        var offset = frame_table[i];
        int frame_type = frame_map[offset];
        if (1 == frame_type)
            continue;
        frame_type &= 0xF;
        if (0 == frame_type || 0xA == frame_type)
            last_key_frame = dir.Count;
        var entry = new AniEntry
        {
            Name = i.ToString ("D4"),
            Type = "image",
            Offset = offset,
            FrameType = frame_type,
            KeyFrame = last_key_frame,
            FrameIndex = dir.Count,
        };
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;

    var ordered = dir.OrderBy (e => e.Offset).ToList();
    for (int i = 0; i < ordered.Count; ++i)
    {
        var entry = ordered[i] as AniEntry;
        long next_offset = file.MaxOffset;
        for (int j = i+1; j <= ordered.Count; ++j)
        {
            next_offset = j == ordered.Count ? file.MaxOffset : ordered[j].Offset;
            if (next_offset != entry.Offset)
                break;
        }
        entry.Size = (uint)(next_offset - entry.Offset);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AnimeGameSystem/ArcANI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
