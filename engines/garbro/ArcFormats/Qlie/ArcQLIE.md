# Qlie / ArcQLIE：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/QLIE` / `GameRes.Formats.Qlie.PackOpener` | `pack` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `if (!file.View.AsciiEqual (index_offset, "FilePackVer")` |
| `PackOpener.TryOpen` | `\|\| '.' != file.View.ReadByte (index_offset+0xC))` |
| `PackOpener.ReadEntryBytes` | `var data = file.View.ReadBytes (entry.Offset, entry.Size);` |
| `PackOpener.Decompress` | `if (LittleEndian.ToUInt32 (input, 0) != 0xFF435031)` |
| `PackOpener.Decompress` | `int output_length = LittleEndian.ToInt32 (input, 8);` |
| `PackOpener.Decompress` | `count = LittleEndian.ToUInt16 (input, src);` |
| `PackOpener.Decompress` | `count = LittleEndian.ToInt32 (input, src);` |
| `PackOpener.GetKeyDataFromExe` | `if (null == tform \|\| !tform.AsciiEqual (0, "TPF0"))` |
| `PackOpener.GetKeyDataFromExe` | `if (null == icon \|\| icon.Length < 0x106 \|\| !icon.AsciiEqual (0, "\x05TIcon"))` |
| `PackIndexReader.PackIndexReader` | `m_pack_version = new Version (m_file.View.ReadByte (index_offset+0xB) - '0',` |
| `PackIndexReader.PackIndexReader` | `m_file.View.ReadByte (index_offset+0xD) - '0');` |
| `PackIndexReader.PackIndexReader` | `m_count = m_file.View.ReadInt32 (index_offset+0x10);` |
| `PackIndexReader.PackIndexReader` | `m_index_offset = m_file.View.ReadInt64 (index_offset+0x14);` |
| `PackIndexReader.Read` | `int name_length = m_index.ReadUInt16();` |
| `PackIndexReader.Read` | `entry.Offset = m_index.ReadInt64();` |
| `PackIndexReader.Read` | `entry.Size   = m_index.ReadUInt32();` |
| `PackIndexReader.Read` | `entry.UnpackedSize = m_index.ReadUInt32();` |
| `PackIndexReader.Read` | `entry.IsPacked    = 0 != m_index.ReadInt32();` |
| `PackIndexReader.Read` | `entry.EncryptionMethod = m_index.ReadInt32();` |
| `PackIndexReader.Read` | `entry.Hash = m_index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Qlie.QlieEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int  EncryptionMethod ;

public uint Hash ;

public byte[] RawName ;

public bool IsEncrypted { get { return EncryptionMethod != 0; } }

public byte[] KeyFile ;
```

### GameRes.Formats.Qlie.QlieArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IEncryption Encryption ;
```

#### QlieArchive

```csharp
public QlieArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IEncryption enc)
    : base (arc, impl, dir) {
    Encryption = enc;
}
```

### GameRes.Formats.Qlie.QlieOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] GameKeyData ;
```

### GameRes.Formats.Qlie.PackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly string[] KeyLocations = { ".", "..", @"..\DLL", "DLL" }

static QlieScheme DefaultScheme = new QlieScheme { KnownKeys = new Dictionary<string, byte[]>() }
```

#### PackOpener

```csharp
public PackOpener () {
    Extensions = new string [] { "pack" };
    ContainedFormats = new[] { "ABMP/QLIE", "DPNG", "ARGB", "PNG", "JPEG", "OGG", "WAV" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 0x1c)
        return null;
    long index_offset = file.MaxOffset - 0x1c;
    if (!file.View.AsciiEqual (index_offset, "FilePackVer")
        || '.' != file.View.ReadByte (index_offset+0xC))
        return null;
    using (var index = new PackIndexReader (this, file, index_offset))
    {
        byte[] arc_key = null;
        byte[] key_file = null;
        bool use_pack_keyfile = false;
        if (index.PackVersion.Major >= 3)
        {
            key_file = FindKeyFile (file);
            use_pack_keyfile = key_file != null;

            if (use_pack_keyfile && index.PackVersion.Minor == 0)
                arc_key = QueryEncryption (file);

        }
        var enc = QlieEncryption.Create (file, index.PackVersion, arc_key);
        List<Entry> dir = null;
        if (index.PackVersion.Major > 1)
        {
            dir = index.Read (enc, key_file, use_pack_keyfile);
        }
        else
        {

            var possibleEncs = new IEncryption[] {
                enc, new EncryptionV2 (IndexLayout.WithoutHash), new EncryptionV2()
            };
            foreach (var v1enc in possibleEncs)
            {
                try
                {
                    dir = index.Read (v1enc, key_file, use_pack_keyfile);
                    if (dir != null)
                    {
                        enc = v1enc;
                        break;
                    }
                }
                catch { }
            }
        }
        if (null == dir)
            return null;
        return new QlieArchive (file, this, dir, enc);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var qent = entry as QlieEntry;
    var qarc = arc as QlieArchive;
    if (null == qent || null == qarc || (!qent.IsEncrypted && !qent.IsPacked))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = ReadEntryBytes (arc.File, qent, qarc.Encryption);
    return new BinMemoryStream (data, entry.Name);
}
```

#### ReadEntryBytes

```csharp
internal byte[] ReadEntryBytes (ArcView file, QlieEntry entry, IEncryption enc) {
    var data = file.View.ReadBytes (entry.Offset, entry.Size);
    if (entry.IsEncrypted)
    {
        enc.DecryptEntry (data, 0, data.Length, entry);
    }
    if (entry.IsPacked)
    {
        data = Decompress (data) ?? data;
    }
    return data;
}
```

#### Decompress

```csharp
internal static byte[] Decompress (byte[] input) {
    if (LittleEndian.ToUInt32 (input, 0) != 0xFF435031)
        return null;

    bool is_16bit = 0 != (input[4] & 1);

    var node = new byte[2,256];
    var child_node = new byte[256];

    int output_length = LittleEndian.ToInt32 (input, 8);
    var output = new byte[output_length];

    int src = 12;
    int dst = 0;
    while (src < input.Length)
    {
        int i, k, count, index;

        for (i = 0; i < 256; i++)
            node[0,i] = (byte)i;

        for (i = 0; i < 256; )
        {
            count = input[src++];

            if (count > 127)
            {
                int step = count - 127;
                i += step;
                count = 0;
            }

            if (i > 255)
                break;

            count++;
            for (k = 0; k < count; k++)
            {
                node[0,i] = input[src++];
                if (node[0,i] != i)
                    node[1,i] = input[src++];
                i++;
            }
        }

        if (is_16bit)
        {
            count = LittleEndian.ToUInt16 (input, src);
            src += 2;
        }
        else
        {
            count = LittleEndian.ToInt32 (input, src);
            src += 4;
        }

        k = 0;
        for (;;)
        {
            if (k > 0)
                index = child_node[--k];
            else
            {
                if (0 == count)
                    break;
                count--;
                index = input[src++];
            }

            if (node[0,index] == index)
                output[dst++] = (byte)index;
            else
            {
                child_node[k++] = node[1,index];
                child_node[k++] = node[0,index];
            }
        }
    }
    if (dst != output.Length)
        return null;

    return output;
}
```

#### QueryEncryption

```csharp
byte[] QueryEncryption (ArcView file) {
    var title = FormatCatalog.Instance.LookupGame (file.Name, @"..\*.exe");
    byte[] key = null;
    if (!string.IsNullOrEmpty (title) && KnownKeys.ContainsKey (title))
        return KnownKeys[title];
    if (null == key)
        key = GuessKeyData (file.Name);
    if (null == key)
    {
        var options = Query<QlieOptions> (arcStrings.ArcEncryptedNotice);
        key = options.GameKeyData;
    }
    return key;
}
```

#### GetKeyData

```csharp
static byte[] GetKeyData (string scheme) {
    byte[] key;
    if (KnownKeys.TryGetValue (scheme, out key))
        return key;
    return null;
}
```

#### FindKeyFile

```csharp
static byte[] FindKeyFile (ArcView arc_file) {

    if (VFS.IsVirtual)
        return null;
    var dir_name = Path.GetDirectoryName (arc_file.Name);
    foreach (var path in KeyLocations)
    {
        var name = Path.Combine (dir_name, path, "key.fkey");
        if (File.Exists (name))
        {
            Trace.WriteLine ("reading key from "+name, "[QLIE]");
            return File.ReadAllBytes (name);
        }
    }
    var pattern = VFS.CombinePath (dir_name, @"..\*.exe");
    foreach (var exe_file in VFS.GetFiles (pattern))
    {
        using (var exe = new ExeFile.ResourceAccessor (exe_file.Name))
        {
            var reskey = exe.GetResource ("RESKEY", "#10");
            if (reskey != null)
                return reskey;
        }
    }
    return null;
}
```

#### GuessKeyData

```csharp
byte[] GuessKeyData (string arc_name) {
    if (VFS.IsVirtual)
        return null;

    var pattern = VFS.CombinePath (VFS.GetDirectoryName (arc_name), @"..\*.exe");
    foreach (var file in VFS.GetFiles (pattern))
    {
        try
        {
            var key = GetKeyDataFromExe (file.Name);
            if (key != null)
                return key;
        }
        catch {  }
    }
    return null;
}
```

#### GetKeyDataFromExe

```csharp
public static byte[] GetKeyDataFromExe (string filename) {
    using (var exe = new ExeFile.ResourceAccessor (filename))
    {
        var tform = exe.GetResource ("TFORM1", "#10");
        if (null == tform || !tform.AsciiEqual (0, "TPF0"))
            return null;
        using (var input = new BinMemoryStream (tform))
        {
            var deserializer = new DelphiDeserializer (input);
            var form = deserializer.Deserialize();
            var image = form.Contents.FirstOrDefault (n => n.Name == "IconKeyImage");
            if (null == image)
                return null;
            var icon = image.Props["Picture.Data"] as byte[];
            if (null == icon || icon.Length < 0x106 || !icon.AsciiEqual (0, "\x05TIcon"))
                return null;
            return new CowArray<byte> (icon, 6, 0x100).ToArray();
        }
    }
}
```

### GameRes.Formats.Qlie.PackIndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
PackOpener  m_fmt ;

ArcView     m_file ;

Version     m_pack_version ;

int         m_count ;

long        m_index_offset ;

IBinaryStream   m_index ;

List<Entry> m_dir ;

public Version PackVersion { get { return m_pack_version; } }

byte[]  m_name_buffer = new byte[0x100] ;

bool m_disposed = false ;
```

#### PackIndexReader

```csharp
public PackIndexReader (PackOpener fmt, ArcView file, long index_offset) {
    m_fmt = fmt;
    m_file = file;
    m_pack_version = new Version (m_file.View.ReadByte (index_offset+0xB) - '0',
                                  m_file.View.ReadByte (index_offset+0xD) - '0');
    m_count = m_file.View.ReadInt32 (index_offset+0x10);
    if (!ArchiveFormat.IsSaneCount (m_count))
        throw new InvalidFormatException();
    m_index_offset = m_file.View.ReadInt64 (index_offset+0x14);
    if (index_offset < 0 || index_offset >= m_file.MaxOffset)
        throw new InvalidFormatException();
    m_index = m_file.CreateStream (m_index_offset);
    m_dir = new List<Entry> (m_count);
}
```

#### Read

```csharp
public List<Entry> Read (IEncryption enc, byte[] key_file, bool use_pack_keyfile) {
    m_dir.Clear();
    m_index.Position = 0;
    bool read_pack_keyfile = 3 == m_pack_version.Major && use_pack_keyfile;
    for (int i = 0; i < m_count; ++i)
    {
        int name_length = m_index.ReadUInt16();
        if (name_length > 0x100)
            return null;
        if (enc.IsUnicode)
            name_length *= 2;
        if (name_length > m_name_buffer.Length)
            m_name_buffer = new byte[name_length];
        if (name_length != m_index.Read (m_name_buffer, 0, name_length))
            return null;
        var name = enc.DecryptName (m_name_buffer, name_length);
        var entry = m_fmt.Create<QlieEntry> (name);
        if (use_pack_keyfile)
            entry.RawName = m_name_buffer.Take (name_length).ToArray();

        entry.Offset = m_index.ReadInt64();
        entry.Size   = m_index.ReadUInt32();
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return null;
        entry.UnpackedSize = m_index.ReadUInt32();
        entry.IsPacked    = 0 != m_index.ReadInt32();
        entry.EncryptionMethod = m_index.ReadInt32();
        if (enc.IndexLayout == IndexLayout.WithHash)
            entry.Hash = m_index.ReadUInt32();
        entry.KeyFile = key_file;
        if (read_pack_keyfile && entry.Name.Contains ("pack_keyfile"))
        {

            key_file = m_fmt.ReadEntryBytes (m_file, entry, enc);
            read_pack_keyfile = false;
        }
        m_dir.Add (entry);
    }
    return m_dir;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/Qlie/DelphiDeserializer.cs](DelphiDeserializer.md)：本页引用的随包算法资料。
- [ArcFormats/Qlie/Encryption.cs](Encryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Qlie/ArcQLIE.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
