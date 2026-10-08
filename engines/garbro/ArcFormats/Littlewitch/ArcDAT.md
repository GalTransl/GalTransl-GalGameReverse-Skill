# Littlewitch / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/RepiPack` / `GameRes.Formats.Littlewitch.DatOpener` | `dat` | `52657069` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "Pack"))` |
| `DatOpener.TryOpen` | `int version = file.View.ReadInt32 (8);` |
| `DatOpener.TryOpen` | `uint name_length = file.View.ReadUInt32 (0xC);` |
| `DatOpener.TryOpen` | `uint name_key = file.View.ReadUInt32 (0x10);` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10 + name_length);` |
| `DatOpener.TryOpen` | `var index = file.View.ReadBytes (0x14 + name_length, (uint)count * 0x20);` |
| `DatOpener.TryOpen` | `entry.Offset        = index.ToUInt32 (pos+0x10);` |
| `DatOpener.TryOpen` | `entry.Size          = index.ToUInt32 (pos+0x14);` |
| `DatOpener.TryOpen` | `entry.UnpackedSize  = index.ToUInt32 (pos+0x18);` |
| `DatOpener.OpenV2` | `uint name_length = file.View.ReadUInt32 (0xC);` |
| `DatOpener.OpenV2` | `uint name_key = file.View.ReadUInt32 (0x10);` |
| `DatOpener.OpenV2` | `int count = file.View.ReadInt32 (0x10 + name_length);` |
| `DatOpener.OpenV2` | `var index = file.View.ReadBytes (0x14 + name_length, (uint)count * 0x50);` |
| `DatOpener.OpenV2` | `entry.Offset        = index.ToUInt32 (pos+0x40);` |
| `DatOpener.OpenV2` | `entry.UnpackedSize  = index.ToUInt32 (pos+0x44);` |
| `DatOpener.OpenV2` | `entry.Size          = index.ToUInt32 (pos+0x48);` |
| `DatOpener.OpenV2` | `entry.Mode = index.ToInt32 (pos+0x4C);` |
| `DatOpener.OpenEntry` | `byte[] encrypted = arc.File.View.ReadBytes (entry.Offset, enc_length);` |
| `DatOpener.FindKey` | `arc_key ^= name_bytes.ToUInt32 (0);` |
| `Md5Comparer.GetHashCode` | `var hash = key.ToInt32 (0);` |
| `Md5Comparer.GetHashCode` | `hash ^= key.ToInt32 (4);` |
| `Md5Comparer.GetHashCode` | `hash ^= key.ToInt32 (8);` |
| `Md5Comparer.GetHashCode` | `hash ^= key.ToInt32 (12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Littlewitch.RepiEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool HasEncryptionKey ;

public int Mode ;

public uint[] LegacyKey ;
```

#### CreateKey

```csharp
public byte[] CreateKey () {
    var name_bytes = Name.ToLowerShiftJis();
    int name_length = name_bytes.Length;
    var md5 = new MD5();
    Array.Reverse (name_bytes);
    var key = new byte[1024];
    int key_pos = 0;
    for (int i = 0; i < 64; ++i)
    {
        int name_pos = i % name_length;
        md5.Update (name_bytes, name_pos, name_length - name_pos);
        md5.Final();
        Buffer.BlockCopy (md5.State, 0, key, key_pos, 16);
        key_pos += 16;
    }
    return key;
}
```

### GameRes.Formats.Littlewitch.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly string ListFileName = name_list_parameter ;

static RepiScheme DatScheme = new RepiScheme { KnownSchemes = new Dictionary<string, uint[]>() }

static Lazy<Dictionary<byte[], string>> s_known_file_names = new Lazy<Dictionary<byte[], string>> (ReadFileList) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "Pack"))
        return null;
    int version = file.View.ReadInt32 (8);
    if (version == 2 || version == 3)
        return OpenV2 (file);
    else if (version != 5)
        return null;
    uint name_length = file.View.ReadUInt32 (0xC);
    if (name_length < 4)
        return null;
    uint name_key = file.View.ReadUInt32 (0x10);
    var key = FindKey (file.Name, name_key);
    if (null == key)
        return null;
    int count = file.View.ReadInt32 (0x10 + name_length);
    if (!IsSaneCount (count))
        return null;
    var index = file.View.ReadBytes (0x14 + name_length, (uint)count * 0x20);
    int pos = 0;
    var dir = new List<Entry> (count);
    var name_builder = new StringBuilder();
    for (int i = 0; i < count; ++i)
    {
        DecryptData (index, pos, 0x20, key[2], key[1]);
        var entry = EntryFromMd5 (index, pos, name_builder);
        entry.Offset        = index.ToUInt32 (pos+0x10);
        entry.Size          = index.ToUInt32 (pos+0x14);
        entry.UnpackedSize  = index.ToUInt32 (pos+0x18);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Mode = -1;
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        dir.Add (entry);
        pos += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenV2

```csharp
ArcFile OpenV2 (ArcView file) {
    uint name_length = file.View.ReadUInt32 (0xC);
    if (name_length < 4)
        return null;
    uint name_key = file.View.ReadUInt32 (0x10);
    var key = FindKey (file.Name, name_key);
    if (null == key)
        return null;
    int count = file.View.ReadInt32 (0x10 + name_length);
    if (!IsSaneCount (count))
        return null;
    var index = file.View.ReadBytes (0x14 + name_length, (uint)count * 0x50);
    int pos = 0;
    var dir = new List<Entry> (count);
    var name_builder = new StringBuilder();
    for (int i = 0; i < count; ++i)
    {
        DecryptData (index, pos, 0x50, key[2], key[1]);
        var name = Binary.GetCString (index, pos, 0x40);
        var entry = FormatCatalog.Instance.Create<RepiEntry> (name);
        entry.Offset        = index.ToUInt32 (pos+0x40);
        entry.UnpackedSize  = index.ToUInt32 (pos+0x44);
        entry.Size          = index.ToUInt32 (pos+0x48);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Mode = index.ToInt32 (pos+0x4C);
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        entry.HasEncryptionKey = true;
        entry.LegacyKey = key;
        dir.Add (entry);
        pos += 0x50;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var rent = entry as RepiEntry;
    if (null == rent || !rent.HasEncryptionKey)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var key = rent.CreateKey();
    uint enc_length = rent.Mode == -1 ? Math.Min ((uint)key.Length, rent.Size) : rent.Size;
    byte[] encrypted = arc.File.View.ReadBytes (entry.Offset, enc_length);
    switch (rent.Mode)
    {
        case -1:
            DecryptEntry (encrypted, key);
            break;
        case 1:
            DecryptData (encrypted, 0, (int)enc_length, rent.LegacyKey[2], rent.LegacyKey[1]);
            break;
        case 2:
            DecryptData2 (encrypted, 0, (int)enc_length, (byte)rent.LegacyKey[2]);
            break;
    }
    Stream input;
    if (enc_length == entry.Size)
    {
        input = new BinMemoryStream (encrypted, entry.Name);
    }
    else
    {
        input = arc.File.CreateStream (entry.Offset + enc_length, entry.Size - enc_length);
        input = new PrefixStream (encrypted, input);
    }
    if (rent.IsPacked)
    {
        input = new LzssStream (input);
    }
    return input;
}
```

#### DecryptEntry

```csharp
static void DecryptEntry (byte[] data, byte[] key) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] ^= key[i];
    }
}
```

#### DecryptData

```csharp
static unsafe void DecryptData (byte[] data, int pos, int length, uint key, uint seed) {
    if (pos < 0 || pos + length > data.Length)
        throw new ArgumentOutOfRangeException ("pos", "Invalid byte array index.");
    fixed (byte* data8 = &data[pos])
    {
        uint* data32 = (uint*)data8;
        for (int count = length / 4; count > 0; --count)
        {
            *data32 ^= key;
            key += Binary.RotL (*data32, 16) ^ seed;
            data32++;
        }
    }
}
```

#### DecryptData2

```csharp
static unsafe void DecryptData2 (byte[] data, int pos, int length, byte key) {
    if (pos < 0 || pos + length > data.Length)
        throw new ArgumentOutOfRangeException ("pos", "Invalid byte array index.");
    uint seed = (uint)(key | key << 8 | key << 16 | key << 24);
    fixed (byte* data8 = &data[pos])
    {
        uint* data32 = (uint*)data8;
        for (int count = length / 4; count > 0; --count)
        {
            *data32 = seed ^ (*data32 << 6) ^ (((*data32 >> 2) ^ (*data32 << 6)) & 0x3F3F3F3F);
            data32++;
        }
        byte* data_end = (byte*)data32;
        for (int count = length % 4; count > 0; --count)
        {
            *data_end = (byte)(key ^ Binary.RotByteR (*data_end, 2));
            data_end++;
        }
    }
}
```

#### EntryFromMd5

```csharp
RepiEntry EntryFromMd5 (byte[] data, int pos, StringBuilder builder) {
    var key = new CowArray<byte> (data, pos, 16).ToArray();
    string name;
    if (KnownNames.TryGetValue (key, out name))
    {
        var entry = FormatCatalog.Instance.Create<RepiEntry> (name);
        entry.HasEncryptionKey = true;
        return entry;
    }
    builder.Clear();
    for (int i = 0; i < 16; ++i)
    {
        builder.AppendFormat ("{0:x2}", key[i]);
    }
    return new RepiEntry { Name = builder.ToString() };
}
```

#### FindKey

```csharp
static uint[] FindKey (string arc_name, uint arc_key) {
    arc_name = Path.GetFileName (arc_name);
    var name_bytes = Encodings.cp932.GetBytes (arc_name);
    arc_key ^= name_bytes.ToUInt32 (0);
    return DatScheme.KnownSchemes.Values.FirstOrDefault (k => k[0] == arc_key);
}
```

#### ReadFileList

```csharp
static Dictionary<byte[], string> ReadFileList () {
    var dict = new Dictionary<byte[], string> (new Md5Comparer());
    try
    {
        var md5 = new MD5();
        FormatCatalog.Instance.ReadFileList (ListFileName, name => {
            var name_bytes = name.ToLowerShiftJis();
            var hash = md5.ComputeHash (name_bytes);
            dict[hash] = name;
        });
    }
    catch (Exception X)
    {
        System.Diagnostics.Trace.WriteLine (X.Message, "[RepiPack]");
    }
    return dict;
}
```

### GameRes.Formats.Littlewitch.Md5Comparer

继承/接口：`IEqualityComparer<byte[]>`。

#### Equals

```csharp
public bool Equals (byte[] left, byte[] right) {
    if (left == null || right == null)
        return left == right;
    if (left.Length != right.Length)
        return false;
    for (int i = 0; i < left.Length; ++i)
    {
        if (left[i] != right[i])
            return false;
    }
    return true;
}
```

#### GetHashCode

```csharp
public int GetHashCode (byte[] key) {
    if (null == key)
        throw new ArgumentNullException ("key");
    if (key.Length < 16)
        throw new ArgumentException ("Invalid key length.", "key");
    var hash = key.ToInt32 (0);
    hash ^= key.ToInt32 (4);
    hash ^= key.ToInt32 (8);
    hash ^= key.ToInt32 (12);
    return hash;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。
- [ArcFormats/MD5.cs](../MD5.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Littlewitch/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
