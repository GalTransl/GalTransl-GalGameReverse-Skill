# YuRis / ArcYPF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `YPF` / `GameRes.Formats.YuRis.YpfOpener` | `ypf` | `59504600`, `4d5a9000` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `YpfOpener.TryOpen` | `if (file.View.AsciiEqual (0, "MZ"))` |
| `YpfOpener.TryOpen` | `if (!file.View.AsciiEqual (ypf_offset, "YPF\0"))` |
| `YpfOpener.TryOpen` | `uint version  = file.View.ReadUInt32 (ypf_offset+4);` |
| `YpfOpener.TryOpen` | `int count     = file.View.ReadInt32 (ypf_offset+8);` |
| `YpfOpener.TryOpen` | `uint dir_size = file.View.ReadUInt32 (ypf_offset+12);` |
| `YpfOpener.OpenEntry` | `if (Binary.AsciiEqual (data, 0, "YSTB"))` |
| `YpfOpener.FindYser` | `uint header_size = file.View.ReadUInt32 (offset+4);` |
| `Parser.ScanDir` | `uint name_size = DecryptLength (scheme.SwapTable, (byte)(m_file.View.ReadByte (dir_offset+4) ^ 0xff));` |
| `Parser.ScanDir` | `byte[] raw_name = m_file.View.ReadBytes (dir_offset, name_size);` |
| `Parser.ScanDir` | `int type_id = m_file.View.ReadByte (dir_offset);` |
| `Parser.ScanDir` | `entry.IsPacked      = 0 != m_file.View.ReadByte (dir_offset+1);` |
| `Parser.ScanDir` | `entry.UnpackedSize  = m_file.View.ReadUInt32 (dir_offset+2);` |
| `Parser.ScanDir` | `entry.Size          = m_file.View.ReadUInt32 (dir_offset+6);` |
| `Parser.ScanDir` | `entry.Offset        = m_file.View.ReadUInt32 (dir_offset+10) + base_offset;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum YpfCompression
    {
        Zlib = 0,
        Snappy = 1,
    }
```

### GameRes.Formats.YuRis.YpfOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public uint      Key { get; set; }

public uint  Version { get; set; }
```

### GameRes.Formats.YuRis.YpfScheme

#### 状态与常量

```csharp
public byte[]   SwapTable ;

public byte     Key ;

public bool     GuessKey ;

public uint     ExtraHeaderSize ;

public uint     ScriptKey ;

public YpfCompression CompressType ;
```

#### YpfScheme

```csharp
public YpfScheme (byte[] swap_table, byte key, uint script_key = 0) {
    SwapTable = swap_table;
    Key = key;
    GuessKey = false;
    ExtraHeaderSize = 0;
    ScriptKey = script_key;
    CompressType = YpfCompression.Zlib;
}
```

#### YpfScheme

```csharp
public YpfScheme (byte[] swap_table) {
    SwapTable = swap_table;
    GuessKey = true;
    ExtraHeaderSize = 0;
    CompressType = YpfCompression.Zlib;
}
```

### GameRes.Formats.YuRis.YpfArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public uint     ScriptKey ;

public YpfCompression CompressType ;
```

#### YpfArchive

```csharp
public YpfArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint script_key)
    : base (arc, impl, dir) {
    ScriptKey = script_key;
}
```

#### YpfArchive

```csharp
public YpfArchive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint script_key, YpfCompression compress_type)
    : base(arc, impl, dir) {
    ScriptKey = script_key;
    CompressType = compress_type;
}
```

### GameRes.Formats.YuRis.YpfOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static YuRisScheme DefaultScheme = new YuRisScheme { KnownSchemes = new Dictionary<string, YpfScheme>() }

static public byte[] SwapTable00 = {
    0x03, 0x48, 0x06, 0x35,
    0x0C, 0x10, 0x11, 0x19, 0x1C, 0x1E,
    0x09, 0x0B, 0x0D, 0x13, 0x15, 0x1B, 0x20, 0x23, 0x26, 0x29, 0x2C, 0x2F, 0x2E, 0x32,
}

static public byte[] SwapTable04 = {
    0x0C, 0x10, 0x11, 0x19, 0x1C, 0x1E,
    0x09, 0x0B, 0x0D, 0x13, 0x15, 0x1B, 0x20, 0x23, 0x26, 0x29, 0x2C, 0x2F, 0x2E, 0x32,
}

static public byte[] SwapTable10 = {
    0x09, 0x0B, 0x0D, 0x13, 0x15, 0x1B, 0x20, 0x23, 0x26, 0x29, 0x2C, 0x2F, 0x2E, 0x32,
}
```

#### YpfOpener

```csharp
public YpfOpener () {
    Signatures = new uint[] { 0x00465059, 0x00905A4D, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long ypf_offset = 0;
    if (file.View.AsciiEqual (0, "MZ"))
    {
        ypf_offset = FindYser (file);
    }
    if (!file.View.AsciiEqual (ypf_offset, "YPF\0"))
        return null;

    uint version  = file.View.ReadUInt32 (ypf_offset+4);
    int count     = file.View.ReadInt32 (ypf_offset+8);
    uint dir_size = file.View.ReadUInt32 (ypf_offset+12);
    if (!IsSaneCount (count) || dir_size < count * 0x17)
        return null;
    if (dir_size > file.View.Reserve (ypf_offset+0x20, dir_size))
        return null;
    var parser = new Parser (file, version, count, dir_size);

    var scheme = QueryEncryptionScheme (file.Name, version);
    var dir = parser.ScanDir (scheme, ypf_offset);
    if (null == dir || 0 == dir.Count)
        return null;

    if (scheme.ScriptKey != 0)
        return new YpfArchive (file, this, dir, scheme.ScriptKey, scheme.CompressType);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var packed_entry = entry as PackedEntry;
    var ypf = arc as YpfArchive;
    Stream input = base.OpenEntry (arc, entry);
    if (null != packed_entry && packed_entry.IsPacked)
    {
        if(ypf == null)
        {
            input = new ZLibStream(input, CompressionMode.Decompress);
        }
        else
        {
            switch (ypf.CompressType)
            {
                case YpfCompression.Snappy:
                {
                    var compress_data = new byte[entry.Size];
                    input.Read(compress_data, 0, compress_data.Length);
                    var decompress_data = Snappier.Snappy.DecompressToArray (compress_data);
                    input = new BinMemoryStream(decompress_data, entry.Name);
                    break;
                }
                case YpfCompression.Zlib:
                default:
                {
                    input = new ZLibStream(input, CompressionMode.Decompress);
                    break;
                }
            }
        }
    }
    uint unpacked_size = null == packed_entry ? entry.Size : packed_entry.UnpackedSize;
    if (null == ypf || 0 == ypf.ScriptKey || unpacked_size <= 0x20
        || !entry.Name.HasExtension (".ybn"))
        return input;
    using (input)
    {
        var data = new byte[unpacked_size];
        input.Read (data, 0, data.Length);
        if (Binary.AsciiEqual (data, 0, "YSTB"))
            DecryptYstb (data, ypf.ScriptKey);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### QueryEncryptionScheme

```csharp
YpfScheme QueryEncryptionScheme (string arc_name, uint version) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (string.IsNullOrEmpty (title))
        title = FormatCatalog.Instance.LookupGame (arc_name, @"..\*.exe");
    YpfScheme scheme;
    if (!string.IsNullOrEmpty (title) && KnownSchemes.TryGetValue (title, out scheme))
        return scheme;
    var options = Query<YpfOptions> (arcStrings.YPFNotice);
    if (!KnownSchemes.TryGetValue (options.Scheme, out scheme) || null == scheme)
        scheme = new YpfScheme {
            SwapTable   = GuessSwapTable (version),
            GuessKey    = true,
            ExtraHeaderSize = version >= 0x1D9 ? 4u : version == 0xDE ? 8u : 0u,
        };
    return scheme;
}
```

#### FindYser

```csharp
internal long FindYser (ArcView file) {
    var exe = new ExeFile (file);
    var offset = exe.FindAsciiString (exe.Overlay, "YSER", 0x10);
    if (-1 == offset)
        return 0;
    uint header_size = file.View.ReadUInt32 (offset+4);
    return offset + header_size;
}
```

#### ChecksumFunc

```csharp
delegate uint ChecksumFunc (byte[] data) ;
```

#### GetFileType

```csharp
static byte GetFileType (uint version, string name) {

    string ext = Path.GetExtension (name).TrimStart ('.').ToLower();
    if ("ybn" == ext) return 0;
    if ("bmp" == ext) return 1;
    if ("png" == ext) return 2;
    if ("jpg" == ext || "jpeg" == ext) return 3;
    if ("gif" == ext) return 4;
    if ("avi" == ext && 0xf7 == version) return 5;
    if ("ycg" == ext) return 8;
    if ("psb" == ext) return 9;
    byte type = 0;
    if ("wav" == ext) type = 5;
    else if ("ogg" == ext) type = 6;
    else if ("psd" == ext) type = 7;
    if (0xf7 == version && 0 != type)
        ++type;
    return type;
}
```

#### GuessSwapTable

```csharp
byte[] GuessSwapTable (uint version) {
    if (0x1F4 == version)
    {
        YpfScheme scheme;
        if (KnownSchemes.TryGetValue ("Unionism Quartet", out scheme))
            return scheme.SwapTable;
    }
    if (version < 0x100)
        return SwapTable04;
    else if (version >= 0x12c && version < 0x196)
        return SwapTable10;
    else
        return SwapTable00;
}
```

#### DecryptYstb

```csharp
unsafe void DecryptYstb (byte[] data, uint key) {
    if (data.Length <= 0x20)
        return;
    fixed (byte* raw = data)
    {
        uint* header = (uint*)raw;
        uint version = header[1];
        int first_item, last_item;
        if (version >= 0x1CB || 0x12C == version || 0x19A == version || 0x1C3 == version || 0x19C == version || 0x198 == version)
        {
            first_item = 3;
            last_item = 7;
        }
        else
        {
            first_item = 2;
            last_item = 4;
        }
        uint total = 0x20;

        for (int i = first_item; i < last_item; ++i)
        {
            if (header[i] >= data.Length)
                return;
            total += header[i];
            if (total > data.Length)
                return;
        }
        if (total != data.Length)
            return;
        byte* data8 = raw+0x20;
        for (int i = first_item; i < last_item; ++i)
        {
            uint size = header[i];
            if (0 == size)
                continue;
            uint* data32 = (uint*)data8;
            for (uint j = size / 4; j != 0; --j)
                *data32++ ^= key;
            data8 = (byte*)data32;
            uint k = key;
            for (uint j = size & 3; j != 0; --j)
            {
                *data8++ ^= (byte)k;
                k >>= 8;
            }
        }
    }
}
```

### GameRes.Formats.YuRis.YpfOpener.Parser

#### 状态与常量

```csharp
ArcView m_file ;

uint    m_version ;

int     m_count ;

uint    m_dir_size ;
```

#### Parser

```csharp
public Parser (ArcView file, uint version, int count, uint dir_size) {
    m_file = file;
    m_count = count;
    m_dir_size = dir_size;
    m_version = version;
}
```

#### ScanDir

```csharp
public List<Entry> ScanDir (YpfScheme scheme, long base_offset = 0) {
    long dir_offset = base_offset + 0x20;
    uint dir_remaining = m_dir_size;
    var dir = new List<Entry> (m_count);
    byte key = scheme.Key;
    bool guess_key = scheme.GuessKey;
    uint extra_size = 0x12 + scheme.ExtraHeaderSize;
    for (int num = 0; num < m_count; ++num)
    {
        if (dir_remaining < 5+extra_size)
            return null;
        dir_remaining -= 5+extra_size;

        uint name_size = DecryptLength (scheme.SwapTable, (byte)(m_file.View.ReadByte (dir_offset+4) ^ 0xff));
        if (name_size > dir_remaining)
            return null;
        dir_remaining -= name_size;
        dir_offset += 5;
        if (0 == name_size)
            return null;
        byte[] raw_name = m_file.View.ReadBytes (dir_offset, name_size);
        dir_offset += name_size;
        for (int ext_size = 4; ext_size <= 5; ++ext_size)
        {
            if (!guess_key || name_size < ext_size)
                break;
            key = (byte)(raw_name[name_size - ext_size] ^ '.');
            int c = 1;
            for (; c < ext_size; ++c)
            {
                char t = (char)(raw_name[name_size - c] ^ key);
                if (!char.IsLetter (t))
                    break;
            }
            if (c == ext_size)
                guess_key = false;
        }
        if (guess_key)
            return null;
        for (uint i = 0; i < name_size; ++i)
        {
            raw_name[i] ^= key;
        }
        string name = Encodings.cp932.GetString (raw_name);

        int type_id = m_file.View.ReadByte (dir_offset);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        if (string.IsNullOrEmpty (entry.Type))
        {
            switch (type_id)
            {
            case 0:
                entry.Type = "script";
                break;
            case 1: case 2: case 3: case 4: case 8:
                entry.Type = "image";
                break;
            case 5:
                entry.Type = 0xf7 == m_version ? "video" : "audio";
                break;
            case 6:
                entry.Type = "audio";
                break;
            case 7:
                entry.Type = 0xf7 == m_version ? "audio" : "image";
                break;
            }
        }
        entry.IsPacked      = 0 != m_file.View.ReadByte (dir_offset+1);
        entry.UnpackedSize  = m_file.View.ReadUInt32 (dir_offset+2);
        entry.Size          = m_file.View.ReadUInt32 (dir_offset+6);
        entry.Offset        = m_file.View.ReadUInt32 (dir_offset+10) + base_offset;
        if (entry.CheckPlacement (m_file.MaxOffset))
            dir.Add (entry);
        dir_offset += extra_size;
    }
    return dir;
}
```

#### DecryptLength

```csharp
static public byte DecryptLength (byte[] swap_table, byte value) {
    int pos = Array.IndexOf (swap_table, value);
    if (-1 == pos)
        return value;
    if (0 != (pos & 1))
        return swap_table[pos-1];
    else
        return swap_table[pos+1];
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/YuRis/ArcYPF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
