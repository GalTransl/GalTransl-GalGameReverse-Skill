# RealLive / ArcSCENE：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCK/SCENE` / `GameRes.Formats.RealLive.SceneOpener` | `pck` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SceneOpener.TryOpen` | `int header_length = file.View.ReadInt32 (0);` |
| `SceneOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (0x34);` |
| `SceneOpener.TryOpen` | `int count = file.View.ReadInt32 (0x38);` |
| `SceneOpener.TryOpen` | `if (file.View.ReadInt32 (0x40) != count)` |
| `SceneOpener.TryOpen` | `if (file.View.ReadInt32 (0x48) != count)` |
| `SceneOpener.TryOpen` | `if (file.View.ReadInt32 (0x50) != count)` |
| `SceneOpener.TryOpen` | `uint name_offset = file.View.ReadUInt32 (0x3C);` |
| `SceneOpener.TryOpen` | `uint pos_offset = file.View.ReadUInt32 (0x44);` |
| `SceneOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (0x4C);` |
| `SceneOpener.TryOpen` | `var name_ofs = name_offset + file.View.ReadUInt32 (offset) * 2;` |
| `SceneOpener.TryOpen` | `var name_len = file.View.ReadUInt32 (offset + 4);` |
| `SceneOpener.TryOpen` | `var name_buf = file.View.ReadBytes (name_ofs, name_len * 2);` |
| `SceneOpener.TryOpen` | `dir[i].Offset = data_offset + file.View.ReadUInt32 (offset);` |
| `SceneOpener.TryOpen` | `dir[i].Size = file.View.ReadUInt32 (offset + 4);` |
| `SceneOpener.TryOpen` | `if (file.View.ReadUInt32 (0x54) != 0)` |
| `SceneOpener.GuessKey` | `uint k = LittleEndian.ToUInt32 (buffer, 0) ^ (uint)input.Length;` |
| `SceneOpener.GuessKey` | `uint t = LittleEndian.ToUInt32 (buffer, pos);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RealLive.SceneArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public byte[] FirstKey ;

public byte[] SecondKey ;
```

#### SceneArchive

```csharp
public SceneArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] first_key, byte[] second_key)
    : base (arc, impl, dir) {
    FirstKey = first_key;
    SecondKey = second_key;
}
```

### GameRes.Formats.RealLive.SceneOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] ExtraKey ;
```

### GameRes.Formats.RealLive.SceneOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static SceneScheme DefaultScheme = new SceneScheme {
    KnownKeys = new Dictionary<string, byte[]>()
}

static readonly byte[] DefaultKey = {
    0x70, 0xF8, 0xA6, 0xB0, 0xA1, 0xA5, 0x28, 0x4F, 0xB5, 0x2F, 0x48, 0xFA, 0xE1, 0xE9, 0x4B, 0xDE,
    0xB7, 0x4F, 0x62, 0x95, 0x8B, 0xE0, 0x03, 0x80, 0xE7, 0xCF, 0x0F, 0x6B, 0x92, 0x01, 0xEB, 0xF8,
    0xA2, 0x88, 0xCE, 0x63, 0x04, 0x38, 0xD2, 0x6D, 0x8C, 0xD2, 0x88, 0x76, 0xA7, 0x92, 0x71, 0x8F,
    0x4E, 0xB6, 0x8D, 0x01, 0x79, 0x88, 0x83, 0x0A, 0xF9, 0xE9, 0x2C, 0xDB, 0x67, 0xDB, 0x91, 0x14,
    0xD5, 0x9A, 0x4E, 0x79, 0x17, 0x23, 0x08, 0x96, 0x0E, 0x1D, 0x15, 0xF9, 0xA5, 0xA0, 0x6F, 0x58,
    0x17, 0xC8, 0xA9, 0x46, 0xDA, 0x22, 0xFF, 0xFD, 0x87, 0x12, 0x42, 0xFB, 0xA9, 0xB8, 0x67, 0x6C,
    0x91, 0x67, 0x64, 0xF9, 0xD1, 0x1E, 0xE4, 0x50, 0x64, 0x6F, 0xF2, 0x0B, 0xDE, 0x40, 0xE7, 0x47,
    0xF1, 0x03, 0xCC, 0x2A, 0xAD, 0x7F, 0x34, 0x21, 0xA0, 0x64, 0x26, 0x98, 0x6C, 0xED, 0x69, 0xF4,
    0xB5, 0x23, 0x08, 0x6E, 0x7D, 0x92, 0xF6, 0xEB, 0x93, 0xF0, 0x7A, 0x89, 0x5E, 0xF9, 0xF8, 0x7A,
    0xAF, 0xE8, 0xA9, 0x48, 0xC2, 0xAC, 0x11, 0x6B, 0x2B, 0x33, 0xA7, 0x40, 0x0D, 0xDC, 0x7D, 0xA7,
    0x5B, 0xCF, 0xC8, 0x31, 0xD1, 0x77, 0x52, 0x8D, 0x82, 0xAC, 0x41, 0xB8, 0x73, 0xA5, 0x4F, 0x26,
    0x7C, 0x0F, 0x39, 0xDA, 0x5B, 0x37, 0x4A, 0xDE, 0xA4, 0x49, 0x0B, 0x7C, 0x17, 0xA3, 0x43, 0xAE,
    0x77, 0x06, 0x64, 0x73, 0xC0, 0x43, 0xA3, 0x18, 0x5A, 0x0F, 0x9F, 0x02, 0x4C, 0x7E, 0x8B, 0x01,
    0x9F, 0x2D, 0xAE, 0x72, 0x54, 0x13, 0xFF, 0x96, 0xAE, 0x0B, 0x34, 0x58, 0xCF, 0xE3, 0x00, 0x78,
    0xBE, 0xE3, 0xF5, 0x61, 0xE4, 0x87, 0x7C, 0xFC, 0x80, 0xAF, 0xC4, 0x8D, 0x46, 0x3A, 0x5D, 0xD0,
    0x36, 0xBC, 0xE5, 0x60, 0x77, 0x68, 0x08, 0x4F, 0xBB, 0xAB, 0xE2, 0x78, 0x07, 0xE8, 0x73, 0xBF
}
```

#### SceneOpener

```csharp
public SceneOpener () {
    Extensions = new string[] { "pck" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int header_length = file.View.ReadInt32 (0);
    if (header_length != 0x5C)
        return null;

    uint offset = file.View.ReadUInt32 (0x34);
    int count = file.View.ReadInt32 (0x38);
    if (!IsSaneCount (count))
        return null;
    if (file.View.ReadInt32 (0x40) != count)
        return null;
    if (file.View.ReadInt32 (0x48) != count)
        return null;
    if (file.View.ReadInt32 (0x50) != count)
        return null;

    uint name_offset = file.View.ReadUInt32 (0x3C);
    uint pos_offset = file.View.ReadUInt32 (0x44);
    uint data_offset = file.View.ReadUInt32 (0x4C);
    if (name_offset >= file.MaxOffset || pos_offset >= file.MaxOffset || data_offset >= file.MaxOffset)
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; i++)
    {
        var name_ofs = name_offset + file.View.ReadUInt32 (offset) * 2;
        var name_len = file.View.ReadUInt32 (offset + 4);
        var name_buf = file.View.ReadBytes (name_ofs, name_len * 2);
        var name = Encoding.Unicode.GetString (name_buf, 0, name_buf.Length);
        var entry = new PackedEntry {
            Name = name + ".ss",
            Type = "script",
            IsPacked = true
        };
        dir.Add (entry);
        offset += 8;
    }

    offset = pos_offset;
    for (int i = 0; i < count; i++)
    {
        dir[i].Offset = data_offset + file.View.ReadUInt32 (offset);
        dir[i].Size = file.View.ReadUInt32 (offset + 4);
        if (!dir[i].CheckPlacement (file.MaxOffset))
            return null;
        offset += 8;
    }

    byte[] extra_key = null;
    if (file.View.ReadUInt32 (0x54) != 0)
    {
        extra_key = QueryKey (file.Name);
        int i = 0;
        while (extra_key == null && i < dir.Count)
        {
            var entry = dir[i++];
            Stream input = file.CreateStream (entry.Offset, entry.Size);
            input = new ByteStringEncryptedStream (input, DefaultKey);
            extra_key = GuessKey (input);
            if (extra_key != null)
                Trace.WriteLine ("Key: " + BitConverter.ToString (extra_key), "[PCK/SCENE]");
        }
        if (extra_key == null)
            return null;
    }

    return new SceneArchive (file, this, dir, DefaultKey, extra_key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var sarc = arc as SceneArchive;
    var pent = entry as PackedEntry;
    Stream input = arc.File.CreateStream (pent.Offset, pent.Size);
    input = new ByteStringEncryptedStream (input, sarc.FirstKey);
    if (sarc.SecondKey != null)
        input = new ByteStringEncryptedStream (input, sarc.SecondKey);
    var data = G00Reader.LzDecompress (BinaryStream.FromStream (input, ""), 2, 1);
    pent.UnpackedSize = (uint)data.Length;
    return new BinMemoryStream (data, pent.Name);
}
```

#### GuessKey

```csharp
byte[] GuessKey (Stream input) {
    if (input.Length < 4)
        return null;
    var buffer = new byte[input.Length];
    var key = new byte[16];
    input.Read (buffer, 0, (int)input.Length);
    uint k = LittleEndian.ToUInt32 (buffer, 0) ^ (uint)input.Length;
    LittleEndian.Pack (k, key, 0);

    int pos = 0;
    const int CHECK = 3;

    while (true)
    {
        uint t = LittleEndian.ToUInt32 (buffer, pos);
        if (t == (k ^ 0x1f0000))
            break;
        pos += 16;
        if (pos >= input.Length - CHECK * 16)
            return null;
    }
    var check = new byte[CHECK][];
    byte flip = 0;
    for (int i = 0; i < CHECK; i++)
    {
        check[i] = new byte[12];
        flip ^= 0x1f;
        pos += 4;
        for (int j = 0; j < 12; j++)
        {
            check[i][j] = (byte)(buffer[pos++] ^ flip);
            flip ^= 0x1f;
        }
    }
    for (int i = 0; i < CHECK - 1; i++)
    {
        if (check[i].SequenceEqual (check[i + 1]))
        {
            Buffer.BlockCopy (check[i], 0, key, 4, 12);
            return key;
        }
    }
    return null;
}
```

#### QueryKey

```csharp
byte[] QueryKey (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownKeys.ContainsKey (title))
        return KnownKeys[title];
    var options = Query<SceneOptions> (arcStrings.ArcEncryptedNotice);
    return options.ExtraKey;
}
```

#### GetKey

```csharp
byte[] GetKey (string title) {
    byte[] key;
    if (string.IsNullOrEmpty (title) || !KnownKeys.TryGetValue (title, out key))
        return null;
    return key;
}
```

## 配套算法与外部条件

- [ArcFormats/RealLive/ImageG00.cs](ImageG00.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/RealLive/ArcSCENE.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
