# KiriKiri / CryptAlgorithms：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ICrypt.ReadName` | `int name_size = header.ReadInt16();` |
| `ICrypt.EntryReadFilter` | `uint signature = header.ToUInt32 (0);` |
| `ICrypt.EntryReadFilter` | `if (header.AsciiEqual (8, "WAVE"))` |
| `ICrypt.EntryReadFilter` | `else if (header.AsciiEqual (8, "WEBP"))` |
| `ICrypt.EntryReadFilter` | `else if (header.AsciiEqual (8, "AVI "))` |
| `ICrypt.DecompressMdf` | `entry.UnpackedSize = mdf_header.ToUInt32 (0);` |
| `ICrypt.DecompressLz4` | `info.SetBlockSize (input.ReadByte());` |
| `ICrypt.DecompressLz4` | `long length = header.ToUInt32 (0);` |
| `ICrypt.DecompressLz4` | `length \|= (long)header.ToUInt32 (0) << 32;` |
| `ICrypt.DecompressLz4` | `info.DictionaryId = header.ToInt32 (0);` |
| `ICrypt.DecompressLz4` | `input.ReadByte();` |
| `ICrypt.DecryptScript` | `reader.ReadInt64();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KiriKiri.ICrypt

#### 状态与常量

```csharp
public virtual bool HashAfterCrypt { get { return false; } }

public bool StartupTjsNotEncrypted { get; set; }

public bool ObfuscatedIndex { get; set; }

static readonly Dictionary<uint, string> FileTypesMap = new Dictionary<uint, string> {
    { 0x5367674f, "audio" },
    { 0x46464952, "audio" },
    { 0x474e5089, "image" },
    { 0xe0ffd8ff, "image" },
    { 0x30474c54, "image" },
    { 0x35474c54, "image" },
    { 0x36474c54, "image" },
    { 0x35474cab, "image" },
    { 0x584d4b4a, "image" },
}
```

#### Decrypt

```csharp
public virtual byte Decrypt (Xp3Entry entry, long offset, byte value) {
    byte[] buffer = new byte[1] { value };
    Decrypt (entry, offset, buffer, 0, 1);
    return buffer[0];
}
```

#### Decrypt

```csharp
public abstract void Decrypt (Xp3Entry entry, long offset, byte[] values, int pos, int count) ;
```

#### Encrypt

```csharp
public virtual void Encrypt (Xp3Entry entry, long offset, byte[] values, int pos, int count) {
    throw new NotImplementedException (Strings.arcStrings.MsgEncNotImplemented);
}
```

#### ReadName

```csharp
public virtual string ReadName (BinaryReader header) {
    int name_size = header.ReadInt16();
    if (name_size > 0 && name_size <= 0x100)
        return new string (header.ReadChars (name_size));
    else
        return null;
}
```

#### EntryReadFilter

```csharp
public virtual Stream EntryReadFilter (Xp3Entry entry, Stream input) {
    if (entry.UnpackedSize <= 5 || "audio" == entry.Type)
        return input;

    var header = new byte[5];
    input.Read (header, 0, 5);
    uint signature = header.ToUInt32 (0);
    GuessEntryTypeBySignature (entry, signature);
    if (0x46464952 == signature)
    {
        if (entry.UnpackedSize >= 12)
        {
            var header_ext = new byte[12];
            Array.Copy (header, header_ext, header.Length);
            input.Read (header_ext, header.Length, header_ext.Length-header.Length);
            header = header_ext;
            if (header.AsciiEqual (8, "WAVE"))
                entry.Type = "audio";
            else if (header.AsciiEqual (8, "WEBP"))
                entry.Type = "image";
            else if (header.AsciiEqual (8, "AVI "))
                entry.Type = "video";
        }
    }
    if (0x184D2204 == signature)
    {

        return DecompressLz4 (entry, header, input);
    }
    if (0x66646D == signature)
    {
        return DecompressMdf (entry, header, input);
    }
    if ((signature & 0xFF00FFFFu) == 0xFF00FEFEu && header[2] < 3 && 0xFE == header[4])
        return DecryptScript (header[2], input, entry.UnpackedSize);

    if (!input.CanSeek)
        return new PrefixStream (header, input);
    input.Position = 0;
    return input;
}
```

#### DecompressMdf

```csharp
internal Stream DecompressMdf (Xp3Entry entry, byte[] header, Stream input) {
    if (header.Length != 5)
        throw new ArgumentException ("Invalid header length for DecompressMdf", "header");
    var mdf_header = new byte[4] { header[4], 0, 0, 0 };
    input.Read (mdf_header, 1, 3);
    entry.UnpackedSize = mdf_header.ToUInt32 (0);
    entry.IsPacked = true;
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

#### DecompressLz4

```csharp
internal Stream DecompressLz4 (Xp3Entry entry, byte[] header, Stream input) {
    if (header.Length != 5)
        throw new ArgumentException ("Invalid header length for DecompressLz4", "header");
    var info = new Lz4FrameInfo (header[4]);
    info.SetBlockSize (input.ReadByte());
    if (info.HasContentLength)
    {
        input.Read (header, 0, 4);
        long length = header.ToUInt32 (0);
        input.Read (header, 0, 4);
        length |= (long)header.ToUInt32 (0) << 32;
        info.OriginalLength = length;
        entry.UnpackedSize = (uint)length;
        entry.IsPacked = true;
    }
    if (info.HasDictionary)
    {
        input.Read (header, 0, 4);
        info.DictionaryId = header.ToInt32 (0);
    }
    input.ReadByte();
    return new Lz4Stream (input, info);
}
```

#### DecryptScript

```csharp
internal Stream DecryptScript (int enc_type, Stream input, uint unpacked_size) {
    using (var reader = new BinaryReader (input, Encoding.Unicode, true))
    {
        if (2 == enc_type)
        {
            reader.ReadInt64();
            reader.ReadInt64();
            return new ZLibStream (input, CompressionMode.Decompress);
        }
        var output = new MemoryStream ((int)unpacked_size+2);
        using (var writer = new BinaryWriter (output, Encoding.Unicode, true))
        {
            writer.Write ('\xFEFF');
            int c;
            if (1 == enc_type)
            {
                while ((c = reader.Read()) != -1)
                {
                    c = (c & 0xAAAA) >> 1 | (c & 0x5555) << 1;
                    writer.Write ((char)c);
                }
            }
            else
            {
                while ((c = reader.Read()) != -1)
                {
                    if (c >= 0x20)
                    {
                        c = c ^ (((c & 0xFE) << 8) ^ 1);
                        writer.Write ((char)c);
                    }
                }
            }
        }
        output.Position = 0;
        input.Dispose();
        return output;
    }
}
```

#### GuessEntryTypeBySignature

```csharp
internal void GuessEntryTypeBySignature (Entry entry, uint signature) {
    if (FileTypesMap.TryGetValue (signature, out var type))
        entry.Type = type;
}
```

### GameRes.Formats.KiriKiri.NoCrypt

继承/接口：`ICrypt`。

#### Decrypt

```csharp
public override byte Decrypt (Xp3Entry entry, long offset, byte value) {
    return value;
}
```

#### Decrypt

```csharp
public override void Decrypt (Xp3Entry entry, long offset, byte[] values, int pos, int count) {
    return;
}
```

#### Encrypt

```csharp
public override void Encrypt (Xp3Entry entry, long offset, byte[] values, int pos, int count) {
    return;
}
```

## 配套算法与外部条件

- [ArcFormats/KiriKiri/ArcXP3.cs](ArcXP3.md)：本页引用的随包算法资料。
- [ArcFormats/Lz4Stream.cs](../Lz4Stream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/KiriKiri/CryptAlgorithms.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
