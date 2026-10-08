# DigitalWorks / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/PAC` / `GameRes.Formats.DigitalWorks.BinOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.ParseIndexTable` | `uint pac_size = exe_file.View.ReadUInt32 (pos);` |
| `BinOpener.ParseIndexTable` | `long offset = exe_file.View.ReadUInt32 (pos);` |
| `BinOpener.ParseIndexTable` | `uint size   = exe_file.View.ReadUInt32 (pos+4);` |
| `BinOpener.ParseIndexTable` | `ushort is_packed = exe_file.View.ReadUInt16 (pos+8);` |
| `BinOpener.ParseIndexTable` | `ushort id   = exe_file.View.ReadUInt16 (pos+10);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DigitalWorks.IndexEntry

#### 状态与常量

```csharp
public  uint    Offset ;

public  uint    Size ;

public  bool    IsPacked ;

public  ushort  Id ;
```

#### IndexEntry

```csharp
public IndexEntry (uint offset, uint size, bool is_packed, ushort id) {
    Offset = offset;
    Size = size;
    IsPacked = is_packed;
    Id = id;
}
```

### GameRes.Formats.DigitalWorks.BinScheme

#### 状态与常量

```csharp
public string   Extension ;

public long     Size ;

public IList<IndexEntry>    Index ;
```

### GameRes.Formats.DigitalWorks.BinOpener

继承/接口：`PacOpener`。

#### 状态与常量

```csharp
static readonly Dictionary<string, string> PacExtensionMap = new Dictionary<string, string> {
    { "ANM", "BIN" },
    { "MOV", "MPG" },
    { "STR", "OGG" },
    { "TAK", "BIN" },
    { "VCE", "OGG" },
    { "VIS", "TMX" },
    { "_SE", "OGG" },
}

PacScheme DefaultScheme = new PacScheme {
    KnownSchemes = new Dictionary<string, IDictionary<string, BinScheme>>()
}
```

#### BinOpener

```csharp
public BinOpener () {
    ContainedFormats = new[] { "TX", "OGG", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasAnyOfExtensions ("bin", "pac"))
        return null;
    var scheme = FindScheme (file);
    if (null == scheme)
        return null;
    var pac_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = scheme.Index.Select (e => new PackedEntry {
        Name = string.Format ("{0}{1:D5}.{2}", pac_name, e.Id, scheme.Extension),
        Offset = e.Offset,
        Size = e.Size,
    } as Entry).ToList();
    dir.ForEach (e => e.Type = FormatCatalog.Instance.GetTypeFromName (e.Name, ContainedFormats));
    return new ArcFile (file, this, dir);
}
```

#### FindScheme

```csharp
BinScheme FindScheme (ArcView bin_file) {
    var bin_name = Path.GetFileName (bin_file.Name).ToUpperInvariant();
    foreach (var game in KnownSchemes.Values)
    {
        BinScheme scheme;
        if (game.TryGetValue (bin_name, out scheme) && bin_file.MaxOffset == scheme.Size)
            return scheme;
    }
    if (bin_file.MaxOffset >= uint.MaxValue)
        return null;
    var bin_dir = VFS.GetDirectoryName (bin_file.Name);
    var game_dir = Directory.GetParent (bin_dir).FullName;
    var exe_files = VFS.GetFiles (VFS.CombinePath (game_dir, "*.exe"));
    if (!exe_files.Any())
        return null;
    var last_idx = new byte[12];
    LittleEndian.Pack ((uint)bin_file.MaxOffset, last_idx, 0);
    LittleEndian.Pack ((uint)bin_file.MaxOffset, last_idx, 4);
    foreach (var exe_entry in exe_files)
    {
        using (var exe_file = VFS.OpenView (exe_entry))
        {
            var exe = new ExeFile (exe_file);
            if (!exe.ContainsSection (".data"))
                continue;
            var data_section = exe.Sections[".data"];
            var idx_pos = exe.FindString (data_section, last_idx, 4);
            if (idx_pos > 0)
                return ParseIndexTable (exe_file, data_section, idx_pos, bin_name);
        }
    }
    return null;
}
```

#### ParseIndexTable

```csharp
BinScheme ParseIndexTable (ArcView exe_file, ExeFile.Section data, long pos, string bin_name) {
    uint pac_size = exe_file.View.ReadUInt32 (pos);
    long last_offset = pac_size;
    var dir = new List<IndexEntry>();
    for (pos -= 12; pos >= data.Offset && last_offset != 0; pos -= 12)
    {
        long offset = exe_file.View.ReadUInt32 (pos);
        uint size   = exe_file.View.ReadUInt32 (pos+4);
        ushort is_packed = exe_file.View.ReadUInt16 (pos+8);
        ushort id   = exe_file.View.ReadUInt16 (pos+10);
        if (0 == size || offset + size > last_offset || is_packed != 0 && is_packed != 1)
            return null;
        var entry = new IndexEntry ((uint)offset, size, is_packed != 0, id);
        dir.Add (entry);
        last_offset = offset;
    }
    bin_name = Path.GetFileNameWithoutExtension (bin_name).ToUpperInvariant();
    string ext;
    if (!PacExtensionMap.TryGetValue (bin_name, out ext))
        ext = "";
    return new BinScheme {
        Extension = ext,
        Size  = pac_size,
        Index = dir,
    };
}
```

## 配套算法与外部条件

- [ArcFormats/DigitalWorks/ArcPAC.cs](ArcPAC.md)：本页引用的随包算法资料。
- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DigitalWorks/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
