# aNCHOR / ArcFPD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FPD` / `GameRes.Formats.Anchor.FpdOpener` | `fpd` | `46504400` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `FpdOpener.TryOpen` | `int version = Binary.BigEndian(file.View.ReadInt32(4));` |
| `FpdOpener.TryOpen` | `int count = (int)Binary.BigEndian(file.View.ReadInt64(8));` |
| `FpdOpener.TryOpen` | `long data_start = Binary.BigEndian(file.View.ReadInt64(0x10));` |
| `FpdOpener.TryOpen` | `long name_offset = Binary.BigEndian(reader.ReadInt64());` |
| `FpdOpener.TryOpen` | `long data_offset = Binary.BigEndian(reader.ReadInt64());` |
| `FpdOpener.TryOpen` | `long size = Binary.BigEndian(reader.ReadInt64());` |
| `FpdOpener.TryOpen` | `long unpacked_size = Binary.BigEndian(reader.ReadInt64());` |
| `FpdOpener.TryOpen` | `var name_block = reader.ReadBytes((int)(data_start - offset - count * 32));` |
| `FpdOpener.OpenEntry` | `uint last = Binary.BigEndian(BitConverter.ToUInt32(buf, 0));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Anchor.FpdArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### FpdArchive

```csharp
public FpdArchive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key) : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Anchor.FpdOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
FpdScheme DefaultScheme = new FpdScheme() ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    int version = Binary.BigEndian(file.View.ReadInt32(4));
    if (version != 2)
        return null;

    int count = (int)Binary.BigEndian(file.View.ReadInt64(8));
    if (!IsSaneCount(count))
        return null;

    long data_start = Binary.BigEndian(file.View.ReadInt64(0x10));
    long offset = 0x38;
    if (data_start < count * 32 + offset)
        return null;
    uint index_size = (uint)(data_start - offset);

    var key = DefaultScheme.ArchiveKey;
    var dir = new List<Entry>(count);

    using (var input = file.CreateStream(offset, (uint)(data_start - offset)))
    using (var decrypted = new ByteStringEncryptedStream(input, key))
    using (var reader = new BinaryReader(decrypted)) {
        var name_offsets = new List<long>(count);
        for (int i = 0; i < count; i++) {
            long name_offset = Binary.BigEndian(reader.ReadInt64());
            long data_offset = Binary.BigEndian(reader.ReadInt64());
            long size = Binary.BigEndian(reader.ReadInt64());
            long unpacked_size = Binary.BigEndian(reader.ReadInt64());

            var entry = new PackedEntry {
                Offset = data_start + data_offset,
                Size = (uint)size,
                UnpackedSize = (uint)unpacked_size,
                IsPacked = unpacked_size != 0
            };
            if (!entry.CheckPlacement(file.MaxOffset))
                return null;
            dir.Add(entry);
            name_offsets.Add(name_offset);
        }
        var name_block = reader.ReadBytes((int)(data_start - offset - count * 32));
        using (var mem = new MemoryStream(name_block))
        using (var stream = new ZLibStream(mem, CompressionMode.Decompress))
        using (var output = new MemoryStream()) {
            stream.CopyTo(output);
            var names = output.ToArray();
            for (int i = 0; i < count; i++) {
                dir[i].Name = Binary.GetCString(names, (int)name_offsets[i], Encoding.UTF8);
                dir[i].Type = FormatCatalog.Instance.GetTypeFromName(dir[i].Name);
                if (dir[i].Name.EndsWith(".epk"))
                    dir[i].Type = "script";
            }
        }
        return new FpdArchive(file, this, dir, key);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var farc = arc as FpdArchive;
    var pent = entry as PackedEntry;
    Stream input = farc.File.CreateStream(entry.Offset, entry.Size);
    input = new ByteStringEncryptedStream(input, farc.Key);
    if (pent.IsPacked)
        input = new ZLibStream(input, CompressionMode.Decompress);
    if (pent.Name.EndsWith(".epk")) {
        var mem = new MemoryStream();
        input.CopyTo(mem);
        mem.Seek(-0x20, SeekOrigin.End);
        var buf = new byte[4];
        mem.Read(buf, 0, 4);
        uint last = Binary.BigEndian(BitConverter.ToUInt32(buf, 0));
        mem.Seek(0, SeekOrigin.Begin);

        var key = Encoding.UTF8.GetBytes(Path.GetFileNameWithoutExtension(pent.Name));
        var encryption = new Mk2Blowfish(key, DefaultScheme.EpkContext);
        input = new InputCryptoStream(mem, encryption.CreateDecryptor());
        input = new LimitStream(input, last);
    }
    return input;
}
```

### GameRes.Formats.Anchor.FpdScheme

继承/接口：`ResourceScheme`。

#### 状态与常量

```csharp
public byte[] ArchiveKey ;

public byte[] EpkContext ;
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。
- [ArcFormats/aNCHOR/Blowfish.cs](Blowfish.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/aNCHOR/ArcFPD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
