# FC01 / ArcMCA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MCA` / `GameRes.Formats.FC01.McaOpener` | `mca` | `4d434120` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `McaOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0x10);` |
| `McaOpener.TryOpen` | `int count = file.View.ReadInt32 (0x20);` |
| `McaOpener.TryOpen` | `int bpp = file.View.ReadInt32 (0x14);` |
| `McaOpener.TryOpen` | `long next_offset = file.View.ReadUInt32 (index_offset);` |
| `McaOpener.TryOpen` | `next_offset = i+1 == count ? file.MaxOffset : file.View.ReadUInt32 (index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FC01.McaArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte Key ;

public readonly int  BPP ;

public readonly BitmapPalette Palette ;
```

#### McaArchive

```csharp
public McaArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte key, int bpp = 24, BitmapPalette palette = null)
    : base (arc, impl, dir) {
    Key = key;
    BPP = bpp;
    Palette = palette;
}
```

### GameRes.Formats.FC01.McaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (0x10);
    int count = file.View.ReadInt32 (0x20);
    if (index_offset >= file.MaxOffset || !IsSaneCount (count))
        return null;

    int bpp = file.View.ReadInt32 (0x14);
    BitmapPalette palette = null;
    if (8 == bpp)
    {
        palette = ImageFormat.ReadPalette (file, index_offset);
        index_offset += 0x400;
    }
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    long next_offset = file.View.ReadUInt32 (index_offset);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (next_offset > file.MaxOffset || next_offset <= index_offset)
            return null;
        index_offset += 4;
        var entry = new Entry
        {
            Name    = string.Format ("{0}#{1:D4}", base_name, i),
            Offset  = next_offset,
            Type    = "image",
        };
        next_offset = i+1 == count ? file.MaxOffset : file.View.ReadUInt32 (index_offset);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (entry.Size > 0x20)
            dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    var options = Query<McgOptions> (arcStrings.MCAEncryptedNotice);
    return new McaArchive (file, this, dir, options.Key, bpp, palette);
}
```

## 配套算法与外部条件

- [ArcFormats/FC01/ImageMCG.cs](ImageMCG.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/FC01/ArcMCA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
