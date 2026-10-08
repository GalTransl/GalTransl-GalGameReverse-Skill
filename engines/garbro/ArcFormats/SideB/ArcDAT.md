# SideB / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/SIDEB` / `GameRes.Formats.AttacheCase.DatOpener` | `dat` | `06000300` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint header_size = file.View.ReadUInt32 (0x1C);` |
| `DatOpener.TryOpen` | `var iv = file.View.ReadBytes (0x20, 32);` |
| `DatOpener.TryOpen` | `iv = file.View.ReadBytes (data_offset - 32, 32);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AttacheCase.AtcArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;

public readonly byte[] IV ;

public readonly uint DataOffset ;
```

#### AtcArchive

```csharp
public AtcArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key, byte[] iv, uint data_offset)
    : base (arc, impl, dir) {
    Key = key;
    IV = iv;
    DataOffset = data_offset;
}
```

### GameRes.Formats.AttacheCase.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] DefaultKey = Encoding.ASCII.GetBytes ("OTG") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint header_size = file.View.ReadUInt32 (0x1C);
    uint data_offset = 0x60 + header_size + header_size % 32;
    if (data_offset >= file.MaxOffset)
        return null;

    var key = new byte[32];
    Buffer.BlockCopy (DefaultKey, 0, key, 0, Math.Min (DefaultKey.Length, key.Length));
    var iv = file.View.ReadBytes (0x20, 32);

    var dir = new List<Entry> ();
    using (var aes = Rijndael.Create())
    {
        aes.BlockSize = 256;
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.Zeros;
        aes.Key = key;
        aes.IV = iv;

        using (var enc = file.CreateStream (0x40))
        using (var dec = new InputCryptoStream (enc, aes.CreateDecryptor()))
        {
            var info = new byte[header_size];
            dec.Read (info, 0, info.Length);
            string info_str = Encoding.UTF8.GetString (info);
            var matches = Regex.Matches (info_str, @"^U_\d+:([^\t]*)\t(\d*)\t", RegexOptions.Multiline);
            uint offset = 0;
            foreach (Match match in matches)
            {
                string name = match.Groups[1].Value;
                uint size = uint.Parse (match.Groups[2].Value);
                var entry = Create<Entry> (name);
                entry.Offset = offset;
                entry.Size = size;
                offset += size;
                dir.Add (entry);
            }
        }
    }

    if (dir.Count == 0)
        return null;
    iv = file.View.ReadBytes (data_offset - 32, 32);
    return new AtcArchive (file, this, dir, key, iv, data_offset);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var aarc = arc as AtcArchive;
    using (var aes = Rijndael.Create())
    {
        aes.BlockSize = 256;
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.Zeros;
        aes.Key = aarc.Key;
        aes.IV = aarc.IV;

        Stream input = aarc.File.CreateStream (aarc.DataOffset);
        input = new InputCryptoStream (input, aes.CreateDecryptor());
        input = new ZLibStream (input, CompressionMode.Decompress);
        StreamSkip (input, (int)entry.Offset);
        return new LimitStream (input, entry.Size);
    }
}
```

#### StreamSkip

```csharp
void StreamSkip (Stream input, int bytesToSkip) {
    byte[] buffer = new byte[4096];
    int totalRead = 0;

    while (totalRead < bytesToSkip)
    {
        int toRead = Math.Min (buffer.Length, bytesToSkip - totalRead);
        int read = input.Read (buffer, 0, toRead);

        if (read == 0) break;
        totalRead += read;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/SideB/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
