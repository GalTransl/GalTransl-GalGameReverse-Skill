# Aoi / ArcVFS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `VFS/AOI` / `GameRes.Formats.Aoi.VfsOpener` | `vfs` | `56460101`, `56460002`, `56460001` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VfsOpener.TryOpen` | `int signature = file.View.ReadInt16 (0);` |
| `VfsOpener.TryOpen` | `int version = file.View.ReadInt16 (2);` |
| `VfsOpener.TryOpen` | `int count = file.View.ReadInt16 (4);` |
| `VfsOpener.TryOpen` | `int entry_size = file.View.ReadInt16 (6);` |
| `VfsOpener.TryOpen` | `int index_size = file.View.ReadInt32 (8);` |
| `VfsOpener.TryOpen` | `if (entry_size <= 0 \|\| index_size <= 0 \|\| file.MaxOffset != file.View.ReadUInt32 (0xC))` |
| `VfsOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x13);` |
| `VfsOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x13);` |
| `VfsOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x17);` |
| `VfsOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x1B);` |
| `VfsOpener.TryOpen` | `entry.IsPacked     = 0 != file.View.ReadByte (index_offset+0x1F);` |
| `VfsOpener.OpenV2` | `int filenames_length = file.View.ReadInt32 (filenames_offset);` |
| `VfsOpener.OpenV2` | `int name_offset = file.View.ReadInt32 (index_offset);` |
| `VfsOpener.OpenV2` | `entry.Offset = file.View.ReadUInt32 (index_offset+0xA);` |
| `VfsOpener.OpenV2` | `entry.Size   = file.View.ReadUInt32 (index_offset+0xE);` |
| `VfsOpener.OpenV2` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x12);` |
| `VfsOpener.OpenV2` | `entry.IsPacked     = 0 != file.View.ReadByte (index_offset+0x16);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aoi.VfsOpener

继承/接口：`ArchiveFormat`。

#### VfsOpener

```csharp
public VfsOpener () {
    Extensions = new string[] { "vfs" };
    Signatures = new uint[] { 0x01014656, 0x02004656, 0x01004656, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int signature = file.View.ReadInt16 (0);
    if (0x4656 != signature && 0x4C56 != signature)
        return null;
    int version = file.View.ReadInt16 (2);
    int count = file.View.ReadInt16 (4);
    if (!IsSaneCount (count))
        return null;
    int entry_size = file.View.ReadInt16 (6);
    int index_size = file.View.ReadInt32 (8);
    if (entry_size <= 0 || index_size <= 0 || file.MaxOffset != file.View.ReadUInt32 (0xC))
        return null;
    if (version >= 0x0200)
        return OpenV2 (file, count, entry_size, index_size);

    int index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x13);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x13);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x17);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x1B);
        entry.IsPacked     = 0 != file.View.ReadByte (index_offset+0x1F);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenV2

```csharp
ArcFile OpenV2 (ArcView file, int count, int entry_size, int index_size) {
    int index_offset = 0x10;
    int filenames_offset = index_offset + entry_size * count;
    int filenames_length = file.View.ReadInt32 (filenames_offset);
    char[] filenames;
    using (var fn_stream = file.CreateStream (filenames_offset+8, (uint)filenames_length*2))
    using (var fn_reader = new BinaryReader (fn_stream, Encoding.Unicode))
        filenames = fn_reader.ReadChars (filenames_length);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_offset = file.View.ReadInt32 (index_offset);
        if (name_offset < 0 || name_offset >= filenames.Length)
            return null;
        var name = GetName (filenames, name_offset);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0xA);
        entry.Size   = file.View.ReadUInt32 (index_offset+0xE);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x12);
        entry.IsPacked     = 0 != file.View.ReadByte (index_offset+0x16);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### GetName

```csharp
static string GetName (char[] names, int begin) {
    int end = Array.IndexOf (names, '\0', begin);
    if (-1 == end)
        end = names.Length;
    return new string (names, begin, end-begin);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Aoi/ArcVFS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
