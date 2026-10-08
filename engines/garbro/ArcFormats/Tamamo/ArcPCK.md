# Tamamo / ArcPCK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCK/TAMAMO` / `GameRes.Formats.Tamamo.PckOpener` | `pck` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PckOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "_FILE001"))` |
| `PckOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `PckOpener.TryOpen` | `uint index_length = file.View.ReadUInt32 (0x10);` |
| `PckOpener.TryOpen` | `var index = file.View.ReadBytes (0x14, index_length);` |
| `PckOpener.TryOpen` | `uint size = index.ToUInt32 (pos);` |
| `PckOpener.TryOpen` | `uint enc_size = index.ToUInt32 (pos);` |
| `PckOpener.OpenEntry` | `byte data_type = arc.File.View.ReadByte (pent.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tamamo.PckOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] Key { get; set; }
```

### GameRes.Formats.Tamamo.PckArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Blowfish Encryption ;
```

#### PckArchive

```csharp
public PckArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Encryption = new Blowfish (key);
}
```

### GameRes.Formats.Tamamo.PckOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
PckScheme DefaultScheme = new PckScheme {
    KnownKeys = new Dictionary<string, byte[]>()
}
```

#### PckOpener

```csharp
public PckOpener () {
    ContainedFormats = new[] { "PNG", "DDS", "OGG", "WAV", "TXT", "DAT/GENERIC" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "_FILE001"))
        return null;
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    var key = QueryKey (file.Name);
    if (null == key)
        return null;
    uint index_length = file.View.ReadUInt32 (0x10);
    var index = file.View.ReadBytes (0x14, index_length);
    if (index.Length != index_length)
        return null;
    var bf = new Blowfish (key);
    bf.Decipher (index, index.Length);

    long data_offset = 0x14 + index_length;
    int pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint size = index.ToUInt32 (pos);
        pos += 4;
        int name_end = Array.IndexOf<byte> (index, 0, pos);
        if (-1 == name_end)
            return null;
        var name = Encodings.cp932.GetString (index, pos, name_end-pos);
        pos = name_end+1;
        uint enc_size = index.ToUInt32 (pos);
        pos += 4;
        var entry = Create<PackedEntry> (name);
        entry.Offset = data_offset;
        entry.Size = enc_size;
        entry.UnpackedSize = size;
        entry.IsPacked = enc_size != size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        data_offset += enc_size + 1;
    }
    return new PckArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = (PckArchive)arc;
    var pent = (PackedEntry)entry;
    byte data_type = arc.File.View.ReadByte (pent.Offset);
    Stream input = arc.File.CreateStream (pent.Offset+1, pent.Size);
    if (data_type != 0)
    {
        input = new InputCryptoStream (input, parc.Encryption.CreateDecryptor());
        if (data_type != 3)
        {
            input = new LimitStream (input, pent.UnpackedSize);
        }
        else
        {
            input = new BZip2InputStream (input);
        }
    }
    return input;
}
```

#### QueryKey

```csharp
byte[] QueryKey (string arc_name) {
    if (0 == KnownKeys.Count)
        return null;
    if (1 == KnownKeys.Count)
        return KnownKeys.Values.First();
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    var key = GetKeyForTitle (title);
    if (key != null)
        return key;
    var options = Query<PckOptions> (arcStrings.ArcEncryptedNotice);
    return options.Key;
}
```

#### GetKeyForTitle

```csharp
byte[] GetKeyForTitle (string title) {
    byte[] key = null;
    if (!string.IsNullOrEmpty (title))
        KnownKeys.TryGetValue (title, out key);
    return key;
}
```

## 配套算法与外部条件

- [ArcFormats/Blowfish.cs](../Blowfish.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Tamamo/ArcPCK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
