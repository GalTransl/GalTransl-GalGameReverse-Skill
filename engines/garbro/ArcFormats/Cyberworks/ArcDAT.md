# Cyberworks / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/Cyberworks/2` / `GameRes.Formats.Cyberworks.DatOpener2024` | `dat`, `04`, `05`, `06`, `app` | 无固定签名或来源表达式未解析 | `False` |
| `ARC/Cyberworks` / `GameRes.Formats.Cyberworks.DatOpener` | `dat`, `04`, `05`, `06`, `app` | 无固定签名或来源表达式未解析 | `False` |
| `ARC/Csystem/2` / `GameRes.Formats.Cyberworks.OldDatOpener2` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `ARC/Csystem` / `GameRes.Formats.Cyberworks.OldDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryParseMeta` | `int title_length = content.ReadInt32();` |
| `DatOpener.TryParseMeta` | `var title = content.ReadBytes (title_length);` |
| `TocUnpacker.DecodeDecimal` | `uint b = m_file.View.ReadByte (offset+i);` |
| `IndexReader.Read` | `int entry_size = m_index.ReadInt32();` |
| `IndexReader.Read` | `entry_size = m_index.ReadInt32();` |
| `IndexReader.ReadEntryInfo` | `uint id = m_index.ReadUInt32();` |
| `IndexReader.ReadEntryInfo` | `entry.UnpackedSize = m_index.ReadUInt32();` |
| `IndexReader.ReadEntryInfo` | `entry.Size = m_index.ReadUInt32();` |
| `IndexReader.ReadEntryInfo` | `entry.Offset = m_index.ReadUInt32();` |
| `ArcIndexReader.ReadEntryType` | `m_type[0] = (char)m_index.ReadByte();` |
| `ArcIndexReader.ReadEntryType` | `m_type[1] = (char)m_index.ReadByte();` |
| `ArcIndexReader.ReadEntryType` | `m_index.ReadInt32();` |
| `ArcIndexReader.ReadEntryType` | `entry_idx = m_index.ReadByte();` |
| `ArcIndexReader2.ReadEntryInfo` | `uint id = m_index.ReadUInt32();` |
| `ArcIndexReader2.ReadEntryInfo` | `entry.UnpackedSize = m_index.ReadUInt32();` |
| `ArcIndexReader2.ReadEntryInfo` | `entry.Offset = m_index.ReadUInt32();` |
| `ArcIndexReader2.ReadEntryInfo` | `entry.Size = m_index.ReadUInt32();` |
| `DatIndexReader.ReadEntryType` | `char type = (char)m_index.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Cyberworks.BellArchive

继承/接口：`ArcFile`。

#### BellArchive

```csharp
public BellArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, AImageScheme scheme)
    : base (arc, impl, dir) {
    Scheme = scheme;
}
```

### GameRes.Formats.Cyberworks.ArchiveNameParser

#### 状态与常量

```csharp
readonly Regex m_regex ;
```

#### ArchiveNameParser

```csharp
protected ArchiveNameParser (string pattern) {
    m_regex = new Regex (pattern, RegexOptions.IgnoreCase);
}
```

#### ParseName

```csharp
public Tuple<string, int> ParseName (string arc_name) {
    var match = m_regex.Match (arc_name);
    if (!match.Success)
        return null;
    int arc_idx;
    var toc_name = ParseMatch (match, out arc_idx);
    if (null == toc_name)
        return null;
    return Tuple.Create (toc_name, arc_idx);
}
```

#### ParseMatch

```csharp
protected abstract string ParseMatch (Match match, out int arc_idx) ;
```

### GameRes.Formats.Cyberworks.ArcNameParser

继承/接口：`ArchiveNameParser`。

#### ParseMatch

```csharp
protected override string ParseMatch (Match match, out int arc_idx) {
    arc_idx = 0;
    char num = match.Groups["num"].Value[0];
    int index_num;
    if (num >= '4' && num <= '6')
        index_num = num - '3';
    else if ('8' == num)
        index_num = 7;
    else
        return null;
    if (match.Groups["idx"].Success)
        arc_idx = char.ToUpper (match.Groups["idx"].Value[0]) - '@';

    var toc_name_builder = new StringBuilder (match.Value);
    var num_pos = match.Groups["id"].Index;
    toc_name_builder.Remove (num_pos, match.Groups["id"].Length);
    toc_name_builder.Insert (num_pos, index_num);
    return toc_name_builder.ToString();
}
```

### GameRes.Formats.Cyberworks.DatNameParser

继承/接口：`ArchiveNameParser`。

#### ParseMatch

```csharp
protected override string ParseMatch (Match match, out int arc_idx) {
    var toc_name_builder = new StringBuilder (match.Groups["name"].Value);
    arc_idx = 0;
    if (match.Groups["idx"].Success)
    {
        if ('a' == match.Groups["idx"].Value[0])
        {
            arc_idx = 1;
            toc_name_builder.Append ('h');
        }
    }
    else
        toc_name_builder.Append ('h');
    toc_name_builder.Append (".dat");
    return toc_name_builder.ToString();
}
```

### GameRes.Formats.Cyberworks.OldArcNameParser

继承/接口：`ArchiveNameParser`。

#### 状态与常量

```csharp
static readonly IDictionary<char, int> s_arcmap = new Dictionary<char, int> {
    { '2', 0 }, { '3', 1 }, { '5', 4 }
}
```

#### ParseMatch

```csharp
protected override string ParseMatch (Match match, out int arc_idx) {
    arc_idx = 0;
    char num = match.Groups["num"].Value[0];
    int index_num;
    if (!s_arcmap.TryGetValue (num, out index_num))
        return null;

    var toc_name_builder = new StringBuilder (match.Value);
    var num_pos = match.Groups["num"].Index;
    toc_name_builder.Remove (num_pos, match.Groups["num"].Length);
    toc_name_builder.Insert (num_pos, index_num);
    return toc_name_builder.ToString();
}
```

### GameRes.Formats.Cyberworks.PatchNameParser

继承/接口：`ArchiveNameParser`。

#### ParseMatch

```csharp
protected override string ParseMatch (Match match, out int arc_idx) {
    arc_idx = 0;
    int index_num = match.Groups["num"].Value[0] - '0' - 1;
    var toc_name_builder = new StringBuilder (match.Value);
    var num_pos = match.Groups["num"].Index;
    toc_name_builder.Remove (num_pos, match.Groups["num"].Length);
    toc_name_builder.Insert (num_pos, index_num);
    return toc_name_builder.ToString();
}
```

### GameRes.Formats.Cyberworks.InKyouParser

继承/接口：`ArchiveNameParser`。

#### ParseMatch

```csharp
protected override string ParseMatch (Match match, out int arc_idx) {
    arc_idx = 0;
    return match.Groups[1].Value + ".dat";
}
```

### GameRes.Formats.Cyberworks.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public bool BlendOverlayImages = true ;

static readonly ArchiveNameParser[] s_name_parsers = {
    new ArcNameParser(),
    new DatNameParser(),
    new PatchNameParser(),
    new InKyouParser()
}

static SchemeMap DefaultScheme = new SchemeMap {
    KnownSchemes = new Dictionary<string, AImageScheme>()
}
```

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat", "04", "05", "06", "app" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name);
    var dir_name = VFS.GetDirectoryName (file.Name);
    string game_name = arc_name != "Arc06.dat" ? TryParseMeta (VFS.CombinePath (dir_name, "Arc06.dat")) : null;
    Tuple<string, int> parsed = null;
    if (string.IsNullOrEmpty (game_name))
    {
        game_name = TryParseMeta (VFS.CombinePath (dir_name, "Arc00.dat"));
        parsed = s_name_parsers.Select (p => p.ParseName (arc_name)).FirstOrDefault (p => p != null);
    }
    else
        parsed = OldDatOpener.ArcNameParser.ParseName (arc_name);
    if (null == parsed)
        return null;
    string toc_name = parsed.Item1;
    int arc_idx = parsed.Item2;

    toc_name = VFS.CombinePath (dir_name, toc_name);
    var toc = ReadToc (toc_name, 8);
    if (null == toc)
        return null;
    using (var index = GetIndexReader (toc, file, arc_idx, game_name))
    {
        if (!index.Read())
            return null;
        return ArchiveFromDir (file, index.Dir, index.HasImages);
    }
}
```

#### GetIndexReader

```csharp
internal virtual IndexReader GetIndexReader (byte[] toc, ArcView file, int arc_idx, string game_name) {
    return new ArcIndexReader (toc, file, arc_idx, game_name);
}
```

#### GetTocUnpacker

```csharp
internal virtual TocUnpacker GetTocUnpacker (string toc_name) {
    return new TocUnpacker (toc_name);
}
```

#### ArchiveFromDir

```csharp
internal ArcFile ArchiveFromDir (ArcView file, List<Entry> dir, bool has_images) {
    if (0 == dir.Count)
        return null;
    if (!has_images)
        return new ArcFile (file, this, dir);
    var scheme = QueryScheme (file.Name);
    return new BellArchive (file, this, dir, scheme);
}
```

#### TryParseMeta

```csharp
internal string TryParseMeta (string meta_arc_name) {
    if (!VFS.FileExists (meta_arc_name))
        return null;
    using (var unpacker = GetTocUnpacker (meta_arc_name))
    {
        if (unpacker.Length > 0x1000)
            return null;
        var data = unpacker.Unpack (8);
        if (null == data)
            return null;
        using (var content = new BinMemoryStream (data))
        {
            int title_length = content.ReadInt32();
            if (title_length <= 0 || title_length > content.Length)
                return null;
            var title = content.ReadBytes (title_length);
            if (title.Length != title_length)
                return null;
            return Encodings.cp932.GetString (title);
        }
    }
}
```

#### ReadToc

```csharp
internal byte[] ReadToc (string toc_name, int num_length) {
    if (!VFS.FileExists (toc_name))
        return null;
    using (var toc_unpacker = GetTocUnpacker (toc_name))
        return toc_unpacker.Unpack (num_length);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null != pent && pent.IsPacked)
    {
        input = new LzssStream (input);
    }
    return input;
}
```

#### QueryScheme

```csharp
internal AImageScheme QueryScheme (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownSchemes.ContainsKey (title))
        return KnownSchemes[title];
    var options = Query<BellOptions> (arcStrings.ArcEncryptedNotice);
    return options.Scheme;
}
```

#### GetScheme

```csharp
public static AImageScheme GetScheme (string title) {
    AImageScheme scheme = null;
    if (string.IsNullOrEmpty (title) || !KnownSchemes.TryGetValue (title, out scheme))
        return null;
    return scheme;
}
```

### GameRes.Formats.Cyberworks.AImageScheme

#### 状态与常量

```csharp
public byte     Value1 ;

public byte     Value2 ;

public byte     Value3 ;

public byte[]   HeaderOrder ;

public bool     Flipped ;

public bool     UseDataDecoder ;
```

#### AImageScheme

```csharp
public AImageScheme () {
    Flipped = true;
}
```

### GameRes.Formats.Cyberworks.DatOpener2024

继承/接口：`DatOpener`。

#### GetIndexReader

```csharp
internal override IndexReader GetIndexReader (byte[] toc, ArcView file, int arc_idx, string game_name) {
    return new ArcIndexReader2 (toc, file, arc_idx, game_name);
}
```

#### GetTocUnpacker

```csharp
internal override TocUnpacker GetTocUnpacker (string toc_name) {
    return new TocUnpacker (toc_name, true);
}
```

### GameRes.Formats.Cyberworks.OldDatOpener

继承/接口：`DatOpener`。

#### 状态与常量

```csharp
internal static readonly ArchiveNameParser ArcNameParser = new OldArcNameParser() ;
```

#### OldDatOpener

```csharp
public OldDatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name);
    var parsed = ArcNameParser.ParseName (arc_name);
    if (null == parsed)
        return null;
    var toc_name = VFS.CombinePath (VFS.GetDirectoryName (file.Name), parsed.Item1);
    var toc = ReadToc (toc_name, 4);
    if (null == toc)
        return null;

    bool has_images = false;
    var dir = new List<Entry>();
    using (var toc_stream = new MemoryStream (toc))
    using (var index = new StreamReader (toc_stream))
    {
        string line;
        while ((line = index.ReadLine()) != null)
        {
            var fields = line.Split (',');
            if (fields.Length != 5)
                return null;
            var name = Path.ChangeExtension (fields[0], fields[4]);
            string type = "";
            if ("b" == fields[4])
            {
                type = "image";
                has_images = true;
            }
            else if ("k" == fields[4] || "j" == fields[4])
                type = "audio";
            var entry = new PackedEntry
            {
                Name = name,
                Type = type,
                Offset       = UInt32.Parse (fields[3]),
                Size         = UInt32.Parse (fields[2]),
                UnpackedSize = UInt32.Parse (fields[1]),
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = entry.UnpackedSize != entry.Size && entry.UnpackedSize != 0;
            dir.Add (entry);
        }
    }
    return ArchiveFromDir (file, dir, has_images);
}
```

### GameRes.Formats.Cyberworks.OldDatOpener2

继承/接口：`DatOpener`。

#### OldDatOpener2

```csharp
public OldDatOpener2 () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name);
    var parsed = OldDatOpener.ArcNameParser.ParseName (arc_name);
    if (null == parsed)
        return null;
    var toc_name = VFS.CombinePath (VFS.GetDirectoryName (file.Name), parsed.Item1);
    var toc = ReadToc (toc_name, 4);
    if (null == toc)
        return null;
    using (var index = new DatIndexReader (toc, file))
    {
        if (!index.Read())
            return null;
        return ArchiveFromDir (file, index.Dir, index.HasImages);
    }
}
```

### GameRes.Formats.Cyberworks.TocUnpacker

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
ArcView   m_file ;

bool      m_should_dispose ;

bool      m_reversed_decimal ;

public long       Length { get { return m_file.MaxOffset; } }

public uint   PackedSize { get; private set; }

public uint UnpackedSize { get; private set; }

bool _disposed = false ;
```

#### TocUnpacker

```csharp
public TocUnpacker (ArcView file, bool should_dispose = false, bool reversed_decimal = false) {
    m_file = file;
    m_should_dispose = should_dispose;
    m_reversed_decimal = reversed_decimal;
}
```

#### Unpack

```csharp
public byte[] Unpack (int num_length) {
    return Unpack (0, num_length);
}
```

#### Unpack

```csharp
public byte[] Unpack (long offset, int num_length) {
    long data_offset = offset + num_length*2;
    if (m_file.MaxOffset <= data_offset)
        return null;
    UnpackedSize = DecodeDecimal (offset, num_length);
    if (UnpackedSize <= 4 || UnpackedSize > 0x1000000)
        return null;
    PackedSize = DecodeDecimal (offset+num_length, num_length);
    if (PackedSize > m_file.MaxOffset - data_offset || 0 == PackedSize)
        return null;
    return UnpackAt (data_offset);
}
```

#### UnpackAt

```csharp
byte[] UnpackAt (long offset) {
    using (var toc_s = m_file.CreateStream (offset, PackedSize))
    using (var lzss = new LzssStream (toc_s))
    {
        var toc = new byte[UnpackedSize];
        if (toc.Length != lzss.Read (toc, 0, toc.Length))
            return null;
        return toc;
    }
}
```

#### DecodeDecimal

```csharp
internal uint DecodeDecimal (long offset, int num_length) {
    uint v = 0;
    uint rank = 1;

    int start, end, step;
    if (m_reversed_decimal)
    {
        start = 0;
        end = num_length;
        step = 1;
    }
    else
    {
        start = num_length-1;
        end = -1;
        step = -1;
    }

    for (int i = start; i != end; i += step, rank *= 10)
    {
        uint b = m_file.View.ReadByte (offset+i);
        if (b != 0xFF)
            v += (b ^ 0x7F) * rank;
    }
    return v;
}
```

### GameRes.Formats.Cyberworks.IndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
protected IBinaryStream   m_index ;

readonly  long            m_max_offset ;

private   List<Entry>     m_dir ;

public List<Entry> Dir { get { return m_dir; } }

public long  MaxOffset { get { return m_max_offset; } }

public bool  HasImages { get; protected set; }

protected uint m_fault_id = 100000 ;

bool _disposed = false ;
```

#### IndexReader

```csharp
public IndexReader (byte[] toc, ArcView file) {
    m_index = new BinMemoryStream (toc);
    m_max_offset = file.MaxOffset;
}
```

#### Read

```csharp
public bool Read () {
    int entry_size = m_index.ReadInt32();
    if (entry_size < 0x11)
        return false;
    int count = (int)m_index.Length / (entry_size + 4);
    if (!ArchiveFormat.IsSaneCount (count))
        return false;
    long next_pos = 0;
    m_dir = new List<Entry> (count);
    while (next_pos < m_index.Length)
    {
        m_index.Position = next_pos;
        entry_size = m_index.ReadInt32();
        if (entry_size <= 0)
            return false;
        next_pos += 4 + entry_size;
        var entry = ReadEntryInfo();
        if (ReadEntryType (entry, entry_size))
        {
            if (entry.CheckPlacement (MaxOffset))
                m_dir.Add (entry);
        }
    }
    return true;
}
```

#### ReadEntryInfo

```csharp
internal virtual PackedEntry ReadEntryInfo () {
    uint id = m_index.ReadUInt32();
    if (id > m_fault_id)
        id = m_fault_id++;
    var entry = new PackedEntry { Name = id.ToString ("D6") };
    entry.UnpackedSize = m_index.ReadUInt32();
    entry.Size = m_index.ReadUInt32();
    entry.IsPacked = entry.UnpackedSize != entry.Size && entry.UnpackedSize != 0;
    entry.Offset = m_index.ReadUInt32();
    return entry;
}
```

#### ReadEntryType

```csharp
protected abstract bool ReadEntryType (Entry entry, int entry_size) ;
```

### GameRes.Formats.Cyberworks.ArcIndexReader

继承/接口：`IndexReader`。

#### 状态与常量

```csharp
int     m_arc_number ;

string  m_game_name ;

bool    m_ignore_b_files = false ;

char[]  m_type = new char[2] ;
```

#### ArcIndexReader

```csharp
public ArcIndexReader (byte[] toc, ArcView file, int arc_number, string game_name = null) : base (toc, file) {
    m_arc_number = arc_number;
    m_game_name = game_name;
    m_ignore_b_files = m_game_name == "ドキドキ母娘レッスン ～教えて♪Ｈなお勉強～";
}
```

#### ReadEntryType

```csharp
protected override bool ReadEntryType (Entry entry, int entry_size) {
    m_type[0] = (char)m_index.ReadByte();
    m_type[1] = (char)m_index.ReadByte();
    int entry_idx = 0;
    if (entry_size >= 0x17)
    {
        m_index.ReadInt32();
        entry_idx = m_index.ReadByte();
    }
    if (entry_idx != m_arc_number)
        return false;
    if (m_type[0].IsAsciiVisible())
    {
        string ext;
        if (m_type[1].IsAsciiVisible())
            ext = new string (m_type);
        else
            ext = new string (m_type[0], 1);
        if ("b0" == ext || "n0" == ext || "o0" == ext || "0b" == ext || ("b" == ext && !m_ignore_b_files))
        {
            entry.Type = "image";
            HasImages = true;
        }
        else if ("j0" == ext || "k0" == ext || "u0" == ext || "j" == ext || "k" == ext)
            entry.Type = "audio";
        entry.Name = Path.ChangeExtension (entry.Name, ext);
    }
    return true;
}
```

### GameRes.Formats.Cyberworks.ArcIndexReader2

继承/接口：`ArcIndexReader`。

#### ReadEntryInfo

```csharp
internal override PackedEntry ReadEntryInfo () {
    uint id = m_index.ReadUInt32();
    if (id > m_fault_id)
        id = m_fault_id++;
    var entry = new PackedEntry { Name = id.ToString ("D6") };
    entry.UnpackedSize = m_index.ReadUInt32();
    entry.Offset = m_index.ReadUInt32();
    entry.Size = m_index.ReadUInt32();
    entry.IsPacked = entry.UnpackedSize != entry.Size && entry.UnpackedSize != 0;
    return entry;
}
```

### GameRes.Formats.Cyberworks.DatIndexReader

继承/接口：`IndexReader`。

#### ReadEntryType

```csharp
protected override bool ReadEntryType (Entry entry, int entry_size) {
    if (entry_size > 0x11)
        throw new InvalidFormatException();
    char type = (char)m_index.ReadByte();
    if (type.IsAsciiVisible())
    {
        string ext = new string (type, 1);
        if ('b' == type)
        {
            entry.Type = "image";
            HasImages = true;
        }
        else if ('k' == type || 'j' == type)
            entry.Type = "audio";
        entry.Name = Path.ChangeExtension (entry.Name, ext);
    }
    return true;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cyberworks/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
