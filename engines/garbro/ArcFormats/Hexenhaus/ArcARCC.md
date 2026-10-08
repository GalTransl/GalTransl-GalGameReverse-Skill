# Hexenhaus / ArcARCC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARCC` / `GameRes.Formats.Hexenhaus.ArcOpener` | `arc` | `41524343` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (0x14);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "NAME"))` |
| `ArcOpener.TryOpen` | `var addr_offset = file.View.ReadInt64 (index_offset+4);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "NIDX"))` |
| `ArcOpener.TryOpen` | `nidx_offsets[i] = file.View.ReadUInt32 (index_offset+2);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "EIDX"))` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "CINF"))` |
| `ArcOpener.TryOpen` | `ushort name_length = file.View.ReadUInt16 (index_offset);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "ADDR"))` |
| `ArcOpener.TryOpen` | `dir[i].Offset = file.View.ReadInt64 (index_offset+2);` |
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (entry.Offset, "FILE"))` |
| `ArcOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (entry.Offset+0x18);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Hexenhaus.ArcOpener

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
    int count = file.View.ReadInt32 (0x14);
    if (!IsSaneCount (count))
        return null;
    long index_offset = 0x2A;
    if (!file.View.AsciiEqual (index_offset, "NAME"))
        return null;
    var addr_offset = file.View.ReadInt64 (index_offset+4);
    index_offset += 0xE;
    if (!file.View.AsciiEqual (index_offset, "NIDX"))
        return null;
    index_offset += 4;
    var nidx_offsets = new uint[count];
    for (int i = 0; i < count; ++i)
    {
        nidx_offsets[i] = file.View.ReadUInt32 (index_offset+2);
        index_offset += 8;
    }
    if (!file.View.AsciiEqual (index_offset, "EIDX"))
        return null;
    index_offset += 4 + 8 * count;
    if (!file.View.AsciiEqual (index_offset, "CINF"))
        return null;
    index_offset += 4;
    var name_buffer = new byte[0x40];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 6;
        ushort name_length = file.View.ReadUInt16 (index_offset);
        if (name_length > name_buffer.Length)
            name_buffer = new byte[name_length];
        file.View.Read (index_offset+4, name_buffer, 0, name_length);
        index_offset += 6 + name_length;
        var name = DecryptName (name_buffer, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        dir.Add (entry);
    }
    index_offset = addr_offset;
    if (!file.View.AsciiEqual (index_offset, "ADDR"))
        return null;
    index_offset += 4;
    for (int i = 0; i < count; ++i)
    {
        dir[i].Offset = file.View.ReadInt64 (index_offset+2);
        index_offset += 12;
    }
    foreach (var entry in dir)
    {
        if (!file.View.AsciiEqual (entry.Offset, "FILE"))
            continue;
        entry.Size = file.View.ReadUInt32 (entry.Offset+0x18);
        entry.Offset += 0x22;
    }
    dir = dir.Where (entry => entry.Size != 0).ToList();
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### DecryptName

```csharp
static string DecryptName (byte[] name, int length) {
    for (int i = 0; i < length; ++i)
        name[i] ^= 0x69;
    return Encodings.cp932.GetString (name, 0, length);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Hexenhaus/ArcARCC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
