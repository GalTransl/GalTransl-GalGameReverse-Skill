# Unity / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/IDX` / `GameRes.Formats.Unity.BinOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `int length = idx.ReadInt32();` |
| `BinOpener.TryOpen` | `entry.Offset = Convert.ToInt64 (info["index"]);` |
| `BinOpener.TryOpen` | `entry.Size   = Convert.ToUInt32 (info["size"]);` |
| `BinDeserializer.DeserializeEntry` | `int id = input.ReadByte();` |
| `BinDeserializer.DeserializeEntry` | `id = input.ReadByte();` |
| `BinDeserializer.ReadField` | `int id = input.ReadByte();` |
| `BinDeserializer.ReadField` | `return ReadString (input, length);` |
| `BinDeserializer.ReadField` | `int value = input.ReadByte();` |
| `BinDeserializer.ReadField` | `return BigEndian.ToInt16 (m_buffer, 0);` |
| `BinDeserializer.ReadField` | `return BigEndian.ToInt32 (m_buffer, 0);` |
| `BinDeserializer.ReadField` | `int length = BigEndian.ToUInt16 (m_buffer, 0);` |
| `BinDeserializer.ReadString` | `string ReadString (Stream input, int length) {` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.BinArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Aes Encryption ;

bool _bin_disposed = false ;
```

#### BinArchive

```csharp
public BinArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Aes enc)
    : base (arc, impl, dir) {
    Encryption = enc;
}
```

### GameRes.Formats.Unity.BinPackKey

#### 状态与常量

```csharp
public byte[]   Key ;

public byte[]   IV ;
```

#### BinPackKey

```csharp
public BinPackKey (string key, string iv) {
    Key = Encoding.UTF8.GetBytes (key);
    IV  = Encoding.UTF8.GetBytes (iv);
}
```

### GameRes.Formats.Unity.BinOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static BinPackScheme DefaultScheme = new BinPackScheme { KnownKeys = new Dictionary<string, BinPackKey>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".bin"))
        return null;
    var idx_name = Path.ChangeExtension (file.Name, "idx");
    if (!VFS.FileExists (idx_name))
        return null;
    var scheme = QueryScheme (file.Name);
    if (null == scheme)
        return null;
    var dir = new List<Entry>();
    using (var idx = VFS.OpenBinaryStream (idx_name))
    using (var aes = Aes.Create())
    {
        aes.Padding = PaddingMode.PKCS7;
        aes.Mode = CipherMode.CBC;
        aes.KeySize = 128;
        aes.Key = scheme.Key;
        aes.IV = scheme.IV;
        var input_buffer = new byte[0x100];
        var unpacker = new BinDeserializer();
        while (idx.PeekByte() != -1)
        {
            int length = idx.ReadInt32();
            if (length <= 0)
                return null;
            if (length > input_buffer.Length)
                input_buffer = new byte[length];
            if (idx.Read (input_buffer, 0, length) < length)
                return null;
            using (var decryptor = aes.CreateDecryptor())
            using (var encrypted = new MemoryStream (input_buffer, 0, length))
            using (var input = new InputCryptoStream (encrypted, decryptor))
            {
                var info = unpacker.DeserializeEntry (input);
                var filename = info["fileName"] as string;
                if (string.IsNullOrEmpty (filename))
                    return null;
                filename = filename.TrimStart ('/', '\\');
                var entry = Create<Entry> (filename);
                entry.Offset = Convert.ToInt64 (info["index"]);
                entry.Size   = Convert.ToUInt32 (info["size"]);
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                dir.Add (entry);
            }
        }
    }
    if (0 == dir.Count)
        return null;
    var arc_aes = Aes.Create();
    arc_aes.Padding = PaddingMode.PKCS7;
    arc_aes.Mode = CipherMode.CBC;
    arc_aes.KeySize = 256;
    arc_aes.Key = scheme.Key;
    arc_aes.IV = scheme.IV;
    return new BinArchive (file, this, dir, arc_aes);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var bin_arc = (BinArchive)arc;
    var decryptor = bin_arc.Encryption.CreateDecryptor();
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new InputCryptoStream (input, decryptor);
}
```

#### QueryScheme

```csharp
BinPackKey QueryScheme (string arc_name) {
    return DefaultScheme.KnownKeys.Values.FirstOrDefault();
}
```

### GameRes.Formats.Unity.BinDeserializer

#### 状态与常量

```csharp
byte[] m_buffer = new byte[0x20] ;
```

#### DeserializeEntry

```csharp
public IDictionary DeserializeEntry (Stream input) {
    int id = input.ReadByte();
    if (id < 0x80 || id > 0x8F)
        throw new FormatException();
    int field_count = id & 0xF;
    var map = new Hashtable (field_count);
    for (int i = 0; i < field_count; ++i)
    {
        id = input.ReadByte();
        if (id < 0xA0 || id > 0xBF)
            throw new FormatException();
        int length = id & 0x1F;
        if (input.Read (m_buffer, 0, length) < length)
            throw new FormatException();
        var key = Encoding.UTF8.GetString (m_buffer, 0, length);
        var value = ReadField (input);
        map[key] = value;
    }
    return map;
}
```

#### ReadField

```csharp
object ReadField (Stream input) {
    int id = input.ReadByte();
    if (id >= 0 && id < 0x80)
    {
        return id;
    }
    else if (id >= 0xA0 && id < 0xC0)
    {
        int length = id & 0x1F;
        return ReadString (input, length);
    }
    switch (id)
    {
    case 0xD0:
        int value = input.ReadByte();
        if (-1 == value)
            throw new FormatException();
        return (sbyte)value;

    case 0xD1:
        if (input.Read (m_buffer, 0, 2) < 2)
            throw new FormatException();
        return BigEndian.ToInt16 (m_buffer, 0);

    case 0xD2:
        if (input.Read (m_buffer, 0, 4) < 4)
            throw new FormatException();
        return BigEndian.ToInt32 (m_buffer, 0);

    case 0xDA:
        if (input.Read (m_buffer, 0, 2) < 2)
            throw new FormatException();
        int length = BigEndian.ToUInt16 (m_buffer, 0);
        return ReadString (input, length);

    default:
        throw new FormatException();
    }
}
```

#### ReadString

```csharp
string ReadString (Stream input, int length) {
    if (length > m_buffer.Length)
        m_buffer = new byte[(length + 0xF) & ~0xF];
    input.Read (m_buffer, 0, length);
    return Encoding.UTF8.GetString (m_buffer, 0, length);
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
