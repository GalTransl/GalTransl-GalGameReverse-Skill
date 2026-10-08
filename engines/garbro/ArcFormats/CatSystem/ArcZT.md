# CatSystem / ArcZT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ZT/PACK` / `GameRes.Formats.CatSystem.ZtOpener` | `zt` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ZtOpener.TryOpen` | `if (0x110 > file.View.ReadUInt32 (8) \|\| 1 < file.View.ReadUInt32 (0xC))` |
| `ZtOpener.TryOpen` | `offset_next     = file.View.ReadUInt32 (offset);` |
| `ZtOpener.TryOpen` | `uint entry_size = file.View.ReadUInt32 (offset+8);` |
| `ZtOpener.TryOpen` | `uint attributes = file.View.ReadUInt32 (offset+0xC);` |
| `ZtOpener.TryOpen` | `string name     = file.View.ReadString (offset+0x10, 0x104);` |
| `ZtOpener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (offset+0x114);` |
| `ZtOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (offset+0x118);` |
| `ZtOpener.TryOpen` | `else if (0 != file.View.ReadUInt32 (offset+4))` |
| `ZtOpener.TryOpen` | `offset_next = file.View.ReadUInt32 (offset+4);` |
| `ZtOpener.TryOpen` | `if (0xC + file.View.ReadUInt32 (offset+8) > offset_next)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CatSystem.ZtOpener

继承/接口：`ArchiveFormat`。

#### ZtOpener

```csharp
public ZtOpener () {
    Extensions = new string[] { "zt" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset < 0x11C)
        return null;
    if (0x110 > file.View.ReadUInt32 (8) || 1 < file.View.ReadUInt32 (0xC))
        return null;
    var dir = new List<Entry> ();
    var subdirs = new Queue<ZtSubdirectory> ();
    const string sep = "\\";
    string parent_name = "";
    long offset = 0;
    uint offset_next;
    do
    {
        offset_next     = file.View.ReadUInt32 (offset);
        uint entry_size = file.View.ReadUInt32 (offset+8);
        if (0 != offset_next && 0xC + entry_size > offset_next)
            return null;
        uint attributes = file.View.ReadUInt32 (offset+0xC);
        string name     = file.View.ReadString (offset+0x10, 0x104);
        if (1 < attributes || 0 == name.Length)
            return null;

        if (0 == attributes)
        {
            var entry = FormatCatalog.Instance.Create<PackedEntry> (parent_name + name);
            uint packed_size = file.View.ReadUInt32 (offset+0x114);
            if (0x110 + packed_size != entry_size)
                return null;
            entry.Offset = offset + 0x11C;
            entry.Size = packed_size;
            entry.UnpackedSize = file.View.ReadUInt32 (offset+0x118);
            entry.IsPacked = true;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        else if (0 != file.View.ReadUInt32 (offset+4))
        {
            subdirs.Enqueue (new ZtSubdirectory { Name = parent_name + name + sep, Offset = offset });
        }

        if (0 == offset_next && 0 != subdirs.Count)
        {
            var subdir = subdirs.Dequeue ();
            parent_name = subdir.Name;
            offset      = subdir.Offset;
            offset_next = file.View.ReadUInt32 (offset+4);
            if (0xC + file.View.ReadUInt32 (offset+8) > offset_next)
                return null;
        }
        offset += offset_next;
    }
    while (0 != offset_next);

    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pentry = (PackedEntry)entry;
    if (0 == pentry.UnpackedSize)
        return Stream.Null;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

### GameRes.Formats.CatSystem.ZtOpener.ZtSubdirectory

#### 状态与常量

```csharp
public string Name ;

public long Offset ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/CatSystem/ArcZT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
