# Lucifen / ArcLPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LPK` / `GameRes.Formats.Lucifen.LpkOpener` | `lpk` | `4c504b31` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LpkOpener.Open` | `uint code = file.View.ReadUInt32 (4) ^ key2;` |
| `LpkOpener.ParseGameInit` | `if (!Binary.AsciiEqual (sob, "SOB0"))` |
| `LpkOpener.ParseGameInit` | `int offset = LittleEndian.ToInt32 (sob, 4) + 8;` |
| `IndexReader.Read` | `int count = LittleEndian.ToInt32 (m_index, 0);` |
| `IndexReader.Read` | `int letter_table_length = LittleEndian.ToInt32 (m_index, index_offset);` |
| `IndexReader.TraverseIndex` | `int next_offset  = 4 == m_index_width ? LittleEndian.ToInt32 (m_index, index_offset)` |
| `IndexReader.TraverseIndex` | `: (int)LittleEndian.ToUInt16 (m_index, index_offset);` |
| `IndexReader.AddEntry` | `long offset = LittleEndian.ToUInt32 (m_index, entry_pos);` |
| `IndexReader.AddEntry` | `entry.Size = LittleEndian.ToUInt32 (m_index, entry_pos+4);` |
| `IndexReader.AddEntry` | `uint unpacked_size = LittleEndian.ToUInt32 (m_index, entry_pos+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lucifen.LuciEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte Flag ;
```

### GameRes.Formats.Lucifen.LuciArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public          LpkInfo Info ;
```

#### LuciArchive

```csharp
public LuciArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, EncryptionScheme scheme, LpkInfo info)
    : base (arc, impl, dir) {
    Info = info;
    Scheme = scheme;
}
```

### GameRes.Formats.Lucifen.EncryptionScheme

#### 状态与常量

```csharp
public LpkOpener.Key BaseKey ;

public          byte ContentXor ;

public          uint RotatePattern ;

public          bool ImportGameInit ;
```

#### DecryptContent

```csharp
internal void DecryptContent (byte[] data) {
    for (int i = 0; i < data.Length; ++i)
    {
        int v = data[i] ^ ContentXor;
        data[i] = Binary.RotByteR ((byte)v, 4);
    }
}
```

#### DecryptEntry

```csharp
internal unsafe void DecryptEntry (byte[] data, int length, uint key) {
    uint pattern = RotatePattern;
    fixed (byte* buf_raw = data)
    {
        uint* encoded = (uint*)buf_raw;
        length /= 4;
        for (int i = 0; i < length; ++i)
        {
            encoded[i] ^= key;
            pattern = Binary.RotR (pattern, 4);
            key = Binary.RotL (key, (int)pattern);
        }
    }
}
```

#### DecryptIndex

```csharp
internal unsafe void DecryptIndex (byte[] data, int length, uint key) {
    uint pattern = RotatePattern;
    fixed (byte* buf_raw = data)
    {
        uint* encoded = (uint*)buf_raw;
        length /= 4;
        for (int i = 0; i < length; ++i)
        {
            encoded[i] ^= key;
            pattern = Binary.RotL (pattern, 4);
            key = Binary.RotR (key, (int)pattern);
        }
    }
}
```

### GameRes.Formats.Lucifen.LpkInfo

#### 状态与常量

```csharp
public bool AlignedOffset ;

public bool Flag1 ;

public bool IsEncrypted ;

public bool PackedEntries ;

public bool WholeCrypt ;

public bool IsPatchFile ;

public uint Key ;

public byte[] Prefix ;
```

### GameRes.Formats.Lucifen.LpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly EncryptionScheme DefaultScheme = new EncryptionScheme {
    BaseKey = new Key (0xA5B9AC6B, 0x9A639DE5), ContentXor = 0x5d, RotatePattern = 0x31746285,
    ImportGameInit = true
}

EncryptionScheme CurrentScheme = DefaultScheme ;

Dictionary<string, Key> CurrentFileMap = new Dictionary<string, Key>() ;

static readonly byte[] ScriptName = Encoding.ASCII.GetBytes ("SCRIPT") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string name = Path.GetFileName (file.Name).ToUpperInvariant();
    if (string.IsNullOrEmpty (name))
        return null;
    Key file_key = null;
    var basename = Encodings.cp932.GetBytes (Path.GetFileNameWithoutExtension (name));
    if (name != "SCRIPT.LPK")
        CurrentFileMap.TryGetValue (name, out file_key);
    try
    {
        var arc = Open (basename, file, CurrentScheme, file_key);
        if (null != arc)
            return arc;
    }
    catch {  }
    var new_scheme = QueryEncryptionScheme (file.Name);
    if (new_scheme == CurrentScheme && !CurrentScheme.ImportGameInit)
        return null;
    CurrentScheme = new_scheme;
    if (name != "SCRIPT.LPK" && CurrentScheme.ImportGameInit)
    {
        if (0 == CurrentFileMap.Count)
            ImportKeys (file.Name);
    }
    if (CurrentFileMap.Count > 0 && !CurrentFileMap.TryGetValue (name, out file_key))
        return null;
    return Open (basename, file, CurrentScheme, file_key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var lent = entry as LuciEntry;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null == lent)
        return input;
    if (lent.IsPacked)
    {
        input = new LzssStream (input);
    }
    var larc = arc as LuciArchive;
    if (null == larc)
        return input;
    var data = new byte[lent.UnpackedSize];
    using (input)
    {
        input.Read (data, 0, data.Length);
    }
    if (larc.Info.WholeCrypt && !(larc.Info.IsPatchFile && lent.Name.HasExtension ("elg")))
    {
        larc.Scheme.DecryptContent (data);
    }
    if (larc.Info.IsEncrypted)
    {
        int count = Math.Min (data.Length, 0x100);
        if (count != 0)
            larc.Scheme.DecryptEntry (data, count, larc.Info.Key);
    }
    input = new BinMemoryStream (data, entry.Name);
    if (null != larc.Info.Prefix)
        return new PrefixStream (larc.Info.Prefix, input);
    else
        return input;
}
```

#### Open

```csharp
ArcFile Open (byte[] basename, ArcView file, EncryptionScheme scheme, Key key) {
    uint key1 = scheme.BaseKey.Key1;
    uint key2 = scheme.BaseKey.Key2;
    for (int b = 0, e = basename.Length-1; e >= 0; ++b, --e)
    {
        key1 ^= basename[e];
        key2 ^= basename[b];
        key1 = Binary.RotR (key1, 7);
        key2 = Binary.RotL (key2, 7);
    }
    if (null != key)
    {
        key1 ^= key.Key1;
        key2 ^= key.Key2;
    }
    uint code = file.View.ReadUInt32 (4) ^ key2;
    int index_size = (int)(code & 0xffffff);
    byte flags = (byte)(code >> 24);
    if (0 != (flags & 1))
        index_size = (index_size << 11) - 8;
    if (index_size < 5 || index_size >= file.MaxOffset)
        return null;
    var index = new byte[index_size];
    if (index_size != file.View.Read (8, index, 0, (uint)index_size))
        return null;
    scheme.DecryptIndex (index, index_size, key2);
    var lpk_info = new LpkInfo
    {
        AlignedOffset = 0 != (flags & 1),
        Flag1         = 0 != (flags & 2),
        IsEncrypted   = 0 != (flags & 4),
        PackedEntries = 0 != (flags & 8),
        WholeCrypt    = 0 != (flags & 0x10),
        IsPatchFile   = 0 != (flags & 0x20),
        Key           = key1
    };
    var reader = new IndexReader (lpk_info);
    var dir = reader.Read (index);
    if (null == dir)
        return null;
    return new LuciArchive (file, this, dir, scheme, reader.Info);
}
```

#### ImportKeys

```csharp
void ImportKeys (string source_name) {
    var script_lpk = VFS.CombinePath (Path.GetDirectoryName (source_name), "SCRIPT.LPK");
    using (var script_file = VFS.OpenView (script_lpk))
    using (var script_arc  = Open (ScriptName, script_file, CurrentScheme, null))
    {
        if (null == script_arc)
            throw new UnknownEncryptionScheme();
        var entry = script_arc.Dir.FirstOrDefault (e => e.Name.Equals ("gameinit.sob", StringComparison.InvariantCultureIgnoreCase));
        if (null == entry)
            throw new FileNotFoundException ("Missing 'gameinit.sob' entry in SCRIPT.LPK");
        using (var gameinit = script_arc.OpenEntry (entry))
        {
            var init_data = new byte[gameinit.Length];
            gameinit.Read (init_data, 0, init_data.Length);
            if (!ParseGameInit (init_data))
                throw new UnknownEncryptionScheme();
        }
    }
}
```

#### ParseGameInit

```csharp
bool ParseGameInit (byte[] sob) {
    CurrentFileMap.Clear();
    if (!Binary.AsciiEqual (sob, "SOB0"))
        return false;
    int offset = LittleEndian.ToInt32 (sob, 4) + 8;
    if (offset <= 0 || offset >= sob.Length)
        return false;
    unsafe
    {
        fixed (byte* buf_raw = sob)
        {
            uint* p = (uint*)(buf_raw + offset);
            uint index_len = *p;
            if (offset+8+(int)index_len >= sob.Length)
                return false;
            p += 2;
            uint* last = p + index_len / 4 - 28;

            while (p < last)
            {
                if (p[0] == 0x28  && p[1] == 0  && p[2] != 0   && p[3] == 8  &&
                    p[4] == 1     && p[5] == 8  && p[6] == 1   && p[7] == 8  &&
                    p[8] != 0     && p[9] == 8  && p[10] != 0  && p[11] == 5 &&
                    p[17] == 0x28 && p[18] == 0 && p[19] != 0  && p[20] == 8 &&
                    p[21] != 0    && p[22] == 8 && p[23] == 0xffffffff && p[24] == 8 &&
                    p[25] == 1    && p[26] == 8 && p[27] == 1  && p[28] == 5)
                {
                    byte* lpk = (byte*)p + p[21] - p[2] + 0x34;
                    int name_index = (int)(lpk - buf_raw);
                    if (name_index < 0 || name_index >= sob.Length)
                    {
                        ++p;
                        continue;
                    }
                    string name = Binary.GetCString (sob, name_index, sob.Length-name_index);
                    name = name.ToUpperInvariant();
                    CurrentFileMap[name] = new Key (p[8], p[10]);
                    p += 0x22;
                } else
                    ++p;
            }
            return CurrentFileMap.Count > 0;
        }
    }
}
```

#### QueryEncryptionScheme

```csharp
EncryptionScheme QueryEncryptionScheme (string arc_name) {
    CurrentFileMap.Clear();
    string title = FormatCatalog.Instance.LookupGame (arc_name);
    Dictionary<string, Key> file_map;
    if (!string.IsNullOrEmpty (title) && KnownSchemes.ContainsKey (title))
    {
        if (KnownKeys.TryGetValue (title, out file_map))
            CurrentFileMap = new Dictionary<string, Key> (file_map);
        return KnownSchemes[title];
    }
    var options = Query<LuciOptions> (arcStrings.ArcEncryptedNotice);
    if (null == options)
        return DefaultScheme;
    title = options.Scheme;
    if (KnownKeys.TryGetValue (title, out file_map))
        CurrentFileMap = new Dictionary<string, Key> (file_map);
    return KnownSchemes[title];
}
```

### GameRes.Formats.Lucifen.LpkOpener.Key

#### 状态与常量

```csharp
public uint Key1, Key2 ;
```

#### Key

```csharp
public Key (uint k1, uint k2) {
    Key1 = k1;
    Key2 = k2;
}
```

### GameRes.Formats.Lucifen.IndexReader

#### 状态与常量

```csharp
byte[]          m_index ;

LpkInfo         m_info ;

List<Entry>     m_dir ;

byte[]          m_name ;

int             m_index_width ;

int             m_entries_offset ;

public LpkInfo  Info { get { return m_info; } }

public int EntrySize { get; private set; }
```

#### IndexReader

```csharp
public IndexReader (LpkInfo info) {
    if (!info.Flag1)
        throw new NotSupportedException ("Not supported LPK index format");
    m_info = info;
    EntrySize = m_info.PackedEntries ? 13 : 9;
}
```

#### Read

```csharp
public List<Entry> Read (byte[] index) {
    m_index = index;
    int count = LittleEndian.ToInt32 (m_index, 0);
    if (!ArchiveFormat.IsSaneCount (count))
        return null;
    int index_offset = 4;
    int prefix_length = m_index[index_offset++];
    if (0 != prefix_length)
    {
        m_info.Prefix = new byte[prefix_length];
        Buffer.BlockCopy (m_index, index_offset, m_info.Prefix, 0, prefix_length);
        index_offset += prefix_length;
    }
    m_index_width = 0 != m_index[index_offset++] ? 4 : 2;
    int letter_table_length = LittleEndian.ToInt32 (m_index, index_offset);
    index_offset += 4;
    m_entries_offset = index_offset + letter_table_length;
    if (m_entries_offset >= m_index.Length)
        return null;
    if ((m_index.Length - m_entries_offset) / EntrySize < count)
        EntrySize = (m_index.Length - m_entries_offset) / count;
    if (EntrySize < 8 || m_info.PackedEntries && EntrySize < 12)
        return null;

    m_dir = new List<Entry> (count);
    m_name = new byte[260];
    TraverseIndex (index_offset, 0);
    return m_dir.Count == count ? m_dir : null;
}
```

#### TraverseIndex

```csharp
void TraverseIndex (int index_offset, int name_length) {
    if (index_offset < 0 || index_offset >= m_index.Length)
        throw new InvalidFormatException ("Error parsing LPK index");
    if (name_length >= m_name.Length)
        throw new InvalidFormatException ("Entry filename is too long");
    int entries = m_index[index_offset++];
    for (int i = 0; i < entries; ++i)
    {
        byte next_letter = m_index[index_offset++];
        int next_offset  = 4 == m_index_width ? LittleEndian.ToInt32 (m_index, index_offset)
                                              : (int)LittleEndian.ToUInt16 (m_index, index_offset);
        m_name[name_length] = next_letter;
        index_offset += m_index_width;;
        if (0 != next_letter)
            TraverseIndex (index_offset+next_offset, name_length+1);
        else
            AddEntry (name_length, next_offset);
    }
}
```

#### AddEntry

```csharp
void AddEntry (int name_length, int entry_num) {
    if (name_length < 1)
        throw new InvalidFormatException ("Invalid LPK entry name");
    string name = Encodings.cp932.GetString (m_name, 0, name_length);
    var entry = FormatCatalog.Instance.Create<LuciEntry> (name);
    int entry_pos = m_entries_offset + EntrySize * entry_num;
    if (entry_pos+EntrySize > m_index.Length)
        throw new InvalidFormatException ("Invalid LPK entry index");
    if (0 != (EntrySize & 1))
        entry.Flag = m_index[entry_pos++];
    long offset = LittleEndian.ToUInt32 (m_index, entry_pos);
    entry.Offset = m_info.AlignedOffset ? offset << 11 : offset;
    entry.Size = LittleEndian.ToUInt32 (m_index, entry_pos+4);
    entry.UnpackedSize = entry.Size;
    if (m_info.PackedEntries)
    {
        uint unpacked_size = LittleEndian.ToUInt32 (m_index, entry_pos+8);
        entry.IsPacked = unpacked_size != 0;
        if (entry.IsPacked)
            entry.UnpackedSize = unpacked_size;
    }
    m_dir.Add (entry);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Lucifen/ArcLPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
