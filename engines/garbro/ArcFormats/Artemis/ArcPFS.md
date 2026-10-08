# Artemis / ArcPFS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PFS` / `GameRes.Formats.Artemis.PfsOpener` | `pfs`, `ipd`, `000`, `001`, `002`, `003`, `004`, `005`, `010` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PfsOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "pf"))` |
| `PfsOpener.TryOpen` | `int version = file.View.ReadByte (2) - '0';` |
| `PfsOpener.OpenPf` | `uint index_size = file.View.ReadUInt32 (3);` |
| `PfsOpener.OpenPf` | `int count = file.View.ReadInt32 (7);` |
| `PfsOpener.OpenPf` | `var index = file.View.ReadBytes (7, index_size);` |
| `PfsOpener.OpenPf` | `int name_length = index.ToInt32 (index_offset);` |
| `PfsOpener.OpenPf` | `entry.Offset = index.ToUInt32 (index_offset);` |
| `PfsOpener.OpenPf` | `entry.Size   = index.ToUInt32 (index_offset+4);` |
| `PfsOpener.OpenPf2` | `uint index_size = file.View.ReadUInt32 (3);` |
| `PfsOpener.OpenPf2` | `int count = file.View.ReadInt32 (0xB);` |
| `PfsOpener.OpenPf2` | `var index = file.View.ReadBytes (7, index_size);` |
| `PfsOpener.OpenPf2` | `int name_length = index.ToInt32 (index_offset);` |
| `PfsOpener.OpenPf2` | `entry.Offset = index.ToUInt32 (index_offset);` |
| `PfsOpener.OpenPf2` | `entry.Size   = index.ToUInt32 (index_offset+4);` |
| `PfsOpener.OpenPf0` | `int count = file.View.ReadInt32 (3);` |
| `PfsOpener.OpenPf0` | `var name = file.View.ReadString (offset, 0x104, Encoding.ASCII);` |
| `PfsOpener.OpenPf0` | `entry.Offset = file.View.ReadUInt32 (offset + 0x104);` |
| `PfsOpener.OpenPf0` | `entry.Size   = file.View.ReadUInt32 (offset + 0x108);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Artemis.PfsOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
EncodingSetting PfsEncoding = new EncodingSetting ("PFSEncodingCP", "DefaultEncoding") ;
```

#### PfsOpener

```csharp
public PfsOpener () {
    Extensions = new string[] { "pfs", "ipd", "000", "001", "002", "003", "004", "005", "010" };
    ContainedFormats = new string[] { "PNG", "JPEG", "IPT", "OGG", "TXT", "SCR" };
    Settings = new[] { PfsEncoding };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "pf"))
        return null;
    int version = file.View.ReadByte (2) - '0';
    switch (version)
    {
    case 6:
    case 8:
        try
        {
            return OpenPf (file, version, PfsEncoding.Get<Encoding>());
        }
        catch (System.ArgumentException)
        {
            return OpenPf (file, version, GetAltEncoding());
        }
    case 2:     return OpenPf2 (file);
    case 0:     return OpenPf0 (file);
    default:    return null;
    }
}
```

#### OpenPf

```csharp
ArcFile OpenPf (ArcView file, int version, Encoding encoding) {
    uint index_size = file.View.ReadUInt32 (3);
    int count = file.View.ReadInt32 (7);
    if (!IsSaneCount (count) || 7L + index_size > file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (7, index_size);
    int index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_length = index.ToInt32 (index_offset);
        var name = encoding.GetString (index, index_offset+4, name_length);
        index_offset += name_length + 8;
        var entry = Create<Entry> (name);
        entry.Offset = index.ToUInt32 (index_offset);
        entry.Size   = index.ToUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 8;
        dir.Add (entry);
    }
    if (version != 8 && version != 9 && version != 4 && version != 5)
        return new ArcFile (file, this, dir);

    using (var sha1 = SHA1.Create())
    {
        var key = sha1.ComputeHash (index);
        return new PfsArchive (file, this, dir, key);
    }
}
```

#### OpenPf2

```csharp
ArcFile OpenPf2 (ArcView file) {
    uint index_size = file.View.ReadUInt32 (3);
    int count = file.View.ReadInt32 (0xB);
    if (!IsSaneCount (count) || 7L + index_size > file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (7, index_size);
    int index_offset = 8;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_length = index.ToInt32 (index_offset);
        var name = Encodings.cp932.GetString (index, index_offset+4, name_length);
        index_offset += name_length + 0x10;
        var entry = Create<Entry> (name);
        entry.Offset = index.ToUInt32 (index_offset);
        entry.Size   = index.ToUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 8;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenPf0

```csharp
ArcFile OpenPf0 (ArcView file) {
    int count = file.View.ReadInt32 (3);
    if (!IsSaneCount (count))
        return null;
    int offset = 7;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (offset, 0x104, Encoding.ASCII);
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (offset + 0x104);
        entry.Size   = file.View.ReadUInt32 (offset + 0x108);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        offset += 0x10C;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = arc as PfsArchive;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null == parc)
        return input;
    return new ByteStringEncryptedStream (input, parc.Key);
}
```

#### GetAltEncoding

```csharp
Encoding GetAltEncoding () {
    var enc = PfsEncoding.Get<Encoding>();
    if (enc.CodePage == 932)
        return Encoding.UTF8;
    else
        return Encodings.cp932;
}
```

### GameRes.Formats.Artemis.PfsArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### PfsArchive

```csharp
public PfsArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

## 配套算法与外部条件

- [ArcFormats/ResourceSettings.cs](../ResourceSettings.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Artemis/ArcPFS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
