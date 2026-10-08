# YaneSDK / ArcHibiki：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/hibiki` / `GameRes.Formats.YaneSDK.HDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `HDatOpener.ReadCount` | `return (short)(file.View.ReadUInt16 (0) ^ 0x8080);` |
| `HDatOpener.TryOpenWithScheme` | `index.ReadUInt16();` |
| `HDatOpener.TryOpenWithScheme` | `entry.Size = index.ReadUInt32();` |
| `HDatOpener.TryOpenWithScheme` | `entry.Offset = index.ReadUInt32();` |
| `HDatOpener.TryOpenWithScheme` | `index.ReadUInt32();` |
| `HDatOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (entry.Offset, encrypted);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.YaneSDK.HDatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public static readonly string SchemeFileName = "hibiki_works.dat" ;

static Lazy<HibikiScheme> s_Scheme = new Lazy<HibikiScheme> (DeserializeScheme) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    int count = ReadCount (file);
    if (!IsSaneCount (count))
        return null;
    var scheme = QueryScheme (file.Name);
    if (null == scheme)
        return null;
    return TryOpenWithScheme (file, count, scheme);
}
```

#### ReadCount

```csharp
int ReadCount (ArcView file) {
    return (short)(file.View.ReadUInt16 (0) ^ 0x8080);
}
```

#### TryOpenWithScheme

```csharp
ArcFile TryOpenWithScheme (ArcView file, int count, HibikiDatScheme scheme) {
    var dat_name = Path.GetFileName (file.Name).ToLowerInvariant();
    IList<HibikiTocRecord> toc_table = null;
    if (scheme.ArcMap != null && scheme.ArcMap.TryGetValue (dat_name, out toc_table))
    {
        if (toc_table.Count != count)
            toc_table = null;
    }
    using (var input = OpenLstIndex (file, dat_name, scheme))
    using (var dec = new XoredStream (input, 0x80))
    using (var index = new BinaryReader (dec))
    {
        const int name_length = 0x100;
        int data_offset = 2 + (name_length + 10) * count;
        index.BaseStream.Position = 2;
        Func<int, Entry> read_entry;
        if (null == toc_table)
        {
            var name_buf = new byte[name_length];
            read_entry = i => {
                if (name_length != index.Read (name_buf, 0, name_length))
                    return null;
                var name = Binary.GetCString (name_buf, 0);
                var entry = FormatCatalog.Instance.Create<Entry> (name);
                index.ReadUInt16();
                entry.Size = index.ReadUInt32();
                entry.Offset = index.ReadUInt32();
                return entry;
            };
        }
        else
        {
            read_entry = i => {
                index.BaseStream.Seek (name_length + 6, SeekOrigin.Current);
                index.ReadUInt32();
                var toc_entry = toc_table[i];
                var entry = FormatCatalog.Instance.Create<Entry> (toc_entry.Name);
                entry.Offset = toc_entry.Offset;
                entry.Size = toc_entry.Size;
                return entry;
            };
        }
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var entry = read_entry (i);
            if (null == entry || string.IsNullOrWhiteSpace (entry.Name)
                || entry.Offset < data_offset || entry.Size > file.MaxOffset)
                return null;
            dir.Add (entry);
        }
        return new HibikiArchive (file, this, dir, scheme.ContentKey);
    }
}
```

#### OpenLstIndex

```csharp
Stream OpenLstIndex (ArcView file, string dat_name, HibikiDatScheme scheme) {
    var lst_name = Path.ChangeExtension (file.Name, ".lst");
    if (VFS.FileExists (lst_name))
        return VFS.OpenStream (lst_name);
    else if ("init.dat" == dat_name)
        return file.CreateStream();

    var dir_name = VFS.GetDirectoryName (file.Name);
    var init_dat = VFS.CombinePath (dir_name, "init.dat");
    if (!VFS.FileExists (init_dat))
    {
        init_dat = VFS.CombinePath (VFS.CombinePath (dir_name, "arc"), "init.dat");
        if (!VFS.FileExists (init_dat))
            return file.CreateStream();
    }
    try
    {
        using (var init = VFS.OpenView (init_dat))
        using (var init_arc = TryOpenWithScheme (init, ReadCount (init), scheme))
        {
            lst_name = Path.GetFileName (lst_name);
            var lst_entry = init_arc.Dir.First (e => e.Name == lst_name);
            return init_arc.OpenEntry (lst_entry);
        }
    }
    catch
    {
        return file.CreateStream();
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var harc = arc as HibikiArchive;
    if (null == harc)
        return base.OpenEntry (arc, entry);
    var key = harc.Key;
    uint encrypted = Math.Min (entry.Size, (uint)key.Length);
    var header = arc.File.View.ReadBytes (entry.Offset, encrypted);
    for (int i = 0; i < header.Length; ++i)
        header[i] ^= key[i];
    if (encrypted == entry.Size)
        return new BinMemoryStream (header);
    var rest = arc.File.CreateStream (entry.Offset + encrypted, entry.Size - encrypted);
    return new PrefixStream (header, rest);
}
```

#### QueryScheme

```csharp
HibikiDatScheme QueryScheme (string arc_name) {
    if (null == KnownSchemes)
        return null;

    return KnownSchemes.Values.FirstOrDefault();
}
```

#### DeserializeScheme

```csharp
static HibikiScheme DeserializeScheme () {
    try
    {
        var dir = FormatCatalog.Instance.DataDirectory;
        var scheme_file = Path.Combine (dir, SchemeFileName);
        using (var input = File.OpenRead (scheme_file))
        {
            var bin = new BinaryFormatter();
            return (HibikiScheme)bin.Deserialize (input);
        }
    }
    catch (Exception X)
    {
        Trace.WriteLine (X.Message, "hibiki_works scheme deserialization failed");
        return new HibikiScheme();
    }
}
```

### GameRes.Formats.YaneSDK.HibikiArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### HibikiArchive

```csharp
public HibikiArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.YaneSDK.HibikiDatScheme

#### 状态与常量

```csharp
public byte[]   ContentKey ;

public IDictionary<string, IList<HibikiTocRecord>>   ArcMap ;
```

### GameRes.Formats.YaneSDK.HibikiTocRecord

#### 状态与常量

```csharp
public string   Name ;

public uint     Offset ;

public uint     Size ;
```

#### HibikiTocRecord

```csharp
public HibikiTocRecord (string name, uint offset, uint size) {
    Name = name;
    Offset = offset;
    Size = size;
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/YaneSDK/ArcHibiki.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
