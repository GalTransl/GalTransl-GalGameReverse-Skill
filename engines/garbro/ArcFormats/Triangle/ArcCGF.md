# Triangle / ArcCGF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CGF` / `GameRes.Formats.Triangle.CgfOpener` | `cgf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CgfOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `CgfOpener.TryOpen` | `uint offset1 = file.View.ReadUInt32 (0x14);` |
| `CgfOpener.TryOpen` | `uint offset2 = file.View.ReadUInt32 (0x20);` |
| `CgfOpener.TryOpen` | `uint size = file.View.ReadUInt32 (index_offset + entry_size - 8);` |
| `CgfOpener.TryOpen` | `offset2 = file.View.ReadUInt32 (index_offset + (entry_size * 2) - 4);` |
| `CgfOpener.TryOpen` | `var name = file.View.ReadString (index_offset, entry_size-4);` |
| `CgfOpener.TryOpen` | `next_offset = i+1 == count ? (uint)file.MaxOffset : file.View.ReadUInt32 (index_offset+entry_size-4);` |
| `CgfOpener.OpenEntry` | `uint packed_size = arc.File.View.ReadUInt32 (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Triangle.CgfEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Flags ;
```

### GameRes.Formats.Triangle.CgfOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count) || file.MaxOffset >= ~0xC0000000)
        return null;
    uint offset1 = file.View.ReadUInt32 (0x14);
    uint offset2 = file.View.ReadUInt32 (0x20);
    uint entry_size, next_offset;
    if (4+(uint)count*0x14 == (offset1 & ~0xC0000000))
    {
        entry_size = 0x14;
        next_offset = offset1;
    }
    else if (4+(uint)count*0x20 == (offset2 & ~0xC0000000))
    {
        entry_size = 0x20;
        next_offset = offset2;
    }
    else
        return null;

    uint index_size = entry_size * (uint)count;
    if (index_size > file.View.Reserve (4, index_size))
        return null;

    uint index_offset = 4;
    uint size = file.View.ReadUInt32 (index_offset + entry_size - 8);
    offset2 = file.View.ReadUInt32 (index_offset + (entry_size * 2) - 4);
    if (size == (offset2 - next_offset))
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, entry_size-4);
        if (!IsValidEntryName (name))
            return null;
        uint flags = next_offset >> 30;
        Entry entry;
        if (1 == flags || name.HasExtension (".iaf"))
            entry = new Entry();
        else
            entry = new CgfEntry { Flags = flags };
        entry.Name = name;
        entry.Type = "image";
        entry.Offset = next_offset & ~0xC0000000;

        index_offset += entry_size;
        next_offset = i+1 == count ? (uint)file.MaxOffset : file.View.ReadUInt32 (index_offset+entry_size-4);
        if (next_offset < entry.Offset)
            return null;
        entry.Size = (next_offset & ~0xC0000000) - (uint)entry.Offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var cent = entry as CgfEntry;
    if (null == cent)
        return base.OpenEntry (arc, entry);
    var offset = entry.Offset;
    var header = new byte[12];
    if (2 == cent.Flags)
    {
        arc.File.View.Read (offset, header, 0, 8);
        offset += 0x10;
    }
    uint packed_size = arc.File.View.ReadUInt32 (offset);
    arc.File.View.Read (offset+4, header, 8, 4);
    var input = arc.File.CreateStream (offset+8, packed_size);
    return new PrefixStream (header, input);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Triangle/ArcCGF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
