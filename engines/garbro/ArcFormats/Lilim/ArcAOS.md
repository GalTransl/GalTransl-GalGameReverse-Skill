# Lilim / ArcAOS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AOSv2` / `GameRes.Formats.Lilim.Aos2Opener` | `aos` | 无固定签名或来源表达式未解析 | `False` |
| `AOS` / `GameRes.Formats.Lilim.AosOpener` | `aos` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AosOpener.TryOpen` | `if (0 == file.View.ReadByte (0))` |
| `AosOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0x10);` |
| `AosOpener.TryOpen` | `var name_buf = file.View.ReadBytes (first_offset, 0x10);` |
| `AosOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (current_offset+0x10);` |
| `AosOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (current_offset+0x10);` |
| `AosOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (current_offset+0x14);` |
| `AosOpener.OpenEntry` | `aent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |
| `Aos2Opener.TryOpen` | `if (0 != file.View.ReadInt32 (0))` |
| `Aos2Opener.TryOpen` | `long base_offset = file.View.ReadUInt32 (4);` |
| `Aos2Opener.TryOpen` | `int index_size = file.View.ReadInt32 (8);` |
| `Aos2Opener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x20);` |
| `Aos2Opener.TryOpen` | `entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x20);` |
| `Aos2Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x24);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lilim.AosOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] IndexLink = Enumerable.Repeat<byte> (0xff, 0x10).ToArray() ;

static readonly byte[] IndexEnd  = Enumerable.Repeat<byte> (0, 0x10).ToArray() ;
```

#### AosOpener

```csharp
public AosOpener () {
    ContainedFormats = new[] { "BMP", "ABM", "IMG/BMP", "DAT/GENERIC", "OGG" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0 == file.View.ReadByte (0))
        return null;
    uint first_offset = file.View.ReadUInt32 (0x10);
    if (first_offset >= file.MaxOffset || 0 != (first_offset & 0x1F))
        return null;
    var name_buf = file.View.ReadBytes (first_offset, 0x10);
    if (!name_buf.SequenceEqual (IndexLink) && !name_buf.SequenceEqual (IndexEnd))
        return null;

    string last_name = null;
    long current_offset = 0;
    var dir = new List<Entry> (0x3E);
    while (current_offset < file.MaxOffset)
    {
        if (0x10 != file.View.Read (current_offset, name_buf, 0, 0x10))
            break;
        if (name_buf.SequenceEqual (IndexLink))
        {
            uint next_offset = file.View.ReadUInt32 (current_offset+0x10);
            current_offset += 0x20 + next_offset;
        }
        else
        {
            int name_length = Array.IndexOf<byte> (name_buf, 0);
            if (0 == name_length)
                break;
            if (-1 == name_length)
                name_length = name_buf.Length;
            var name = Encodings.cp932.GetString (name_buf, 0, name_length);
            if (last_name == name || string.IsNullOrWhiteSpace (name))
                return null;
            last_name = name;
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = file.View.ReadUInt32 (current_offset+0x10);
            entry.Size   = file.View.ReadUInt32 (current_offset+0x14);
            current_offset += 0x20;
            entry.Offset += current_offset;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = name.HasExtension (".scr");
            dir.Add (entry);
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var aent = entry as PackedEntry;
    if (null == aent || !aent.IsPacked)
        return base.OpenEntry (arc, entry);

    aent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
    var packed = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
    var unpacked = new HuffmanStream (packed);
    return new LimitStream (unpacked, aent.UnpackedSize);
}
```

### GameRes.Formats.Lilim.Aos2Opener

继承/接口：`AosOpener`。

#### Aos2Opener

```csharp
public Aos2Opener () {
    Extensions = new string[] { "aos" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0 != file.View.ReadInt32 (0))
        return null;

    long base_offset = file.View.ReadUInt32 (4);
    uint index_offset = 0x111;
    int index_size = file.View.ReadInt32 (8);
    if (base_offset >= file.MaxOffset || index_offset+index_size >= file.MaxOffset
        || base_offset < index_offset+index_size)
        return null;
    int count = index_size / 0x28;
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x20);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x20);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".scr"))
            entry.IsPacked = true;
        else if (name.HasExtension (".cmp"))
        {
            entry.IsPacked = true;
            entry.Name = Path.ChangeExtension (entry.Name, ".abm");
            entry.Type = "image";
        }
        dir.Add (entry);
        index_offset += 0x28;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/HuffmanCompression.cs](../HuffmanCompression.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Lilim/ArcAOS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
