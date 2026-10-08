# Majiro / ArcMajiro：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MAJIRO` / `GameRes.Formats.Majiro.ArcOpener` | `arc` | `4d616a69` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "roArcV"))` |
| `ArcOpener.TryOpen` | `int version = file.View.ReadByte (0xA) - '0';` |
| `ArcOpener.TryOpen` | `if (version < 1 \|\| version > 3 \|\| !file.View.AsciiEqual (0xB, ".000\0"))` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (16);` |
| `ArcOpener.TryOpen` | `uint names_offset = file.View.ReadUInt32 (20);` |
| `ArcOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (24);` |
| `ArcOpener.TryOpen` | `uint offset_next = file.View.ReadUInt32 (table_pos+hash_size);` |
| `ArcOpener.TryOpen` | `offset_next = file.View.ReadUInt32 (table_pos + entry_size + hash_size);` |
| `ArcOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (table_pos + hash_size + 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Majiro.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "roArcV"))
        return null;
    int version = file.View.ReadByte (0xA) - '0';
    if (version < 1 || version > 3 || !file.View.AsciiEqual (0xB, ".000\0"))
        return null;
    int count = file.View.ReadInt32 (16);
    uint names_offset = file.View.ReadUInt32 (20);
    uint data_offset = file.View.ReadUInt32 (24);
    if (data_offset <= names_offset || data_offset >= file.MaxOffset || !IsSaneCount (count))
        return null;
    int table_size = count + (1 == version ? 1 : 0);
    int entry_size = 4 * (version + 1);
    table_size *= entry_size;
    if (table_size + 0x1c != names_offset)
        return null;
    if (data_offset > file.View.Reserve (0, data_offset))
        return null;
    int names_size = (int)(data_offset - names_offset);
    var names = new byte[names_size];
    file.View.Read (names_offset, names, 0, (uint)names_size);
    int names_pos = 0;
    int table_pos = 0x1c;
    int hash_size = version < 3 ? 4 : 8;
    uint offset_next = file.View.ReadUInt32 (table_pos+hash_size);

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var zero = Array.IndexOf (names, (byte)0, names_pos, names_size);
        if (-1 == zero)
            break;
        int name_len = zero-names_pos;
        string name = Encodings.cp932.GetString (names, names_pos, name_len);
        names_size -= name_len+1;
        names_pos = zero+1;
        uint offset = offset_next;
        offset_next = file.View.ReadUInt32 (table_pos + entry_size + hash_size);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        if (1 == version)
            entry.Size = offset_next >= offset ? offset_next - offset : 0;
        else
            entry.Size = file.View.ReadUInt32 (table_pos + hash_size + 4);
        table_pos += entry_size;
        if (offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    if (!dir.Any())
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Majiro/ArcMajiro.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
