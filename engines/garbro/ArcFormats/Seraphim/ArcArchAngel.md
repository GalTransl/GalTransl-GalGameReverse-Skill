# Seraphim / ArcArchAngel：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/ARCH` / `GameRes.Formats.ArchAngel.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int file_count = file.View.ReadInt16 (0);` |
| `DatOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_pos);` |
| `DatOpener.TryOpen` | `int index = file.View.ReadInt16 (index_pos+4);` |
| `DatOpener.TryOpen` | `uint size = file.View.ReadUInt32 (2 + i * 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ArchAngel.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly string[] DefaultSections = { "image", "script", "" }
```

#### DatOpener

```csharp
public DatOpener () {
    ContainedFormats = new[] { "CB" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset > uint.MaxValue
        || !VFS.IsPathEqualsToFileName (file.Name, "ARCHPAC.DAT"))
        return null;
    int file_count = file.View.ReadInt16 (0);
    if (!IsSaneCount (file_count))
        return null;
    long index_pos = 2 + 4 * file_count;
    var section_table = new SortedDictionary<int, uint>();
    uint min_offset = (uint)file.MaxOffset;
    while (index_pos + 6 <= min_offset)
    {
        uint offset = file.View.ReadUInt32 (index_pos);
        int index = file.View.ReadInt16 (index_pos+4);
        if (index < 0 || index > file_count || offset > file.MaxOffset)
            return null;
        if (offset < min_offset)
            min_offset = offset;
        section_table[index] = offset;
        index_pos += 6;
    }
    var dir = new List<Entry> (file_count);
    int section_num = 0;
    Func<string> get_type;
    if (section_table.Count == DefaultSections.Length)
        get_type = () => DefaultSections[section_num];
    else
        get_type = () => section_num > 0 ? "image" : "";
    foreach (var section in section_table)
    {
        int i = section.Key;
        uint base_offset = section.Value;
        do
        {
            uint size = file.View.ReadUInt32 (2 + i * 4);
            if (size > 0)
            {
                var entry = new PackedEntry
                {
                    Name = string.Format("{0}-{1:D6}", section_num, i),
                    Type = get_type(),
                    Offset = base_offset,
                    Size = size,
                };
                if (!entry.CheckPlacement(file.MaxOffset))
                    return null;
                if ("script" == entry.Type)
                    entry.IsPacked = true;
                dir.Add(entry);
                base_offset += size;
            }
            ++i;
        }
        while (i < file_count && !section_table.ContainsKey (i));
        ++section_num;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked || pent.Size <= 4)
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (0 == pent.UnpackedSize)
        pent.UnpackedSize = input.Signature;
    try
    {
        var data = Seraphim.ScnOpener.LzDecompress (input);
        return new BinMemoryStream (data, entry.Name);
    }
    catch
    {
        return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    finally
    {
        input.Dispose();
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Seraphim/ArcArchAngel.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
