# RPM / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/RPM` / `GameRes.Formats.Rpm.ArcOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `ArcOpener.TryOpen` | `is_compressed = file.View.ReadUInt32 (4);` |
| `ArcOpener.TryOpen` | `var first_entry = file.View.ReadBytes (8, 0x20);` |
| `ArcIndexReader.ReadIndex` | `var index = m_file.View.ReadBytes (offset, (uint)index_size);` |
| `ArcIndexReader.ReadIndex` | `uint data_offset = LittleEndian.ToUInt32 (index, scheme.NameLength + 8);` |
| `ArcIndexReader.ReadIndex` | `entry.UnpackedSize  = LittleEndian.ToUInt32 (index, index_offset);` |
| `ArcIndexReader.ReadIndex` | `entry.Size          = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `ArcIndexReader.ReadIndex` | `entry.Offset        = LittleEndian.ToUInt32 (index, index_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Rpm.EncryptionScheme

#### 状态与常量

```csharp
public string   Keyword ;

public int      NameLength ;

public int      IndexOffset ;
```

#### EncryptionScheme

```csharp
public EncryptionScheme (string key, int name_length = 32, int index_offset = 8) {
    Keyword = key;
    NameLength = name_length;
    IndexOffset = index_offset;
}
```

### GameRes.Formats.Rpm.ArcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const int MinEntryLength = 0x1C ;

static readonly int[] PossibleNameSizes = new[] { 0x20, 0x18, 0x10 }
```

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count) || 4 + count * MinEntryLength >= file.MaxOffset)
        return null;

    uint is_compressed = 1;
    var index_reader = new ArcIndexReader (file, count);
    var scheme = index_reader.GuessScheme (4, PossibleNameSizes);
    if (null == scheme)
    {
        is_compressed = file.View.ReadUInt32 (4);
        if (is_compressed <= 1)
            scheme = index_reader.GuessScheme (8, PossibleNameSizes);
    }

    if (null == scheme && KnownSchemes.Count > 0 && file.Name.HasExtension (".arc"))
    {
        var first_entry = file.View.ReadBytes (8, 0x20);
        if (-1 == Array.FindIndex (first_entry, x => x != 0))
            return null;
        scheme = QueryScheme();
    }
    if (null == scheme)
        return null;

    if (scheme.Keyword != "inst"
        && VFS.IsPathEqualsToFileName (file.Name, "instdata.arc"))
        scheme = new EncryptionScheme ("inst", scheme.NameLength);

    var dir = index_reader.ReadIndex (scheme, scheme.IndexOffset > 4 ? is_compressed != 0 : true);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var packed = entry as PackedEntry;
    if (null == packed || !packed.IsPacked)
        return input;
    return new LzssStream (input);
}
```

#### QueryScheme

```csharp
EncryptionScheme QueryScheme () {
    var options = Query<RpmOptions> (arcStrings.RPMEncryptedNotice);
    return options.Scheme;
}
```

#### GetScheme

```csharp
static EncryptionScheme GetScheme (string title) {
    EncryptionScheme scheme = null;
    KnownSchemes.TryGetValue (title, out scheme);
    return scheme;
}
```

### GameRes.Formats.Rpm.ArcIndexReader

#### 状态与常量

```csharp
ArcView             m_file ;

int                 m_count ;
```

#### ArcIndexReader

```csharp
public ArcIndexReader (ArcView file, int count) {
    m_file = file;
    m_count = count;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex (EncryptionScheme scheme, bool is_compressed) {
    long offset = scheme.IndexOffset;
    int index_size = m_count * (scheme.NameLength + 12);
    var index = m_file.View.ReadBytes (offset, (uint)index_size);
    if (index.Length != index_size)
        return null;
    DecryptIndex (index, scheme.Keyword);

    uint data_offset = LittleEndian.ToUInt32 (index, scheme.NameLength + 8);
    if (data_offset != offset + index_size)
        return null;

    int index_offset = 0;
    var dir = new List<Entry> (m_count);
    for (int i = 0; i < m_count; ++i)
    {
        var name = Binary.GetCString (index, index_offset, scheme.NameLength);
        index_offset += scheme.NameLength;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.UnpackedSize  = LittleEndian.ToUInt32 (index, index_offset);
        entry.Size          = LittleEndian.ToUInt32 (index, index_offset+4);
        entry.Offset        = LittleEndian.ToUInt32 (index, index_offset+8);
        entry.IsPacked      = is_compressed;
        if (0 != entry.Size)
        {
            if (entry.Offset < data_offset || !entry.CheckPlacement (m_file.MaxOffset))
                return null;
        }
        dir.Add (entry);
        index_offset += 12;
    }
    return dir;
}
```

#### DecryptIndex

```csharp
internal static void DecryptIndex (byte[] data, string key) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] += (byte)key[i % key.Length];
    }
}
```

#### GuessScheme

```csharp
public EncryptionScheme GuessScheme (int index_offset, int[] possible_name_sizes) {
    byte[] first_entry = new byte[possible_name_sizes[0] + 12];
    if (first_entry.Length != m_file.View.Read (index_offset, first_entry, 0, (uint)first_entry.Length))
        return null;
    byte[] key_bits = new byte[4];
    byte[] actual_offset = new byte[4];
    foreach (var name_length in possible_name_sizes)
    {
        int first_offset = index_offset + m_count * (name_length + 12);
        if (first_offset >= m_file.MaxOffset)
            continue;
        LittleEndian.Pack (first_offset, actual_offset, 0);
        int i;
        for (i = 0; i < 4; ++i)
        {
            key_bits[i] = (byte)(first_entry[name_length+8+i] - actual_offset[i]);
        }

        int first_match = ReverseFind (first_entry, name_length-4, key_bits);
        if (first_match < 4)
            continue;
        int second_match = ReverseFind (first_entry, first_match-4, key_bits);
        if (second_match <= 0)
            continue;
        int key_length = first_match - second_match;
        byte[] key = new byte[key_length];
        for (i = 0; i < key_length; ++i)
        {
            byte sym = (byte)-first_entry[second_match+i];
            if (sym < 0x21 || sym > 0x7E)
                break;
            key[(second_match+i) % key_length] = sym;
        }
        if (i == key_length)
            return new EncryptionScheme (Encoding.ASCII.GetString (key), name_length, index_offset);
    }
    return null;
}
```

#### ReverseFind

```csharp
static int ReverseFind (byte[] array, int pos, byte[] pattern) {
    int pattern_end_pos = pattern.Length-1;
    int pattern_pos = pattern_end_pos;
    for (int i = pos + pattern_pos; i >= 0; --i)
    {
        if (array[i] == pattern[pattern_pos])
        {
            if (0 == pattern_pos)
                return i;
            --pattern_pos;
        }
        else if (pattern_end_pos != pattern_pos)
        {
            i += pattern_end_pos - pattern_pos;
            pattern_pos = pattern_end_pos;
        }
    }
    return -1;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/RPM/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
