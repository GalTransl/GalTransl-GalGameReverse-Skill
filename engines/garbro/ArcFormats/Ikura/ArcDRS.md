# Ikura / ArcDRS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DRS` / `GameRes.Formats.Ikura.DrsOpener` | ``, `dat`, `snr` | 无固定签名或来源表达式未解析 | `False` |
| `IKURA/GDL` / `GameRes.Formats.Ikura.MpxOpener` | 无固定值 | `534d324d` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DrsOpener.TryOpen` | `int dir_size = file.View.ReadUInt16 (0);` |
| `DrsOpener.TryOpen` | `byte first = file.View.ReadByte (2);` |
| `DrsOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (dir_offset+12);` |
| `DrsOpener.TryOpen` | `var name = file.View.ReadString (dir_offset, 12);` |
| `DrsOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (dir_offset+12);` |
| `MpxOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "PX10") \|\| file.MaxOffset > uint.MaxValue)` |
| `MpxOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `MpxOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (12);` |
| `MpxOpener.TryOpen` | `var name = file.View.ReadString (dir_offset, 12);` |
| `MpxOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (dir_offset+12);` |
| `MpxOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (dir_offset+16);` |
| `MpxOpener.OpenEntry` | `bool encoded = arc.File.View.AsciiEqual (entry.Offset+entry.Size-0x10, "SECRETFILTER100a");` |
| `MpxOpener.OpenEntry` | `int signature = LittleEndian.ToUInt16 (data, 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ikura.DrsOpener

继承/接口：`ArchiveFormat`。

#### DrsOpener

```csharp
public DrsOpener () {
    Extensions = new string[] { "", "dat", "snr" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset > uint.MaxValue)
        return null;
    int dir_size = file.View.ReadUInt16 (0);
    if (dir_size < 0x20 || 0 != (dir_size & 0xf) || dir_size + 2 >= file.MaxOffset)
        return null;
    byte first = file.View.ReadByte (2);
    if (first <= 0x20)
        return null;
    file.View.Reserve (0, (uint)dir_size + 2);
    int dir_offset = 2;

    uint next_offset = file.View.ReadUInt32 (dir_offset+12);
    if (next_offset > file.MaxOffset || next_offset < dir_size+2)
        return null;

    int count = dir_size / 0x10 - 1;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (dir_offset, 12);
        if (string.IsNullOrEmpty (name))
            return null;
        uint offset = next_offset;
        dir_offset += 0x10;
        next_offset = file.View.ReadUInt32 (dir_offset+12);
        if (next_offset > file.MaxOffset || next_offset < offset)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size = next_offset - offset;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Ikura.IsfOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] Secret ;
```

### GameRes.Formats.Ikura.IsfArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public byte[] Secret ;
```

#### IsfArchive

```csharp
public IsfArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] secret = null)
    : base (arc, impl, dir) {
    Secret = secret;
}
```

### GameRes.Formats.Ikura.MpxOpener

继承/接口：`ArchiveFormat`。

#### MpxOpener

```csharp
public MpxOpener () {
    Extensions = Enumerable.Empty<string>();
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "PX10") || file.MaxOffset > uint.MaxValue)
        return null;
    int count = file.View.ReadInt32 (8);
    if (count <= 0 || count > 0xfffff)
        return null;
    uint index_size = file.View.ReadUInt32 (12);
    if (index_size > file.MaxOffset)
        return null;

    long dir_offset = 0x20;
    var dir = new List<Entry> (count);
    bool has_scripts = false;
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (dir_offset, 12);
        if (string.IsNullOrEmpty (name))
            return null;
        name = name.ToLowerInvariant();
        Entry entry;
        if (name.EndsWith (".isf") || name.EndsWith (".snr"))
        {
            entry = new Entry { Name = name, Type = "script" };
            has_scripts = true;
        }
        else if (name.EndsWith (".bin"))
            entry = new ImageEntry { Name = name };
        else
            entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (dir_offset+12);
        entry.Size   = file.View.ReadUInt32 (dir_offset+16);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        dir_offset += 0x14;
    }
    if (has_scripts)
        return new IsfArchive (file, this, dir);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var isf = arc as IsfArchive;
    if (null == isf || entry.Type != "script" || entry.Size <= 0x10)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    bool encoded = arc.File.View.AsciiEqual (entry.Offset+entry.Size-0x10, "SECRETFILTER100a");
    uint entry_size = entry.Size;
    if (encoded)
    {
        entry_size -= 0x10;
        if (null == isf.Secret)
            isf.Secret = QuerySecret();
        if (null == isf.Secret || 0 == isf.Secret.Length)
            return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    var data = new byte[entry_size];
    arc.File.View.Read (entry.Offset, data, 0, entry_size);
    if (encoded)
    {
        var decoder = new IsfDecoder (isf.Secret);
        decoder.Decode (data);
    }
    int signature = LittleEndian.ToUInt16 (data, 4);
    if (0x9795 == signature)
    {
        ApplyTransformation (data, 8, x => x >> 2 | x << 6);
    }
    else if (0xd197 == signature)
    {
        ApplyTransformation (data, 8, x => ~x);
    }
    else if (0xce89 == signature && 0 != data[6])
    {
        byte key = data[6];
        ApplyTransformation (data, 8, x => x ^ key);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### QuerySecret

```csharp
private byte[] QuerySecret () {
    var options = Query<IsfOptions> (arcStrings.ArcEncryptedNotice);
    return options.Secret;
}
```

#### GetSecret

```csharp
private static byte[] GetSecret (string scheme) {
    byte[] secret;
    if (KnownSecrets.TryGetValue (scheme, out secret))
        return secret;
    return null;
}
```

#### ApplyTransformation

```csharp
private static void ApplyTransformation (byte[] data, int offset, Func<byte, int> method) {
    for (int i = offset; i < data.Length; ++i)
        data[i] = (byte)method (data[i]);
}
```

### GameRes.Formats.Ikura.IsfDecoder

#### 状态与常量

```csharp
byte[]      m_secret ;

static readonly byte[] HexEncodeMap = Encoding.ASCII.GetBytes("G5FXIL094MPRKWCJ3OEBVA7HQ2SU8Y6TZ1ND") ;

static readonly byte[] HexTable = new byte[] {
    0x06, 0x21, 0x19, 0x10, 0x08, 0x01, 0x1E, 0x16, 0x1C, 0x07, 0x15, 0x13, 0x0E, 0x23, 0x12, 0x02,
    0x00, 0x17, 0x04, 0x0F, 0x0C, 0x05, 0x09, 0x22, 0x11, 0x0A, 0x18, 0x0B, 0x1A, 0x1F, 0x1B, 0x14,
    0x0D, 0x03, 0x1D, 0x20,
}
```

#### IsfDecoder

```csharp
public IsfDecoder (byte[] secret) {
    m_secret = secret;
}
```

#### Decode

```csharp
public void Decode (byte[] data) {
    var key_string = CreateKeyString();
    int n = 0;
    for (int i = 0; i < data.Length; )
    {
        DecodePrepare (n++, key_string);
        for (int j = 0; j < key_string.Length && i < data.Length; )
        {
            data[i++] ^= key_string[j++];
        }
    }
}
```

#### CreateKeyString

```csharp
private byte[] CreateKeyString () {
    byte[] len_str = new byte[2];
    for (int i = 0; i < 2; i++)
        len_str[i] = EncodeHex ((byte)(Chr2HexCode (m_secret[0x500 + i]) - Chr2HexCode (m_secret[0x100 + i])));

    byte[] key_string = new byte[Str2Hex (len_str)];
    for (int i = 0; i < key_string.Length; i++)
        key_string[i] = EncodeHex ((byte)(Chr2HexCode (m_secret[0x510 + i]) - Chr2HexCode (m_secret[0x110 + i])));
    return key_string;
}
```

#### DecodePrepare

```csharp
private void DecodePrepare (int index, byte[] key_string) {
    int p = (index & 0x3f) * 16;
    for (int i = 0; i < key_string.Length; i++)
        key_string[i] = EncodeHex ((byte)(Chr2HexCode (key_string[i]) + Chr2HexCode (m_secret[p+i])));
}
```

#### EncodeHex

```csharp
private static byte EncodeHex (byte symbol) {
    if (symbol < 0x80)
        return HexEncodeMap[symbol % 36];
    symbol = (byte)(-(sbyte)symbol % 36);
    if (0 == symbol)
        return HexEncodeMap[0];
    return HexEncodeMap[36 - symbol];
}
```

#### Chr2HexCode

```csharp
private static byte Chr2HexCode (byte chr) {
    return HexTable[Chr2Hex (chr)];
}
```

#### Chr2Hex

```csharp
private static byte Chr2Hex (byte chr) {
    byte code;
    if (chr >= '0' && chr <= '9')
        code = (byte)(chr - '0');
    else if (chr >= 'a' && chr <= 'z')
        code = (byte)(chr - 'a' + 10);
    else if (chr >= 'A' && chr <= 'Z')
        code = (byte)(chr - 'A' + 10);
    else
        code = 0;
    return code;
}
```

#### Str2Hex

```csharp
private static int Str2Hex (byte[] shex) {
    int idec = 0;
    for (int i = 0; i < shex.Length; ++i)
    {
        int mid = Chr2Hex (shex[i]);
        mid <<= ((shex.Length - i - 1) << 2);
        idec |= mid;
    }
    return idec;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ikura/ArcDRS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
