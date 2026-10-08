# Yuka / ArcYKC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `YKC` / `GameRes.Formats.Yuka.YkcOpener` | `ykc`, `dat` | `594b4330` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `YkcOpener.TryOpen` | `var version = file.View.ReadUInt32 (4);` |
| `YkcOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0x10);` |
| `YkcOpener.TryOpen` | `uint index_length = file.View.ReadUInt32 (0x14);` |
| `YkcOpener.TryOpen` | `entry.NameOffset = file.View.ReadUInt32 (index_offset);` |
| `YkcOpener.TryOpen` | `entry.NameLength = file.View.ReadUInt32 (index_offset+4);` |
| `YkcOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+8);` |
| `YkcOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0xC);` |
| `YkcOpener.TryOpen` | `entry.Name = file.View.ReadString (entry.NameOffset, entry.NameLength, encoding);` |
| `YkcOpener.OpenEntry` | `\|\| !arc.File.View.AsciiEqual (entry.Offset, "YKS001")` |
| `YkcOpener.OpenEntry` | `\|\| 1 != arc.File.View.ReadUInt16 (entry.Offset+6))` |
| `YkcOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `YkcOpener.OpenEntry` | `uint text_offset = LittleEndian.ToUInt32 (data, 0x20);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Yuka.YukaEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint NameOffset ;

public uint NameLength ;
```

### GameRes.Formats.Yuka.YkcOpener

继承/接口：`ArchiveFormat`。

#### YkcOpener

```csharp
public YkcOpener () {
    Extensions = new string[] { "ykc", "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var version = file.View.ReadUInt32 (4);
    if (version != 0x3130 && version != 0x3230)
        return null;
    uint index_offset = file.View.ReadUInt32 (0x10);
    uint index_length = file.View.ReadUInt32 (0x14);
    int count = (int)(index_length / 0x14);
    if (index_offset >= file.MaxOffset || !IsSaneCount (count))
        return null;
    if (index_length > file.View.Reserve (index_offset, index_length))
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new YukaEntry();
        entry.NameOffset = file.View.ReadUInt32 (index_offset);
        entry.NameLength = file.View.ReadUInt32 (index_offset+4);
        entry.Offset = file.View.ReadUInt32 (index_offset+8);
        entry.Size   = file.View.ReadUInt32 (index_offset+0xC);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x14;
    }
    Encoding encoding = 0x3130 == version ? Encodings.cp932 : Encoding.UTF8;

    foreach (YukaEntry entry in dir)
    {
        entry.Name = file.View.ReadString (entry.NameOffset, entry.NameLength, encoding);
        entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size < 0x24
        || !entry.Name.HasExtension (".yks")
        || !arc.File.View.AsciiEqual (entry.Offset, "YKS001")
        || 1 != arc.File.View.ReadUInt16 (entry.Offset+6))
        return base.OpenEntry (arc, entry);

    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    uint text_offset = LittleEndian.ToUInt32 (data, 0x20);
    for (uint i = text_offset; i < data.Length; ++i)
        data[i] ^= 0xAA;
    data[6] = 0;
    return new BinMemoryStream (data, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Yuka/ArcYKC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
