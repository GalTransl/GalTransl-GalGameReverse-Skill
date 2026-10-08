# Musica / ArcPAZ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAZ` / `GameRes.Formats.Musica.PazOpener` | `paz`, `dat` | `93848f85`, `9593888f`, `6564656e`, `86848f84`, `53746561`, `6d617368`, `83848092`, `7472696e`, `4253465f`, `65665f73`, `65665f66`, `796f7269`, `68616a69` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PazOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (0);` |
| `PazOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (start_offset);` |
| `PazOpener.TryOpen` | `int count = index.ReadInt32();` |
| `PazOpener.TryOpen` | `video_key = index.ReadBytes (scheme.MovKeyIs2D ? 0x10000 : 0x100);` |
| `PazOpener.TryOpen` | `var name = index.BaseStream.ReadCString();` |
| `PazOpener.TryOpen` | `entry.Offset    = index.ReadInt64();` |
| `PazOpener.TryOpen` | `entry.UnpackedSize = index.ReadUInt32();` |
| `PazOpener.TryOpen` | `entry.Size        = index.ReadUInt32();` |
| `PazOpener.TryOpen` | `entry.AlignedSize = index.ReadUInt32();` |
| `PazOpener.TryOpen` | `entry.IsPacked = index.ReadInt32 () != 0;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Musica.PazEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint     AlignedSize ;

public byte[]   Key ;
```

### GameRes.Formats.Musica.PazArchiveBase

继承/接口：`MultiFileArchive`。

#### 状态与常量

```csharp
public readonly int         Version ;

public readonly byte        XorKey ;
```

#### PazArchiveBase

```csharp
public PazArchiveBase (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version, byte key, IReadOnlyList<ArcView> parts = null)
    : base (arc, impl, dir, parts) {
    Version = version;
    XorKey = key;
}
```

#### GetEntrySize

```csharp
protected override uint GetEntrySize (Entry entry) {
    var pent = entry as PazEntry;
    if (pent != null)
        return pent.AlignedSize;
    else
        return entry.Size;
}
```

#### DecryptEntry

```csharp
internal abstract Stream DecryptEntry (Stream input, PazEntry entry) ;
```

### GameRes.Formats.Musica.PazArchive

继承/接口：`PazArchiveBase`。

#### 状态与常量

```csharp
public readonly Blowfish    Encryption ;
```

#### PazArchive

```csharp
public PazArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version, byte key, byte[] data_key, IReadOnlyList<ArcView> parts = null)
    : base (arc, impl, dir, version, key, parts) {
    Encryption = new Blowfish (data_key);
}
```

#### DecryptEntry

```csharp
internal override Stream DecryptEntry (Stream input, PazEntry entry) {
    input = new InputCryptoStream (input, Encryption.CreateDecryptor());
    var key = entry.Key;
    if (null == key)
        return input;
    var rc4 = new Rc4Transform (key);
    if (Version >= 2)
    {
        uint crc = Crc32.Compute (key, 0, key.Length);
        int skip_rounds = (int)(crc >> 12) & 0xFF;
        for (int i = 0; i < skip_rounds; ++i)
        {
            rc4.NextByte();
        }
    }
    return new InputCryptoStream (input, rc4);
}
```

### GameRes.Formats.Musica.MovPazArchive

继承/接口：`PazArchiveBase`。

#### 状态与常量

```csharp
public readonly byte[]  MovKey ;
```

#### MovPazArchive

```csharp
public MovPazArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version, byte key, byte[] mov_key, IReadOnlyList<ArcView> parts = null)
    : base (arc, impl, dir, version, key, parts) {
    MovKey = mov_key;
}
```

#### DecryptEntry

```csharp
internal override Stream DecryptEntry (Stream input, PazEntry entry) {
    if (Version < 1)
    {
        using (input)
        {
            var data = new byte[entry.AlignedSize];
            input.Read (data, 0, data.Length);
            for (int i = 0; i < data.Length; ++i)
                data[i] = MovKey[data[i]];
            return new BinMemoryStream (data, entry.Name);
        }
    }
    var key = new byte[0x100];
    for (int i = 0; i < 0x100; ++i)
        key[i] = (byte)(MovKey[i] ^ entry.Key[i % entry.Key.Length]);

    var rc4 = new Rc4Transform (key);
    var block = rc4.GenerateBlock ((int)Math.Min (0x10000, input.Length));
    return new ByteStringEncryptedStream (input, block);
}
```

### GameRes.Formats.Musica.MovTwoPazArchive

继承/接口：`PazArchiveBase`。

#### 状态与常量

```csharp
public readonly byte[,]  MovKey ;
```

#### MovTwoPazArchive

```csharp
public MovTwoPazArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version, byte key, byte[] mov_key, IReadOnlyList<ArcView> parts = null)
    : base (arc, impl, dir, version, key, parts) {
    MovKey = new byte[0x100, 0x100];
    for (int i = 0; i < 0x100; i++)
        for (int j = 0; j < 0x100; j++)
            MovKey[i, mov_key[i * 0x100 + j]] = (byte)j;
}
```

#### DecryptEntry

```csharp
internal override Stream DecryptEntry (Stream input, PazEntry entry) {
    using (input)
    {
        var data = new byte[entry.AlignedSize];
        input.Read (data, 0, data.Length);
        for (int i = 0; i < data.Length; ++i)
            data[i] = MovKey[(i >> 16) & 0xFF, data[i]];
        return new BinMemoryStream (data, entry.Name);
    }
}
```

### GameRes.Formats.Musica.PazOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ISet<string> AudioPazNames = new HashSet<string> {
    "bgm", "se", "voice", "pmbgm", "pmse", "pmvoice"
}

static readonly ISet<string> VideoPazNames = new HashSet<string> { "mov" }

MusicaScheme m_scheme = new MusicaScheme {
    KnownSchemes = new Dictionary<uint, PazScheme>(),
    KnownTitles = new Dictionary<string, PazScheme>()
}
```

#### PazOpener

```csharp
public PazOpener () {
    Extensions = new string[] { "paz", "dat" };
    Signatures = new uint[] {
        0x858F8493, 0x8F889395, 0x6E656465, 0x848F8486, 0x61657453, 0x6873616D, 0x92808483,
        0x6E697274, 0x5F465342, 0x735F6665, 0x665F6665, 0x69726F79, 0x696A6168, 0
    };
    ContainedFormats = new string[] { "PNG", "ANI/PAZ", "SQZ", "OGG", "WAV", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint signature = file.View.ReadUInt32 (0);
    var scheme = QueryEncryption (file.Name, signature);
    if (null == scheme)
        return null;
    uint start_offset = scheme.Version > 0 ? 0x20u : 0u;
    uint index_size = file.View.ReadUInt32 (start_offset);
    start_offset += 4;
    byte xor_key = (byte)(index_size >> 24);
    if (xor_key != 0)
        index_size ^= (uint)(xor_key << 24 | xor_key << 16 | xor_key << 8 | xor_key);
    if (0 != (index_size & 7) || index_size + start_offset >= file.MaxOffset)
        return null;

    var arc_list = new List<Entry>();
    var arc_dir = VFS.GetDirectoryName (file.Name);
    long max_offset = file.MaxOffset;
    for (char suffix = 'A'; suffix <= 'Z'; ++suffix)
    {
        var part_name = VFS.CombinePath (arc_dir, file.Name + suffix);
        if (!VFS.FileExists (part_name))
            break;
        var part = VFS.FindFile (part_name);
        arc_list.Add (part);
        max_offset += part.Size;
    }
    var arc_name = Path.GetFileNameWithoutExtension (file.Name).ToLowerInvariant();
    bool is_audio = AudioPazNames.Contains (arc_name);
    bool is_video = VideoPazNames.Contains (arc_name);
    Stream input = file.CreateStream (start_offset, index_size);
    byte[] video_key = null;
    List<Entry> dir;
    try
    {
        if (xor_key != 0)
            input = new XoredStream (input, xor_key);
        var enc = new Blowfish (scheme.ArcKeys[arc_name].IndexKey);
        input = new InputCryptoStream (input, enc.CreateDecryptor());
        using (var index = new ArcView.Reader (input))
        {
            int count = index.ReadInt32();
            if (!IsSaneCount (count))
                return null;
            if (is_video)
                video_key = index.ReadBytes (scheme.MovKeyIs2D ? 0x10000 : 0x100);

            dir = new List<Entry> (count);
            for (int i = 0; i < count; ++i)
            {
                var name = index.BaseStream.ReadCString();
                var entry = FormatCatalog.Instance.Create<PazEntry> (name);
                entry.Offset    = index.ReadInt64();
                entry.UnpackedSize = index.ReadUInt32();
                entry.Size        = index.ReadUInt32();
                entry.AlignedSize = index.ReadUInt32();
                if (!entry.CheckPlacement (max_offset))
                    return null;
                entry.IsPacked = index.ReadInt32 () != 0;
                if (string.IsNullOrEmpty (entry.Type) && is_audio)
                {
                    entry.Type = "audio";
                }
                if (scheme.Version > 0)
                {
                    string password = "";
                    if (!entry.IsPacked && scheme.TypeKeys != null)
                    {
                        password = scheme.GetTypePassword (name, is_audio);
                    }
                    if (!string.IsNullOrEmpty (password) || is_video)
                    {
                        password = string.Format ("{0} {1:X08} {2}", name.ToLowerInvariant(), entry.UnpackedSize, password);
                        entry.Key = Encodings.cp932.GetBytes (password);
                    }
                }
                dir.Add (entry);
            }
        }
    }
    finally
    {
        input.Dispose();
    }
    List<ArcView> parts = null;
    if (arc_list.Count > 0)
    {
        parts = new List<ArcView> (arc_list.Count);
        try
        {
            foreach (var arc_entry in arc_list)
            {
                var arc_file = VFS.OpenView (arc_entry);
                parts.Add (arc_file);
            }
        }
        catch
        {
            foreach (var part in parts)
                part.Dispose();
            throw;
        }
    }
    if (is_video)
    {
        if (scheme.MovKeyIs2D)
            return new MovTwoPazArchive (file, this, dir, scheme.Version, xor_key, video_key, parts);
        if (scheme.Version < 1)
        {
            var table = new byte[0x100];
            for (int i = 0; i < 0x100; ++i)
                table[video_key[i]] = (byte)i;
            video_key = table;
        }
        return new MovPazArchive (file, this, dir, scheme.Version, xor_key, video_key, parts);
    }
    return new PazArchive (file, this, dir, scheme.Version, xor_key, scheme.ArcKeys[arc_name].DataKey, parts);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = arc as PazArchiveBase;
    var pent = entry as PazEntry;
    if (null == parc || null == pent)
        return base.OpenEntry (arc, entry);

    Stream input = parc.OpenStream (entry);
    try
    {
        if (parc.XorKey != 0)
            input = new XoredStream (input, parc.XorKey);

        input = parc.DecryptEntry (input, pent);

        if (pent.Size < pent.AlignedSize)
            input = new LimitStream (input, pent.Size);
        if (pent.IsPacked)
            input = new ZLibStream (input, CompressionMode.Decompress);
        return input;
    }
    catch
    {
        if (input != null)
            input.Dispose();
        throw;
    }
}
```

#### QueryEncryption

```csharp
PazScheme QueryEncryption (string arc_name, uint signature) {
    PazScheme scheme = null;
    if (!KnownSchemes.TryGetValue (signature, out scheme) && KnownTitles.Count > 1)
    {
        var title = FormatCatalog.Instance.LookupGame (arc_name);
        scheme = GetScheme (title);
        if (null == scheme)
        {
            if (!arc_name.HasExtension (".paz"))
                return null;
            var options = Query<PazOptions> (arcStrings.ArcEncryptedNotice);
            scheme = options.Scheme;
        }
    }
    arc_name = Path.GetFileNameWithoutExtension (arc_name).ToLowerInvariant();
    if (null == scheme || !scheme.ArcKeys.ContainsKey (arc_name))
        throw new UnknownEncryptionScheme();
    return scheme;
}
```

#### GetScheme

```csharp
PazScheme GetScheme (string title) {
    PazScheme scheme;
    if (string.IsNullOrEmpty (title) || !KnownTitles.TryGetValue (title, out scheme))
        return null;
    return scheme;
}
```

### GameRes.Formats.Musica.PazScheme

#### 状态与常量

```csharp
public int                          Version ;

public IDictionary<string, PazKey>  ArcKeys ;

public IDictionary<string, string>  TypeKeys ;

public bool                         MovKeyIs2D ;
```

#### GetTypePassword

```csharp
public string GetTypePassword (string name, bool is_audio) {
    string password = null;
    if (name.Contains ('.'))
    {
        if (name.EndsWith (".png"))
            TypeKeys.TryGetValue ("png", out password);
        else if (name.EndsWith (".ogg") || is_audio)
            TypeKeys.TryGetValue ("ogg", out password);
        else if (name.EndsWith (".sc"))
            TypeKeys.TryGetValue ("sc", out password);
        else if (name.EndsWith (".avi") || name.EndsWith (".mpg") || name.EndsWith (".mpeg"))
            TypeKeys.TryGetValue ("avi", out password);
    }
    else if (is_audio)
        TypeKeys.TryGetValue ("ogg", out password);
    return password ?? "";
}
```

## 配套算法与外部条件

- [ArcFormats/Blowfish.cs](../Blowfish.md)：本页引用的随包算法资料。
- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/MultiFileArchive.cs](../MultiFileArchive.md)：本页引用的随包算法资料。
- [ArcFormats/RC4.cs](../RC4.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Musica/ArcPAZ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
