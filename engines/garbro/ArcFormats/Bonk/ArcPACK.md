# Bonk / ArcPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/BONK` / `GameRes.Formats.Bonk.PackOpener` | `pack` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.OpenEntry` | `if (null == pent \|\| !pent.IsPacked && (entry.Size < 16 \|\| !arc.File.View.AsciiEqual (entry.Offset, "SLID")))` |
| `PackOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `PackOpener.OpenEntry` | `uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+8);` |
| `PackOpener.OpenEntry` | `int frame_size = arc.File.View.ReadUInt16 (entry.Offset+0xC);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Bonk.PackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
Lazy<Dictionary<string, ArchiveRecord>> FileListMap = new Lazy<Dictionary<string, ArchiveRecord>> (ReadFileList) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var index = LookupIndex (file);
    if (null == index)
        return null;

    var last_record = index.Last();
    if (last_record.Offset + last_record.Size > file.MaxOffset)
        return null;
    var dir = index.Select (e => e.ToEntry()).ToList();
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked && (entry.Size < 16 || !arc.File.View.AsciiEqual (entry.Offset, "SLID")))
        return base.OpenEntry (arc, entry);
    if (!pent.IsPacked)
    {
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);
    }
    uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+8);
    int frame_size = arc.File.View.ReadUInt16 (entry.Offset+0xC);
    var input = arc.File.CreateStream (entry.Offset+0x10, packed_size);
    var lzss = new LzssStream (input);
    lzss.Config.FrameSize = frame_size;
    lzss.Config.FrameInitPos = frame_size - 0x12;
    return lzss;
}
```

#### LookupIndex

```csharp
IEnumerable<IndexRecord> LookupIndex (ArcView file) {
    var arc_name = Path.GetFileName (file.Name).ToLower();
    if (!arc_name.StartsWith ("data_") || !arc_name.EndsWith (".pack"))
        return null;
    ArchiveRecord arc_record;
    if (!FileListMap.Value.TryGetValue (arc_name, out arc_record))
        return null;
    if (file.MaxOffset != arc_record.Size)
        return null;
    return arc_record.Index;
}
```

#### ReadFileList

```csharp
static Dictionary<string, ArchiveRecord> ReadFileList () {
    var file_map = new Dictionary<string, ArchiveRecord>();
    var comma = new char[] {','};
    List<IndexRecord> current_list = null;
    FormatCatalog.Instance.ReadFileList (name_list_parameter, line => {
        var parts = line.Split (comma);
        if (2 == parts.Length)
        {
            current_list = new List<IndexRecord>();
            file_map[parts[0]] = new ArchiveRecord {
                Size = long.Parse (parts[1], NumberStyles.HexNumber),
                Index = current_list,
            };
        }
        else if (3 == parts.Length)
        {
            current_list.Add (new IndexRecord {
                Name = parts[2],
                Offset = long.Parse (parts[0], NumberStyles.HexNumber),
                Size   = uint.Parse (parts[1], NumberStyles.HexNumber),
            });
        }
    });
    return file_map;
}
```

### GameRes.Formats.Bonk.ArchiveRecord

#### 状态与常量

```csharp
public long     Size ;

public IEnumerable<IndexRecord> Index ;
```

### GameRes.Formats.Bonk.IndexRecord

#### 状态与常量

```csharp
public string   Name ;

public long     Offset ;

public uint     Size ;
```

#### ToEntry

```csharp
public Entry ToEntry () {
    var entry = FormatCatalog.Instance.Create<PackedEntry> (Name);
    entry.Offset = Offset;
    entry.Size = Size;
    return entry;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Bonk/ArcPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
