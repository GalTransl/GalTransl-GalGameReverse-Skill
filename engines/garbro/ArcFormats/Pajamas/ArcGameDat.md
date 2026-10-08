# Pajamas / ArcGameDat：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GAMEDAT` / `GameRes.Formats.Pajamas.DatOpener` | `dat`, `pak` | `47414d45` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "GAMEDAT PAC"))` |
| `DatOpener.TryOpen` | `int version = file.View.ReadByte (0x0b);` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0x0c);` |
| `DatOpener.TryOpen` | `var name = file.View.ReadString (name_offset, (uint)name_length);` |
| `DatOpener.TryOpen` | `entry.Offset = base_offset + file.View.ReadUInt32 (index_offset);` |
| `DatOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+4);` |
| `DatOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Pajamas.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat", "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "GAMEDAT PAC"))
        return null;
    int version = file.View.ReadByte (0x0b);
    if ('K' == version)
        version = 1;
    else if ('2' == version)
        version = 2;
    else
        return null;
    int count = file.View.ReadInt32 (0x0c);
    if (count <= 0 || count > 0xfffff)
        return null;
    int name_length = 1 == version ? 16 : 32;

    int name_offset = 0x10;
    int index_offset = name_offset + name_length*count;
    int base_offset = index_offset + 8*count;
    if ((uint)base_offset > file.View.Reserve (0, (uint)base_offset))
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (name_offset, (uint)name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = base_offset + file.View.ReadUInt32 (index_offset);
        entry.Size = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        name_offset += name_length;
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!entry.Name.EndsWith ("textdata.bin", StringComparison.InvariantCultureIgnoreCase))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);

    if (0x95 == data[0] && 0x6B == data[1] && 0x3C == data[2]
        && 0x9D == data[3] && 0x63 == data[4])
    {
        byte key = 0xC5;
        for (int i = 0; i < data.Length; ++i)
        {
            data[i] ^= key;
            key += 0x5C;
        }
    }
    return new BinMemoryStream (data, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Pajamas/ArcGameDat.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
