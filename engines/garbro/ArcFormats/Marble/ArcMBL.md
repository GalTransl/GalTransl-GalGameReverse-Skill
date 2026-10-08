# Marble / ArcMBL：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MBL/GRA` / `GameRes.Formats.Marble.GraMblOpener` | `mbl` | 无固定签名或来源表达式未解析 | `False` |
| `MBL` / `GameRes.Formats.Marble.MblOpener` | `mbl`, `dns` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MblOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `MblOpener.TryOpen` | `uint filename_len = file.View.ReadUInt32 (4);` |
| `MblOpener.ReadIndex` | `string name = file.View.ReadString (index_offset, filename_len);` |
| `MblOpener.ReadIndex` | `string ext = file.View.ReadString (index_offset+name.Length+1, filename_len-(uint)name.Length-1);` |
| `MblOpener.ReadIndex` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `MblOpener.ReadIndex` | `uint signature = file.View.ReadUInt32 (offset);` |
| `MblOpener.ReadIndex` | `entry.Size = file.View.ReadUInt32 (index_offset+4);` |
| `MblOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `GraMblOpener.TryOpen` | `uint filename_len = file.View.ReadUInt32 (0);` |
| `GraMblOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `GraMblOpener.TryOpen` | `string name = file.View.ReadString (index_offset, filename_len);` |
| `GraMblOpener.TryOpen` | `Offset  = file.View.ReadUInt32 (index_offset),` |
| `GraMblOpener.TryOpen` | `Size    = file.View.ReadUInt32 (index_offset+4),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Marble.MblOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public string PassPhrase ;
```

### GameRes.Formats.Marble.MblArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### MblArchive

```csharp
public MblArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, string password)
    : base (arc, impl, dir) {
    Key = Encodings.cp932.GetBytes (password);
}
```

### GameRes.Formats.Marble.MblOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<ImageFormat> PrsFormat = new ResourceInstance<ImageFormat> ("PRS") ;

static readonly ResourceInstance<ImageFormat> YpFormat  = new ResourceInstance<ImageFormat> ("PRS/YP") ;
```

#### MblOpener

```csharp
public MblOpener () {
    Extensions = new string[] { "mbl", "dns" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    ArcFile arc = null;
    uint filename_len = file.View.ReadUInt32 (4);
    if (filename_len > 0 && filename_len <= 0xff)
        arc = ReadIndex (file, count, filename_len, 8);
    if (null == arc)
        arc = ReadIndex (file, count, 0x10, 4);
    if (null == arc)
        arc = ReadIndex (file, count, 0x38, 4);
    return arc;
}
```

#### ReadIndex

```csharp
private ArcFile ReadIndex (ArcView file, int count, uint filename_len, uint index_offset) {
    uint index_size = (8u + filename_len) * (uint)count;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    try
    {
        bool contains_scripts = Path.GetFileNameWithoutExtension (file.Name).EndsWith ("_data", StringComparison.OrdinalIgnoreCase);
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            string name = file.View.ReadString (index_offset, filename_len);
            if (0 == name.Length)
                break;
            if (filename_len-name.Length > 1)
            {
                string ext = file.View.ReadString (index_offset+name.Length+1, filename_len-(uint)name.Length-1);
                if (0 != ext.Length)
                    name = Path.ChangeExtension (name, ext);
            }
            name = name.ToLowerInvariant();
            index_offset += (uint)filename_len;
            uint offset = file.View.ReadUInt32 (index_offset);
            string type = null;
            if (contains_scripts || name.EndsWith (".s"))
            {
                type = "script";
            }
            else if (4 == Path.GetExtension (name).Length)
            {
                type = FormatCatalog.Instance.GetTypeFromName (name);
            }
            Entry entry;
            if (string.IsNullOrEmpty (type))
            {
                entry = new AutoEntry (name, () => {
                    uint signature = file.View.ReadUInt32 (offset);
                    if (0x4259 == (0xFFFF & signature))
                        return PrsFormat.Value;
                    else if (0x5059 == (0xFFFF & signature))
                        return YpFormat.Value;
                    else if (0 != signature)
                        return FormatCatalog.Instance.LookupSignature (signature).FirstOrDefault();
                    else
                        return null;
                });
            }
            else
            {
                entry = new Entry { Name = name, Type = type };
            }
            entry.Offset = offset;
            entry.Size = file.View.ReadUInt32 (index_offset+4);
            if (offset < index_size || !entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += 8;
        }
        if (0 == dir.Count || (1 == dir.Count && count > 1))
            return null;
        contains_scripts = contains_scripts || dir.Any (e => e.Name.EndsWith (".s"));
        if (contains_scripts)
        {
            var password = QueryPassPhrase (file.Name);
            if (!string.IsNullOrEmpty (password))
                return new MblArchive (file, this, dir, password);
        }
        return new ArcFile (file, this, dir);
    }
    catch
    {
        return null;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Type != "script")
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var marc = arc as MblArchive;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (null == marc || null == marc.Key)
    {
        for (int i = 0; i < data.Length; ++i)
        {
            data[i] = (byte)-data[i];
        }
    }
    else if (marc.Key.Length > 0)
    {
        for (int i = 0; i < data.Length; ++i)
        {
            data[i] ^= marc.Key[i % marc.Key.Length];
        }
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### QueryPassPhrase

```csharp
string QueryPassPhrase (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownKeys.ContainsKey (title))
        return KnownKeys[title];
    var options = Query<MblOptions> (arcStrings.MBLNotice);
    return options.PassPhrase;
}
```

### GameRes.Formats.Marble.GraMblOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint filename_len = file.View.ReadUInt32 (0);
    int count = file.View.ReadInt32 (4);
    if (filename_len < 8 || filename_len > 0x40 || !IsSaneCount (count))
        return null;
    var arc_name = Path.GetFileNameWithoutExtension (file.Name);
    if (!arc_name.Equals ("mg_gra", StringComparison.InvariantCultureIgnoreCase))
        return null;

    uint index_offset = 8;
    uint index_size = (8u + filename_len) * (uint)count;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, filename_len);
        if (0 == name.Length)
            break;
        name = name.ToLowerInvariant();
        index_offset += filename_len;
        var entry = new Entry {
            Name    = Path.ChangeExtension (name, "bmp"),
            Type    = "image",
            Offset  = file.View.ReadUInt32 (index_offset),
            Size    = file.View.ReadUInt32 (index_offset+4),
        };
        if (entry.Offset < index_size || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    if (0 == dir.Count || (1 == dir.Count && count > 1))
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (input.PeekByte() != 0x78)
        return input;
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

## 配套算法与外部条件

- [ArcFormats/Marble/ImagePRS.cs](ImagePRS.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Marble/ArcMBL.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
