# Actgs / ArcCG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CG/ACTGS/2` / `GameRes.Formats.Actgs.ArcCgOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `CG/ACTGS` / `GameRes.Formats.Actgs.CgOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CgOpener.TryOpen` | `var pattern = file.View.ReadBytes (4, 8);` |
| `CgOpener.TryOpen` | `uint signature_key = key.ToUInt32 (0);` |
| `CgOpener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (0) ^ signature_key);` |
| `ArcCgOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `ArcCgOpener.TryOpen` | `var pattern = file.View.ReadBytes (0x1018, 8);` |
| `ArcCgOpener.TryOpen` | `uint size = buffer.ToUInt32 (0);` |
| `ArcCgOpener.OpenEntry` | `if (header.AsciiEqual ("BM"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Actgs.CgOpener

继承/接口：`DatOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var pattern = file.View.ReadBytes (4, 8);
    var key = FindKey (4, pattern);
    if (null == key)
        return null;
    uint signature_key = key.ToUInt32 (0);
    int count = (int)(file.View.ReadUInt32 (0) ^ signature_key);
    if (!IsSaneCount (count))
        return null;
    uint index_size = 32 * (uint)count;
    using (var enc = file.CreateStream (0x10, index_size))
    using (var input = new ByteStringEncryptedStream (enc, key))
    using (var index = new BinaryStream (input, file.Name))
    {
        var reader = new IndexReader (file.MaxOffset);
        var dir = reader.Read (index, count);
        if (null == dir)
            return null;
        return new ActressArchive (file, this, dir, key);
    }
}
```

#### FindKey

```csharp
internal byte[] FindKey (int offset, byte[] pattern) {
    return Array.Find (KnownKeys, k => KeySequence (k).Skip (offset).Take (pattern.Length).SequenceEqual (pattern));
}
```

#### KeySequence

```csharp
internal static IEnumerable<byte> KeySequence (byte[] key) {
    for (;;)
    {
        for (int i = 0; i < key.Length; ++i)
            yield return key[i];
    }
}
```

### GameRes.Formats.Actgs.ArcCgOpener

继承/接口：`CgOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 0x1020)
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    var pattern = file.View.ReadBytes (0x1018, 8);
    var key = FindKey (0x18, pattern);
    if (null == key)
        return null;
    var dir = new List<Entry> (count);
    var buffer = new byte[0x20];
    long offset = 0x1000;
    while (file.View.Read (offset, buffer, 0, 0x20) == 0x20)
    {
        offset += 0x20;
        Decrypt (buffer, 0, 0x20, key);
        uint size = buffer.ToUInt32 (0);
        var name = Binary.GetCString (buffer, 4);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        offset += (size + 0xFu) & ~0xFu;
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    return new ActressArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var actarc = arc as ActressArchive;
    if (null == actarc || null == actarc.Key)
        return base.OpenEntry (arc, entry);
    var header = ReadEntryHeader (actarc, entry);
    Stream input;
    if (entry.Size <= 0x20)
        input = new BinMemoryStream (header, entry.Name);
    else
        input = new PrefixStream (header, arc.File.CreateStream (entry.Offset+0x20, entry.Size-0x20));
    if (header.AsciiEqual ("BM"))
        return input;
    input.Position = 4;
    return new LzssStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/Actgs/ArcDAT.cs](ArcDAT.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Actgs/ArcCG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
