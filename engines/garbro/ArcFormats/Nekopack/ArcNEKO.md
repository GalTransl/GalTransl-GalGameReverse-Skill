# Nekopack / ArcNEKO：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NEKOPACK/1` / `GameRes.Formats.Neko.Pak1Opener` | `dat` | `4e454b4f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IndexReader.Parse` | `uint name_hash = m_input.ReadUInt32();` |
| `IndexReader.Parse` | `uint size = m_input.ReadUInt32();` |
| `Pak1Opener.TryOpen` | `if (!file.View.AsciiEqual (4, "PACK"))` |
| `Pak1Opener.TryOpen` | `int length = file.View.ReadInt32 (0x14);` |
| `Pak1Opener.TryOpen` | `uint seed = file.View.ReadUInt32 (8);` |
| `Pak1Opener.TryOpen` | `uint hash = LittleEndian.ToUInt32 (buffer, 0);` |
| `Pak1Opener.TryOpen` | `return LittleEndian.ToUInt32 (buffer, 8);` |
| `Pak1Opener.ReadBlock` | `uint hash = view.ReadUInt32 (offset);` |
| `Pak1Opener.ReadBlock` | `length = view.ReadInt32 (offset+4);` |
| `NekoEncryption32bit.ReadDir` | `Hash      = input.ReadUInt32(),` |
| `NekoEncryption32bit.ReadDir` | `FileCount = input.ReadInt32()` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Neko.DirRecord

#### 状态与常量

```csharp
public uint Hash ;

public int  FileCount ;
```

### GameRes.Formats.Neko.IndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

int             m_index_size ;

long            m_max_offset ;

INekoFormat     m_format ;

static string[] s_known_dir_names = {
    "image/actor", "image/back", "image/mask", "image/visual", "image/actor/big",
    "image/face", "image/actor/b", "image/actor/bb", "image/actor/s", "image/actor/ss",
    "sound/bgm", "sound/env", "sound/se", "sound/bgv", "voice", "script", "system", "count",
}

static Lazy<string[]> s_known_file_names = new Lazy<string[]> (ReadNekoPackLst) ;

bool _disposed = false ;
```

#### IndexReader

```csharp
public IndexReader (ArcView file, INekoFormat enc, byte[] index, int index_size) {
    m_input = new BinMemoryStream (index, 0, index_size, file.Name);
    m_index_size = index_size;
    m_max_offset = file.MaxOffset;
    m_format = enc;
}
```

#### Parse

```csharp
public List<Entry> Parse (long current_offset) {
    var names_map = GetNamesMap (KnownDirNames);
    var files_map = GetNamesMap (KnownFileNames);

    var dir = new List<Entry>();
    while (m_input.Position < m_index_size)
    {
        var dir_info = m_format.ReadDir (m_input);
        string dir_name;
        if (!names_map.TryGetValue (dir_info.Hash, out dir_name))
            dir_name = dir_info.Hash.ToString ("X8");
        dir.Capacity = dir.Count + dir_info.FileCount;
        for (int i = 0; i < dir_info.FileCount; ++i)
        {
            uint name_hash = m_input.ReadUInt32();
            uint size = m_input.ReadUInt32();
            string file_name;
            string type = "";
            if (!files_map.TryGetValue (name_hash, out file_name))
                file_name = name_hash.ToString ("X8");
            else
                type = FormatCatalog.Instance.GetTypeFromName (file_name);
            var entry = new Entry
            {
                Name = string.Format ("{0}/{1}", dir_name, file_name),
                Type = type,
                Offset = current_offset,
                Size = size,
            };
            if (!entry.CheckPlacement (m_max_offset))
                return null;
            dir.Add (entry);
            current_offset = m_format.NextOffset (entry);
        }
    }
    return dir.Count > 0 ? dir : null;
}
```

#### GetNamesMap

```csharp
IDictionary<uint, string> GetNamesMap (string[] known_names) {
    var map = new Dictionary<uint, string> (known_names.Length);
    var buffer = new byte[0x100];
    foreach (var name in known_names)
    {
        int length = Encodings.cp932.GetBytes (name, 0, name.Length, buffer, 0);
        uint hash = m_format.HashFromName (buffer, 0, length);
        if (!map.ContainsKey (hash))
            map[hash] = name;
        else if (!map[hash].Equals (name, StringComparison.InvariantCultureIgnoreCase))
            Trace.WriteLine (string.Format ("{0}: hash collision with {1} [{2:X8}]", name, map[hash], hash),
                             "[NEKOPACK]");
    }
    return map;
}
```

#### DetectTypes

```csharp
public void DetectTypes (IEnumerable<Entry> dir, Func<Entry, uint> get_signature) {
    foreach (var entry in dir.Where (e => string.IsNullOrEmpty (e.Type)))
    {
        if (entry.Name.HasAnyOfExtensions ("txt", "nut"))
        {
            entry.Type = "script";
            continue;
        }
        uint signature = get_signature (entry);
        var res = AutoEntry.DetectFileType (signature);
        if (res != null)
            entry.ChangeType (res);
        else if (entry.Name.StartsWith ("script/"))
            entry.Type = "script";
    }
}
```

#### ReadNekoPackLst

```csharp
static string[] ReadNekoPackLst () {
    try
    {
        var names = new List<string>();
        FormatCatalog.Instance.ReadFileList (name_list_parameter, name => names.Add (name));
        return names.ToArray();
    }
    catch (Exception X)
    {
        Trace.WriteLine (X.Message, "[NEKOPACK]");
        return new string[0];
    }
}
```

### GameRes.Formats.Neko.NekoArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly INekoFormat Decoder ;
```

#### NekoArchive

```csharp
public NekoArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, INekoFormat decoder)
    : base (arc, impl, dir) {
    Decoder = decoder;
}
```

### GameRes.Formats.Neko.Pak1Opener

继承/接口：`ArchiveFormat`。

#### Pak1Opener

```csharp
public Pak1Opener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "PACK"))
        return null;
    int length = file.View.ReadInt32 (0x14);
    if (length < 0x10 || length >= file.MaxOffset)
        return null;
    uint seed = file.View.ReadUInt32 (8);
    var dec = new NekoEncryption32bit (seed);
    byte[] index = ReadBlock (file.View, dec, 0x10, out length);

    using (var reader = new IndexReader (file, dec, index, length))
    {
        var dir = reader.Parse (0x18+length);
        if (null == dir)
            return null;
        byte[] buffer = new byte[0x10];
        reader.DetectTypes (dir, entry => {
            file.View.Read (entry.Offset, buffer, 0, 0x10);
            uint hash = LittleEndian.ToUInt32 (buffer, 0);
            if (0 != hash)
                dec.Decrypt (hash, buffer, 8, 8);
            return LittleEndian.ToUInt32 (buffer, 8);
        });
        return new NekoArchive (file, this, dir, dec);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pak = arc as NekoArchive;
    if (null == pak)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    int length;
    var data = ReadBlock (arc.File.View, pak.Decoder, entry.Offset, out length);
    return new BinMemoryStream (data, 0, length, entry.Name);
}
```

#### HashFromString

```csharp
static uint HashFromString (uint seed, byte[] str, int offset, int length) {

    uint result = seed;
    for (int i = 0; i < length; ++i)
    {
        byte c = str[offset+i];
        result += c + result * 37;
    }
    return result;
}
```

#### CalcParity

```csharp
static uint CalcParity (uint a1, uint a2) {
    uint v1 = (a2 ^ ((a2 ^ ((a2 ^ ((a2 ^ a1) + 1566083941u)) - 899497514u)) - 1894007588u)) + 1812433253u;
    int v2 = (int)(((a2 ^ ((a2 ^ a1) + 1566083941u)) - 899497514u) >> 27);
    return v1 << v2 | v1 >> (32-v2);
}
```

#### ReadBlock

```csharp
static byte[] ReadBlock (ArcView.Frame view, INekoFormat enc, long offset, out int length) {
    uint hash = view.ReadUInt32 (offset);
    length = view.ReadInt32 (offset+4);

    int aligned_size = (length+7) & ~7;
    byte[] buffer = new byte[aligned_size];
    length = view.Read (offset+8, buffer, 0, (uint)length);
    if (0 != hash)
    {
        enc.Decrypt (hash, buffer, 0, aligned_size);
    }
    return buffer;
}
```

### GameRes.Formats.Neko.NekoEncryption32bit

继承/接口：`INekoFormat`。

#### 状态与常量

```csharp
readonly uint m_seed ;

static readonly byte[] ShiftMap = new byte[] {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x38, 0x2F, 0x33, 0x3C, 0x40, 0x3B, 0x2A, 0x2E, 0x31, 0x30, 0x26, 0x44, 0x35, 0x28, 0x3E, 0x12,
    0x02, 0x22, 0x06, 0x20, 0x1A, 0x1C, 0x0F, 0x11, 0x18, 0x17, 0x42, 0x2B, 0x3A, 0x37, 0x34, 0x0C,
    0x41, 0x08, 0x1D, 0x07, 0x15, 0x21, 0x05, 0x1E, 0x0A, 0x14, 0x0E, 0x10, 0x09, 0x27, 0x1F, 0x0B,
    0x23, 0x16, 0x0D, 0x01, 0x25, 0x04, 0x1B, 0x03, 0x13, 0x24, 0x19, 0x2D, 0x12, 0x29, 0x32, 0x3F,
    0x3D, 0x08, 0x1D, 0x07, 0x15, 0x21, 0x05, 0x1E, 0x0A, 0x14, 0x0E, 0x10, 0x09, 0x27, 0x1F, 0x0B,
    0x23, 0x16, 0x0D, 0x01, 0x25, 0x04, 0x1B, 0x03, 0x13, 0x24, 0x19, 0x2C, 0x39, 0x43, 0x36, 0x00,
    0x4B, 0xA9, 0xA7, 0xAF, 0x50, 0x52, 0x91, 0x9F, 0x47, 0x6B, 0x96, 0xAB, 0x87, 0xB5, 0x9B, 0xBB,
    0x99, 0xA4, 0xBF, 0x5C, 0xC6, 0x9C, 0xC2, 0xC4, 0xB6, 0x4F, 0xB8, 0xC1, 0x85, 0xA8, 0x51, 0x7E,
    0x5F, 0x82, 0x73, 0xC7, 0x90, 0x4E, 0x45, 0xA5, 0x7A, 0x63, 0x70, 0xB3, 0x79, 0x83, 0x60, 0x55,
    0x5B, 0x5E, 0x68, 0xBA, 0x53, 0xA1, 0x67, 0x97, 0xAC, 0x71, 0x81, 0x59, 0x64, 0x7C, 0x9D, 0xBD,
    0x9D, 0xBD, 0x95, 0xA0, 0xB2, 0xC0, 0x6F, 0x6A, 0x54, 0xB9, 0x6D, 0x88, 0x77, 0x48, 0x5D, 0x72,
    0x49, 0x93, 0x57, 0x65, 0xBE, 0x4A, 0x80, 0xA2, 0x5A, 0x98, 0xA6, 0x62, 0x7F, 0x84, 0x75, 0xBC,
    0xAD, 0xB1, 0x6E, 0x76, 0x8B, 0x9E, 0x8C, 0x61, 0x69, 0x8D, 0xB4, 0x78, 0xAA, 0xAE, 0x8F, 0xC3,
    0x58, 0xC5, 0x74, 0xB7, 0x8E, 0x7D, 0x89, 0x8A, 0x56, 0x4D, 0x86, 0x94, 0x9A, 0x4C, 0x92, 0xB0,
}
```

#### NekoEncryption32bit

```csharp
public NekoEncryption32bit (uint seed) {
    m_seed = seed;
}
```

#### Decrypt

```csharp
public void Decrypt (uint hash, byte[] buf, int offset, int length) {
    if (offset < 0 || offset > buf.Length)
        throw new ArgumentException ("offset");
    int count = Math.Min (length, buf.Length-offset) / 8;
    if (0 == count)
        return;
    ulong key = KeyFromHash (hash);
    unsafe
    {
        fixed (byte* data = buf)
        {
            ulong* first = (ulong*)(data + offset);
            ulong* last = first + count;
            while (first != last)
            {
                ulong v = *first ^ key;
                key = MMX.PAddW (key, v);
                *first++ = v;
            }
        }
    }
}
```

#### HashFromName

```csharp
public uint HashFromName (byte[] str, int offset, int length) {

    uint hash = m_seed;
    for (int i = 0; i < length; ++i)
    {
        byte c = str[offset+i];
        hash = 81 * (ShiftMap[c] ^ hash);
    }
    return hash;
}
```

#### ReadDir

```csharp
public DirRecord ReadDir (IBinaryStream input) {
    return new DirRecord {
        Hash      = input.ReadUInt32(),
        FileCount = input.ReadInt32()
    };
}
```

#### NextOffset

```csharp
public long NextOffset (Entry entry) {
    return entry.Offset + entry.Size + 8;
}
```

#### KeyFromHash

```csharp
public static ulong KeyFromHash (uint hash) {
    uint v2 = hash ^ (hash + 1566083941u);
    uint v3 = v2 ^ (hash - 899497514u);
    ulong result = v3 ^ (v2 - 1894007588u);
    return result | (result ^ (v3 + 1812433253u)) << 32;
}
```

## 配套算法与外部条件

- [ArcFormats/ArcCommon.cs](../ArcCommon.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Nekopack/ArcNEKO.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
