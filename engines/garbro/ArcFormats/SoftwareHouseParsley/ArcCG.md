# SoftwareHouseParsley / ArcCG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/yanepack` / `GameRes.Formats.Parsley.CgOpener` | ``, `dat` | `79616e65` | `False` |
| `CG/PARSLEY/1` / `GameRes.Formats.Parsley.CgV1Opener` | `` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CgOpener.TryOpen` | `if (file.View.AsciiEqual (0, "yane"))` |
| `CgOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "pack"))` |
| `CgOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `CgOpener.TryOpen` | `int first_offset = file.View.ReadInt32 (0x2C);` |
| `CgOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x20);` |
| `CgOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x20);` |
| `CgOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x24);` |
| `CgV1Opener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `CgV1Opener.TryOpen` | `var name = index.ReadCString();` |
| `CgV1Opener.TryOpen` | `entry.Offset = index.ReadUInt32();` |
| `CgV1Opener.TryOpen` | `if (palette_entry != null && 1 == file.View.ReadByte (palette_entry.Offset+8))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Parsley.CgOpener

继承/接口：`ArchiveFormat`。

#### CgOpener

```csharp
public CgOpener () {
    Extensions = new string[] { "", "dat" };
    Signatures = new uint[] { 0, 0x656E6179 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.AsciiEqual (0, "yane"))
    {
        if (!file.View.AsciiEqual (4, "pack"))
            return null;
    }
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    int first_offset = file.View.ReadInt32 (0x2C);
    if (12 + count*0x28 != first_offset)
        return null;

    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x20);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x20);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x28;
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Parsley.CgV1Opener

继承/接口：`ArchiveFormat`。

#### CgV1Opener

```csharp
public CgV1Opener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    var arc_name = Path.GetFileName (file.Name);
    bool is_ucg = arc_name.StartsWith ("UCG", StringComparison.OrdinalIgnoreCase);
    bool is_cg = is_ucg || arc_name == "CG";

    using (var index = file.CreateStream())
    {
        index.Position = 4;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadCString();
            if (string.IsNullOrWhiteSpace (name) || name.Length > 0x100)
                return null;
            var entry = Create<PackedEntry> (name);
            entry.Offset = index.ReadUInt32();
            if (entry.Offset >= file.MaxOffset)
                return null;
            entry.IsPacked = is_ucg;
            dir.Add (entry);
        }
        long index_end = index.Position;
        for (int i = 0; i < count; ++i)
        {
            var entry = dir[i];
            if (entry.Offset < index_end)
                return null;
            long next_offset = i+1 < count ? dir[i+1].Offset : file.MaxOffset;
            entry.Size = (uint)(next_offset - entry.Offset);
            if (is_cg)
                entry.Type = "image";
        }
        if (is_cg && !is_ucg)
        {
            var palette_entry = dir.Find (e => e.Name.Equals ("Palette", StringComparison.OrdinalIgnoreCase));
            if (palette_entry != null && 1 == file.View.ReadByte (palette_entry.Offset+8))
            {
                var palette = ImageFormat.ReadPalette (file, palette_entry.Offset+9, 0x100, PaletteFormat.Rgb);
                return new CgArchive (file, this, dir, palette);
            }
        }
        return new ArcFile (file, this, dir);
    }
}
```

### GameRes.Formats.Parsley.CgArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly BitmapPalette DefaultPalette ;
```

#### CgArchive

```csharp
public CgArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, BitmapPalette palette)
    : base (arc, impl, dir) {
    DefaultPalette = palette;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/SoftwareHouseParsley/ArcCG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
