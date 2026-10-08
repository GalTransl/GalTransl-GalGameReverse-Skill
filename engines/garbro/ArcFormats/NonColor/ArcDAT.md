# NonColor / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/noncolor` / `GameRes.Formats.NonColor.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0) ^ SignatureKey;` |
| `DatOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `DatOpener.ReadFileMapIndex` | `int scheme_count = idx.ReadInt32();` |
| `DatOpener.ReadFileMapIndex` | `ulong   key = idx.ReadUInt64();` |
| `DatOpener.ReadFileMapIndex` | `uint offset = idx.ReadUInt32();` |
| `DatOpener.ReadFileMapIndex` | `int   count = idx.ReadInt32();` |
| `DatOpener.ReadFilenameMap` | `ulong   key = idx.ReadUInt64();` |
| `DatOpener.ReadFilenameMap` | `uint offset = idx.ReadUInt32();` |
| `DatOpener.ReadFilenameMap` | `int  length = idx.ReadInt32();` |
| `DatOpener.ReadFilenameMap` | `var name_bytes = lst.ReadBytes (length);` |
| `NcIndexReader.ReadEntry` | `var hash   = m_input.ReadUInt64();` |
| `NcIndexReader.ReadEntry` | `int flags  = m_input.ReadByte() ^ (byte)hash;` |
| `NcIndexReader.ReadEntry` | `Offset = m_input.ReadUInt32() ^ (uint)hash ^ m_master_key,` |
| `NcIndexReader.ReadEntry` | `Size   = m_input.ReadUInt32() ^ (uint)hash,` |
| `NcIndexReader.ReadEntry` | `UnpackedSize = m_input.ReadUInt32() ^ (uint)hash,` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NonColor.ArcDatEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte[]   RawName ;

public ulong    Hash ;

public int      Flags ;
```

### GameRes.Formats.NonColor.ArcDatArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly ulong MasterKey ;
```

#### ArcDatArchive

```csharp
public ArcDatArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ulong key)
    : base (arc, impl, dir) {
    MasterKey = key;
}
```

### GameRes.Formats.NonColor.Scheme

#### 状态与常量

```csharp
public string   Title ;

public ulong    Hash ;

public string   FileListName ;

public bool     LowCaseNames ;

public bool     IgnoreScriptKey ;
```

#### ComputeHash

```csharp
public virtual ulong ComputeHash (byte[] name) {
    return Crc64.Compute (name, 0, name.Length);
}
```

#### GetBytes

```csharp
public byte[] GetBytes (string name) {
    if (LowCaseNames)
        return name.ToLowerShiftJis();
    else
        return Encodings.cp932.GetBytes (name);
}
```

### GameRes.Formats.NonColor.NameRecord

#### 状态与常量

```csharp
public string   Name ;

public byte[]   NameBytes ;
```

### GameRes.Formats.NonColor.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal const int SignatureKey = 0x26ACA46E ;

public static readonly string PersistentFileMapName = "NCFileMap.dat" ;

static IDictionary<ulong, Tuple<uint, int>> FileMapIndex = null ;

Tuple<ulong, Dictionary<ulong, NameRecord>> LastAccessedScheme ;

static ArcDatScheme DefaultScheme = new ArcDatScheme { KnownSchemes = new Dictionary<string, Scheme>() }
```

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    int count = file.View.ReadInt32 (0) ^ SignatureKey;
    if (!IsSaneCount (count))
        return null;

    var scheme = QueryScheme (file.Name);
    if (null == scheme)
        return null;

    using (var index = new NcIndexReader (file, count))
        return index.Read (this, scheme);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var darc = arc as ArcDatArchive;
    var dent = entry as ArcDatEntry;
    if (null == darc || null == dent || 0 == dent.Size)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (dent.IsPacked)
    {
        if (darc.MasterKey != 0)
            DecryptData (data, (uint)(dent.Hash ^ darc.MasterKey));
        else if (6 == dent.Flags)
            DecryptData (data, (uint)dent.Hash);
        return new ZLibStream (new MemoryStream (data), CompressionMode.Decompress);
    }

    if (dent.RawName != null && 0 != dent.Flags)
        DecryptWithName (data, dent.RawName);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
internal unsafe void DecryptData (byte[] data, uint key) {
    fixed (byte* data8 = data)
    {
        uint* data32 = (uint*)data8;
        for (int i = data.Length/4; i > 0; --i)
            *data32++ ^= key;
    }
}
```

#### DecryptWithName

```csharp
internal void DecryptWithName (byte[] data, byte[] name) {
    int block_length = data.Length / name.Length;
    int n = 0;
    for (int i = 0; i < name.Length-1; ++i)
    for (int j = 0; j < block_length; ++j)
        data[n++] ^= name[i];
}
```

#### ReadFileMapIndex

```csharp
internal IDictionary<ulong, Tuple<uint, int>> ReadFileMapIndex (BinaryReader idx) {
    int scheme_count = idx.ReadInt32();
    idx.BaseStream.Seek (12, SeekOrigin.Current);
    var map = new Dictionary<ulong, Tuple<uint, int>> (scheme_count);
    for (int i = 0; i < scheme_count; ++i)
    {
        ulong   key = idx.ReadUInt64();
        uint offset = idx.ReadUInt32();
        int   count = idx.ReadInt32();
        map[key] = Tuple.Create (offset, count);
    }
    return map;
}
```

#### ReadFilenameMap

```csharp
internal IDictionary<ulong, NameRecord> ReadFilenameMap (Scheme scheme) {
    if (null != LastAccessedScheme && LastAccessedScheme.Item1 == scheme.Hash)
        return LastAccessedScheme.Item2;
    if (!string.IsNullOrEmpty (scheme.FileListName))
    {
        var dict = new Dictionary<ulong, NameRecord>();
        FormatCatalog.Instance.ReadFileList (scheme.FileListName, line => {
            var bytes = scheme.GetBytes (line);
            ulong hash = scheme.ComputeHash (bytes);
            dict[hash] = new NameRecord { Name = line, NameBytes = bytes };
        });
        LastAccessedScheme = Tuple.Create (scheme.Hash, dict);
        return dict;
    }
    var dir = FormatCatalog.Instance.DataDirectory;
    var lst_file = Path.Combine (dir, PersistentFileMapName);
    var idx_file = Path.ChangeExtension (lst_file, ".idx");
    using (var idx_stream = File.OpenRead (idx_file))
    using (var idx = new BinaryReader (idx_stream))
    {
        if (null == FileMapIndex)
            FileMapIndex = ReadFileMapIndex (idx);

        Tuple<uint, int> nc_info;
        if (!FileMapIndex.TryGetValue (scheme.Hash, out nc_info))
            throw new UnknownEncryptionScheme();

        using (var lst_stream = File.OpenRead (lst_file))
        using (var lst = new BinaryReader (lst_stream))
        {
            var name_map = new Dictionary<ulong, NameRecord> (nc_info.Item2);
            idx_stream.Position = nc_info.Item1;
            for (int i = 0; i < nc_info.Item2; ++i)
            {
                ulong   key = idx.ReadUInt64();
                uint offset = idx.ReadUInt32();
                int  length = idx.ReadInt32();
                lst_stream.Position = offset;
                var name_bytes = lst.ReadBytes (length);
                var name = Encodings.cp932.GetString (name_bytes);
                name_map[key] = new NameRecord { Name = name, NameBytes = name_bytes };
            }
            LastAccessedScheme = Tuple.Create (scheme.Hash, name_map);
            return name_map;
        }
    }
}
```

#### QueryScheme

```csharp
internal Scheme QueryScheme (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownSchemes.ContainsKey (title))
        return KnownSchemes[title];
    var options = Query<ArcDatOptions> (arcStrings.ArcEncryptedNotice);
    Scheme scheme;
    if (string.IsNullOrEmpty (options.Scheme) || !KnownSchemes.TryGetValue (options.Scheme, out scheme))
        return null;
    return scheme;
}
```

### GameRes.Formats.NonColor.NcIndexReaderBase

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
protected IBinaryStream m_input ;

private   List<Entry>   m_dir ;

private   int           m_count ;

private   ArcView       m_file ;

public long IndexPosition { get; set; }

public long     MaxOffset { get { return m_file.MaxOffset; } }

public bool ExtendByteSign { get; protected set; }

bool m_disposed = false ;
```

#### NcIndexReaderBase

```csharp
protected NcIndexReaderBase (ArcView file, int count) {
    m_input = file.CreateStream();
    m_dir = new List<Entry> (count);
    m_count = count;
    m_file = file;
    IndexPosition = 4;
}
```

#### Read

```csharp
public ArcFile Read (DatOpener format, Scheme scheme) {
    var file_map = format.ReadFilenameMap (scheme);
    var dir = Read (file_map);
    if (null == dir)
        return null;
    var master_key = scheme.IgnoreScriptKey ? 0ul : scheme.Hash;
    return new ArcDatArchive (m_file, format, dir, master_key);
}
```

#### Read

```csharp
public List<Entry> Read (IDictionary<ulong, NameRecord> file_map) {
    int skipped = 0, last_reported = -1;
    string last_name = null;
    m_input.Position = IndexPosition;
    for (int i = 0; i < m_count; ++i)
    {
        var entry = ReadEntry();
        NameRecord known_rec;
        if (file_map.TryGetValue (entry.Hash, out known_rec))
        {
            entry.Name = known_rec.Name;
            entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
            entry.RawName = known_rec.NameBytes;
            if (null == last_name && i > 0)
            {
                Trace.WriteLine (string.Format ("[{0}] {1}", i, known_rec.Name), "[noncolor]");
                last_reported = i;
            }
        }
        else
        {
            if (last_name != null && last_reported != i-1)
                Trace.WriteLine (string.Format ("[{0}] {1}", i-1, last_name), "[noncolor]");
            Trace.WriteLine (string.Format ("[{0}] Unknown hash {1:X08}", i, entry.Hash), "[noncolor]");
            last_name = null;
        }
        if (0 == (entry.Flags & 2))
        {
            if (null == known_rec.Name)
            {
                ++skipped;
                continue;
            }
            else
            {
                var raw_name = known_rec.NameBytes;
                entry.Offset        ^= Extend8Bit (raw_name[raw_name.Length >> 1]);
                entry.Size          ^= Extend8Bit (raw_name[raw_name.Length >> 2]);
                entry.UnpackedSize  ^= Extend8Bit (raw_name[raw_name.Length >> 3]);
            }
        }
        last_name = known_rec.Name;
        if (!entry.CheckPlacement (MaxOffset))
        {
            Trace.WriteLine (string.Format ("{0}: invalid placement [key:{1:X8}] [{2:X8}:{3:X8}]", entry.Name, entry.Hash, entry.Offset, entry.Size));
            continue;
        }
        if (string.IsNullOrEmpty (entry.Name))
            entry.Name = string.Format ("{0:D5}#{1:X8}", i, entry.Hash);
        m_dir.Add (entry);
    }
    if (skipped != 0)
        Trace.WriteLine (string.Format ("Missing {0} names", skipped), "[noncolor]");
    if (0 == m_dir.Count)
        return null;
    return m_dir;
}
```

#### Extend8Bit

```csharp
uint Extend8Bit (byte v) {

    return ExtendByteSign ? (uint)(int)(sbyte)v : v;
}
```

#### ReadEntry

```csharp
protected abstract ArcDatEntry ReadEntry () ;
```

### GameRes.Formats.NonColor.NcIndexReader

继承/接口：`NcIndexReaderBase`。

#### 状态与常量

```csharp
readonly uint   m_master_key ;
```

#### NcIndexReader

```csharp
public NcIndexReader (ArcView file, int count, uint master_key = 0) : base (file, count) {
    m_master_key = master_key;
}
```

#### ReadEntry

```csharp
protected override ArcDatEntry ReadEntry () {
    var hash   = m_input.ReadUInt64();
    int flags  = m_input.ReadByte() ^ (byte)hash;
    return new ArcDatEntry {
        Hash   = hash,
        Flags  = flags,
        Offset = m_input.ReadUInt32() ^ (uint)hash ^ m_master_key,
        Size   = m_input.ReadUInt32() ^ (uint)hash,
        UnpackedSize = m_input.ReadUInt32() ^ (uint)hash,
        IsPacked = 0 != (flags & 2),
    };
}
```

## 配套算法与外部条件

- [ArcFormats/Crc64.cs](../Crc64.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/NonColor/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
