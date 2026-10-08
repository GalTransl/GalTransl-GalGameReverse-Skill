# TanukiSoft / ArcTAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `TAC` / `GameRes.Formats.Tanuki.TacOpener` | `tac`, `stx` | `54417263` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `TacOpener.TryOpen` | `if (file.View.AsciiEqual (4, "1.00"))` |
| `TacOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "1.10"))` |
| `TacOpener.TryOpen` | `else if (file.View.AsciiEqual (4, "1.20"))` |
| `TacOpener.TryOpen` | `int count = file.View.ReadInt32 (0x14);` |
| `TacOpener.TryOpen` | `int bucket_count = file.View.ReadInt32 (0x18);` |
| `TacOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0x1C);` |
| `TacOpener.TryOpen` | `uint arc_seed = file.View.ReadUInt32 (0x20);` |
| `TacOpener.TryOpen` | `index_offset = 0x30 + file.View.ReadUInt32 (0x2C);` |
| `TacOpener.TryOpen` | `var packed_bytes = file.View.ReadBytes (index_offset, index_size);` |
| `TacOpener.TryOpen` | `entry.Hash = index.ReadUInt16();` |
| `TacOpener.TryOpen` | `entry.Count = index.ReadUInt16();` |
| `TacOpener.TryOpen` | `entry.Index = index.ReadInt32();` |
| `TacOpener.TryOpen` | `entry.Hash = index.ReadUInt64();` |
| `TacOpener.TryOpen` | `entry.IsPacked = index.ReadInt32() != 0;` |
| `TacOpener.TryOpen` | `entry.UnpackedSize = index.ReadUInt32();` |
| `TacOpener.TryOpen` | `entry.Offset = base_offset + index.ReadUInt32();` |
| `TacOpener.TryOpen` | `entry.Size = index.ReadUInt32();` |
| `TacOpener.TryOpen` | `var res = AutoEntry.DetectFileType (buffer.ToUInt32 (0));` |
| `TacOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (tent.Offset, tent.EncryptedSize);` |
| `TacOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (tent.Offset, tent.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tanuki.TacOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] IndexKey = Encoding.ASCII.GetBytes ("TLibArchiveData") ;

static readonly string ListFileName = name_list_parameter ;

static Lazy<string[]> s_known_file_names = new Lazy<string[]> (ReadTanukiLst) ;
```

#### TacOpener

```csharp
public TacOpener () {
    Extensions = new string[] { "tac", "stx" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version;
    if (file.View.AsciiEqual (4, "1.00"))
        version = 100;
    else if (file.View.AsciiEqual (4, "1.10"))
        version = 110;
    else if (file.View.AsciiEqual (4, "1.20"))
        version = 120;
    else
        return null;
    int count = file.View.ReadInt32 (0x14);
    if (!IsSaneCount (count))
        return null;

    int bucket_count = file.View.ReadInt32 (0x18);
    uint index_size = file.View.ReadUInt32 (0x1C);
    uint arc_seed = file.View.ReadUInt32 (0x20);
    long index_offset = 0;
    switch (version)
    {
        case 100:
            index_offset = 0x24;
            break;
        case 110:
            index_offset = 0x2C;
            break;
        case 120:
            index_offset = 0x30 + file.View.ReadUInt32 (0x2C);
            break;
    };
    long base_offset = index_offset + index_size;
    var blowfish = new Blowfish (IndexKey);
    var packed_bytes = file.View.ReadBytes (index_offset, index_size);
    blowfish.Decipher (packed_bytes, packed_bytes.Length & ~7);

    using (var input = new MemoryStream (packed_bytes))
    using (var unpacked = new ZLibStream (input, CompressionMode.Decompress))
    using (var index = new BinaryReader (unpacked))
    {
        var file_map = BuildFileNameMap (arc_seed);
        var dir_table = new List<TacBucket> (bucket_count);
        for (int i = 0; i < bucket_count; ++i)
        {
            var entry = new TacBucket();
            entry.Hash = index.ReadUInt16();
            entry.Count = index.ReadUInt16();
            entry.Index = index.ReadInt32();
            dir_table.Add (entry);
        }
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var entry = new TacEntry();
            entry.Hash = index.ReadUInt64();
            entry.IsPacked = index.ReadInt32() != 0;
            entry.UnpackedSize = index.ReadUInt32();
            entry.Offset = base_offset + index.ReadUInt32();
            entry.Size = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        var buffer = new byte[8];
        foreach (var bucket in dir_table)
        {
            for (int i = 0; i < bucket.Count; ++i)
            {
                var entry = dir[bucket.Index+i] as TacEntry;
                entry.Hash = entry.Hash << 16 | bucket.Hash;
                bool known_name = file_map.ContainsKey (entry.Hash);
                if (known_name)
                {
                    entry.Name = file_map[entry.Hash];
                    entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
                }
                else
                {
                    entry.Name = string.Format ("{0:X16}", entry.Hash);
                }
                if (entry.IsPacked)
                    continue;
                entry.Key = Encoding.ASCII.GetBytes (string.Format ("{0}_tlib_secure_", entry.Hash));
                if (!known_name)
                {
                    var bf = new Blowfish (entry.Key);
                    file.View.Read (entry.Offset, buffer, 0, 8);
                    bf.Decipher (buffer, 8);
                    var res = AutoEntry.DetectFileType (buffer.ToUInt32 (0));
                    if (res != null)
                        entry.ChangeType (res);
                }
                if ("image" == entry.Type && !entry.Name.HasExtension (".af"))
                    entry.EncryptedSize = Math.Min (10240, entry.Size);
                else
                    entry.EncryptedSize = entry.Size;
            }
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var tent = entry as TacEntry;
    if (null == tent)
        return base.OpenEntry (arc, entry);
    if (tent.IsPacked)
    {
        var input = arc.File.CreateStream (entry.Offset, entry.Size);
        return new ZLibStream (input, CompressionMode.Decompress);
    }
    var bf = new Blowfish (tent.Key);
    if (tent.EncryptedSize < tent.Size)
    {
        var header = arc.File.View.ReadBytes (tent.Offset, tent.EncryptedSize);
        bf.Decipher (header, header.Length);
        var rest = arc.File.CreateStream (tent.Offset+tent.EncryptedSize, tent.Size-tent.EncryptedSize);
        return new PrefixStream (header, rest);
    }
    else if (0 == (tent.Size & 7))
    {
        var input = arc.File.CreateStream (tent.Offset, tent.Size);
        return new InputCryptoStream (input, bf.CreateDecryptor());
    }
    else
    {
        var data = arc.File.View.ReadBytes (tent.Offset, tent.Size);
        bf.Decipher (data, data.Length & ~7);
        return new BinMemoryStream (data);
    }
}
```

#### HashFromString

```csharp
internal static ulong HashFromString (string s, uint seed) {
    s = s.Replace ('\\', '/').ToUpperInvariant();
    var bytes = Encodings.cp932.GetBytes (s);
    ulong hash = 0;
    for (int i = 0; i < bytes.Length; ++i)
    {
        hash = bytes[i] + 0x19919 * hash + seed;
    }
    return hash;
}
```

#### HashFromAsciiString

```csharp
internal static ulong HashFromAsciiString (string s, uint seed) {
    ulong hash = 0;
    for (int i = 0; i < s.Length; ++i)
    {
        hash = (uint)char.ToUpperInvariant (s[i]) + 0x19919 * hash + seed;
    }
    return hash;
}
```

#### BuildFileNameMap

```csharp
Dictionary<ulong, string> BuildFileNameMap (uint seed) {
    var map = new Dictionary<ulong, string> (KnownNames.Length);
    foreach (var name in KnownNames)
    {
        map[HashFromAsciiString (name, seed)] = name;
    }
    return map;
}
```

#### ReadTanukiLst

```csharp
static string[] ReadTanukiLst () {
    try
    {
        var names = new List<string>();
        FormatCatalog.Instance.ReadFileList (ListFileName, name => names.Add (name));
        return names.ToArray();
    }
    catch (Exception X)
    {
        System.Diagnostics.Trace.WriteLine (X.Message, "[TAC]");
        return new string[0];
    }
}
```

### GameRes.Formats.Tanuki.TacEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public ulong    Hash ;

public byte[]   Key ;

public uint     EncryptedSize ;
```

### GameRes.Formats.Tanuki.TacBucket

#### 状态与常量

```csharp
public ushort   Hash ;

public int      Count ;

public int      Index ;
```

## 配套算法与外部条件

- [ArcFormats/Blowfish.cs](../Blowfish.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/TanukiSoft/ArcTAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
