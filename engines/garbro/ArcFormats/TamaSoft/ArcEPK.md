# TamaSoft / ArcEPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `EPK` / `GameRes.Formats.Tama.PakOpener` | `epk` | `45504b20` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "EPK "))` |
| `PakOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4) - 0x20;` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (0x18);` |
| `PakOpener.TryOpen` | `uint name_offset = file.View.ReadUInt32 (index_offset+8);` |
| `PakOpener.TryOpen` | `int name_length = file.View.ReadInt32 (name_offset);` |
| `PakOpener.TryOpen` | `entry.Offset = file.View.ReadInt64 (index_offset+0x10);` |
| `PakOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x18);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tama.EpkEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  ArcNumber ;
```

### GameRes.Formats.Tama.EpkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IReadOnlyList<ArcView>  Parts ;

bool _epk_disposed = false ;
```

#### EpkArchive

```csharp
public EpkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IReadOnlyList<ArcView> parts)
    : base (arc, impl, dir) {
    Parts = parts;
}
```

### GameRes.Formats.Tama.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "EPK "))
        return null;
    uint index_size = file.View.ReadUInt32 (4) - 0x20;
    int count = file.View.ReadInt32 (0x18);
    if (!IsSaneCount (count) || index_size >= file.MaxOffset)
        return null;
    uint index_offset = 0x20;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    var arc_list = new List<Entry>();
    var arc_dir = VFS.GetDirectoryName (file.Name);
    var arc_name = Path.GetFileNameWithoutExtension (file.Name);
    for (int i = 1; i < 10; ++i)
    {
        var part_name = string.Format ("{0}.e{1:D02}", arc_name, i);
        part_name = VFS.CombinePath (arc_dir, part_name);
        if (!VFS.FileExists (part_name))
            break;
        arc_list.Add (VFS.FindFile (part_name));
    }

    var name_buffer = new byte[0x40];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint name_offset = file.View.ReadUInt32 (index_offset+8);
        int name_length = file.View.ReadInt32 (name_offset);
        if (name_length <= 0 || name_length >= index_size)
            return null;
        if (name_length > name_buffer.Length)
            name_buffer = new byte[name_length];
        file.View.Read (name_offset+4, name_buffer, 0, (uint)name_length);
        for (int j = 0; j < name_length; ++j)
            name_buffer[j] ^= 0xFF;
        var name = Encodings.cp932.GetString (name_buffer, 0, name_length);

        var entry = FormatCatalog.Instance.Create<EpkEntry> (name);
        entry.Offset = file.View.ReadInt64 (index_offset+0x10);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x18);
        dir.Add (entry);
        index_offset += 0x28;
    }
    var arc_set = new List<ArcView> (arc_list.Count);
    try
    {
        long max_offset = file.MaxOffset;
        var bounds = new List<long> (arc_list.Count+1);
        bounds.Add (max_offset);
        foreach (var arc_entry in arc_list)
        {
            var arc_file = VFS.OpenView (arc_entry);
            arc_set.Add (arc_file);
            max_offset += arc_file.MaxOffset;
            bounds.Add (max_offset);
        }
        foreach (EpkEntry entry in dir)
        {
            if (!entry.CheckPlacement (max_offset))
                return null;
            entry.ArcNumber = bounds.FindIndex (x => x > entry.Offset);
            if (entry.ArcNumber > 0)
                entry.Offset -= bounds[entry.ArcNumber-1];
        }
        var arc = new EpkArchive (file, this, dir, arc_set);
        arc_set = null;
        return arc;
    }
    finally
    {
        if (arc_set != null)
        {
            foreach (var arc in arc_set)
                arc.Dispose();
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var earc = arc as EpkArchive;
    var eent = entry as EpkEntry;
    if (null == earc || null == eent)
        return base.OpenEntry (arc, entry);
    long entry_offset = entry.Offset;
    ArcView file = arc.File;
    if (eent.ArcNumber > 0)
        file = earc.Parts[eent.ArcNumber-1];
    if (entry_offset + entry.Size <= file.MaxOffset)
        return file.CreateStream (entry_offset, entry.Size);
    uint first_part_size = (uint)(file.MaxOffset - entry_offset);
    var begin = file.CreateStream (entry_offset, first_part_size);
    var end = earc.Parts[eent.ArcNumber].CreateStream (0, entry.Size - first_part_size);
    return new ConcatStream (begin, end);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/TamaSoft/ArcEPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
