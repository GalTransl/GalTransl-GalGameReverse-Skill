# Hecate / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/HECATE` / `GameRes.Formats.Hecate.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = (int)reader.ReadInt64();` |
| `DatOpener.TryOpen` | `var name_buf = reader.ReadBytes (0x200);` |
| `DatOpener.TryOpen` | `entry.Size = (uint)reader.ReadInt64();` |
| `DatOpener.TryOpen` | `entry.EncryptedSize = (uint)reader.ReadInt64();` |
| `DatOpener.TryOpen` | `entry.RemainingSize = (uint)reader.ReadInt64();` |
| `DatOpener.TryOpen` | `entry.Offset = reader.ReadInt64();` |
| `DatOpener.TryOpen` | `reader.ReadInt64();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Hecate.DatArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;

public readonly byte[] IV ;
```

#### DatArchive

```csharp
public DatArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key, byte[] iv)
    : base (arc, impl, dir) {
    Key = key;
    IV = iv;
}
```

### GameRes.Formats.Hecate.DatEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint EncryptedSize ;

public uint RemainingSize ;
```

### GameRes.Formats.Hecate.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] DefaultKey = Encoding.UTF8.GetBytes ("プッチンプリン食べたいなー") ;

static readonly ISet<string> ImageArchives = new HashSet<string> {
    "bgimage", "ev", "fgimage", "image"
}

static readonly ISet<string> AudioArchives = new HashSet<string> { "bgm", "se", "voice" }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    var toc_name = Path.ChangeExtension (file.Name, "lib");
    if (!VFS.FileExists (toc_name))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name).ToLowerInvariant();
    bool is_image = ImageArchives.Contains (base_name);
    bool is_audio = AudioArchives.Contains (base_name);
    using (var aes = Aes.Create())
    {
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.PKCS7;
        aes.Key = ResizeKey (DefaultKey, 32);
        aes.IV = ResizeKey (DefaultKey, 16);

        using (var enc = VFS.OpenStream (toc_name))
        using (var dec = new InputCryptoStream (enc, aes.CreateDecryptor()))
        using (var reader = new BinaryReader (dec))
        {
            int count = (int)reader.ReadInt64();
            if (!IsSaneCount (count))
                return null;

            var dir = new List<Entry> (count);
            for (int i = 0; i < count; i++)
            {
                var name_buf = reader.ReadBytes (0x200);
                var name = Binary.GetCString (name_buf, 0, Encoding.UTF8);
                var entry = Create<DatEntry> (name);
                entry.Size = (uint)reader.ReadInt64();
                entry.EncryptedSize = (uint)reader.ReadInt64();
                entry.RemainingSize = (uint)reader.ReadInt64();
                entry.Offset = reader.ReadInt64();
                reader.ReadInt64();
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                if (base_name == "script")
                {
                    entry.Type = "script";
                    entry.Name += ".ks";
                }
                else if (is_image)
                    entry.Type = "image";
                else if (is_audio)
                    entry.Type = "audio";
                dir.Add (entry);
            }

            return new DatArchive (file, this, dir, aes.Key, aes.IV);
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var darc = arc as DatArchive;
    var dent = entry as DatEntry;
    using (var aes = Aes.Create())
    {
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.PKCS7;
        aes.Key = darc.Key;
        aes.IV = darc.IV;

        var buffer = new byte[dent.Size];

        using (var enc = arc.File.CreateStream (dent.Offset, dent.EncryptedSize + dent.RemainingSize))
        using (var lim = new LimitStream (enc, dent.EncryptedSize))
        using (var dec = new InputCryptoStream (lim, aes.CreateDecryptor()))
        using (var mem = new MemoryStream())
        {
            dec.CopyTo (mem);
            mem.Position = 0;
            mem.Read (buffer, 0, (int)mem.Length);
            enc.Read (buffer, (int)mem.Length, (int)dent.RemainingSize);
            return new BinMemoryStream (buffer);
        }
    }
}
```

#### ResizeKey

```csharp
byte[] ResizeKey (byte[] key, int size) {
    var output = new byte[size];
    for (int i = 0; i < key.Length; i++)
    {
        output[i % output.Length] ^= key[i];
    }
    return output;
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Hecate/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
