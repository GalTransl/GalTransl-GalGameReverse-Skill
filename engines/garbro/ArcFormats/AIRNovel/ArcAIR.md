# AIRNovel / ArcAIR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AIR` / `GameRes.Formats.AirNovel.AirOpener` | `air` | 无固定签名或来源表达式未解析 | `False` |

## 类型别名

| 摘录中的名称 | 来源类型 |
|---|---|
| `SharpZip` | `ICSharpCode.SharpZipLib.Zip` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AirNovel.AirEntry

继承/接口：`ZipEntry`。

#### 状态与常量

```csharp
public bool IsEncrypted { get; set; }
```

#### AirEntry

```csharp
public AirEntry (SharpZip.ZipEntry zip_entry) : base (zip_entry) {
    IsEncrypted = Name.EndsWith ("_");
    if (IsEncrypted)
    {
        Name = Name.Substring (0, Name.Length-1);
        Type = FormatCatalog.Instance.GetTypeFromName (Name);
    }
}
```

### GameRes.Formats.AirNovel.AirArchive

继承/接口：`PkZipArchive`。

#### 状态与常量

```csharp
public byte[]   Key ;

public uint     CoderLength ;
```

#### AirArchive

```csharp
public AirArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, SharpZip.ZipFile native, byte[] key) : base (arc, impl, dir, native) {
    Key = key;
}
```

### GameRes.Formats.AirNovel.AirOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<ArchiveFormat> Zip = new ResourceInstance<ArchiveFormat> ("ZIP") ;

AirNovelScheme DefaultScheme = new AirNovelScheme { KnownKeys = new Dictionary<string, string>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".air"))
        return null;
    var input = file.CreateStream();
    SharpZip.ZipFile zip = null;
    try
    {
        var sc = SharpZip.StringCodec.FromCodePage (Encoding.UTF8.CodePage);
        zip = new SharpZip.ZipFile (input, false, sc);
        var files = zip.Cast<SharpZip.ZipEntry>().Where (z => !z.IsDirectory);
        bool has_encrypted = false;
        var dir = new List<Entry>();
        foreach (var f in files)
        {
            var entry = new AirEntry (f);
            has_encrypted |= entry.IsEncrypted;
            dir.Add (entry);
        }
        if (has_encrypted)
        {
            uint coder_length;
            if (FindAirNovelCoderLength (zip, out coder_length))
            {
                var key = QueryEncryptionKey (file);
                if (!string.IsNullOrEmpty (key))
                {
                    var rc4_key = AirRc4Crypt.GenerateKey (key);
                    return new AirArchive (file, this, dir, zip, rc4_key) { CoderLength = coder_length };
                }
            }
        }
        return new PkZipArchive (file, Zip.Value, dir, zip);
    }
    catch
    {
        if (zip != null)
            zip.Close();
        input.Dispose();
        throw;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var zarc = (AirArchive)arc;
    var zent = (AirEntry)entry;
    var input = zarc.Native.GetInputStream (zent.NativeEntry);
    if (!zent.IsEncrypted)
        return input;
    var data = new byte[zent.UnpackedSize];
    using (input)
        input.Read (data, 0, data.Length);
    int enc_len;
    if (zent.Name.HasExtension (".an"))
        enc_len = data.Length;
    else
        enc_len = Math.Min (data.Length, (int)zarc.CoderLength);
    var rc4 = new AirRc4Crypt (zarc.Key);
    rc4.Decrypt (data, 0, enc_len);
    return new BinMemoryStream (data, entry.Name);
}
```

#### FindAirNovelCoderLength

```csharp
bool FindAirNovelCoderLength (SharpZip.ZipFile zip, out uint coder_length) {
    coder_length = 0;
    var config = zip.GetEntry ("config.anprj");
    if (null == config)
        return false;
    using (var input = zip.GetInputStream (config))
    {
        var coder = FindConfigNode (input, "/config/coder[@len]");
        if (null == coder)
            return false;
        var lenAttr = coder.Attributes["len"].Value;
        var styles = NumberStyles.Integer;
        if (lenAttr.StartsWith ("0x"))
        {
            lenAttr = lenAttr.Substring (2, lenAttr.Length-2);
            styles = NumberStyles.HexNumber;
        }
        return UInt32.TryParse (lenAttr, styles, CultureInfo.InvariantCulture, out coder_length);
    }
}
```

#### FindConfigNode

```csharp
XmlNode FindConfigNode (Stream input, string xpath) {
    using (var reader = new StreamReader (input))
    {
        var xml = new XmlDocument();
        xml.Load (reader);
        return xml.DocumentElement.SelectSingleNode (xpath);
    }
}
```

#### QueryEncryptionKey

```csharp
string QueryEncryptionKey (ArcView file) {
    var title = FormatCatalog.Instance.LookupGame (file.Name);
    if (string.IsNullOrEmpty (title))
        return null;
    string key;
    if (!KnownKeys.TryGetValue (title, out key))
        return null;
    return key;
}
```

### GameRes.Formats.AirNovel.AirRc4Crypt

#### 状态与常量

```csharp
const int KeyLength = 0xFF ;

byte[]  KeyState = new byte[KeyLength+1] ;
```

#### AirRc4Crypt

```csharp
public AirRc4Crypt (byte[] key) {
    for (int i = 0; i <= KeyLength; ++i)
    {
        KeyState[i] = (byte)i;
    }
    int j = 0;
    for (int i = 0; i <= KeyLength; ++i)
    {
        j = (j + KeyState[i] + key[i]) & KeyLength;
        KeyState[i] ^= KeyState[j];
        KeyState[j] ^= KeyState[i];
        KeyState[i] ^= KeyState[j];
    }
}
```

#### GenerateKey

```csharp
public static byte[] GenerateKey (string passPhrase) {
    if (string.IsNullOrEmpty (passPhrase))
        throw new ArgumentException ("passPhrase");
    var key = new byte[KeyLength+1];
    for (int i = 0; i < key.Length; ++i)
    {
        key[i] = (byte)passPhrase[i % passPhrase.Length];
    }
    return key;
}
```

#### Decrypt

```csharp
public void Decrypt (byte[] data, int pos, int length) {
    int i = 0;
    int j = 0;
    var keyCopy = KeyState.Clone() as byte[];
    int last = Math.Min (pos + length, data.Length);
    while (pos < last)
    {
        i = (i + 1) & KeyLength;
        j = (j + keyCopy[i]) & KeyLength;

        keyCopy[i] ^= keyCopy[j];
        keyCopy[j] ^= keyCopy[i];
        keyCopy[i] ^= keyCopy[j];
        int k = (keyCopy[i] + keyCopy[j]) & KeyLength;
        data[pos++] ^= keyCopy[k];
    }
}
```

## 配套算法与外部条件

- [ArcFormats/PkWare/ArcZIP.cs](../PkWare/ArcZIP.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/AIRNovel/ArcAIR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
