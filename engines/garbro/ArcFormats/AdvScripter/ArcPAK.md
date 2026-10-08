# AdvScripter / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/MD002` / `GameRes.Formats.AdvScripter.PakOpener` | `pak` | `4d443030` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (file.View.ReadByte (4) != '2' \|\| !file.View.AsciiEqual (0x21, "00V"))` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (0x24);` |
| `PakOpener.TryOpen` | `int version = file.View.ReadByte (0x20) - '0';` |
| `PakOpener.TryOpen` | `entry.IsPacked     = buffer.ToInt32 (0x20) != 0;` |
| `IndexReader.IndexReader` | `Offset       = buffer.ToUInt32 (0x24);` |
| `IndexReader.IndexReader` | `UnpackedSize = buffer.ToUInt32 (0x28);` |
| `IndexReader.IndexReader` | `PackedSize   = buffer.ToUInt32 (0x2C);` |
| `IndexReader.IndexReader` | `m_key = file.View.ReadUInt32 (0x1C);` |
| `IndexReader.IndexReader` | `Offset       = buffer.ToUInt32 (0x24) ^ m_key;` |
| `IndexReader.IndexReader` | `UnpackedSize = buffer.ToUInt32 (0x28) ^ m_key;` |
| `IndexReader.IndexReader` | `PackedSize   = buffer.ToUInt32 (0x2C) ^ m_key;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AdvScripter.MdArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly int Version ;
```

#### MdArchive

```csharp
public MdArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version)
    : base (arc, impl, dir) {
    Version = version;
}
```

### GameRes.Formats.AdvScripter.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadByte (4) != '2' || !file.View.AsciiEqual (0x21, "00V"))
        return null;
    int count = file.View.ReadInt32 (0x24);
    if (!IsSaneCount (count))
        return null;
    int version = file.View.ReadByte (0x20) - '0';
    if (version < 1 || version > 9)
        return null;
    var index_entry = new IndexReader (file, version);
    var buffer = new byte[0x30];
    uint index_offset = 0x28;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_offset, buffer, 0, 0x30);
        index_entry.Decrypt (buffer);
        var name = Binary.GetCString (buffer, 0, 0x20);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset       = index_entry.Offset;
        entry.UnpackedSize = index_entry.UnpackedSize;
        entry.Size         = index_entry.PackedSize;
        entry.IsPacked     = buffer.ToInt32 (0x20) != 0;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x30;
    }
    return new MdArchive (file, this, dir, version);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var mdarc = arc as MdArchive;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (mdarc != null && (mdarc.Version >= 5 && mdarc.Version <= 8))
        input = new XoredStream (input, 0xFF);
    var pent = entry as PackedEntry;
    if (pent != null && pent.IsPacked)
        input = new LzssStream (input);
    return input;
}
```

### GameRes.Formats.AdvScripter.PakOpener.IndexReader

#### 状态与常量

```csharp
public uint Offset ;

public uint PackedSize ;

public uint UnpackedSize ;

public readonly Action<byte[]> Decrypt ;

private uint m_key ;
```

#### IndexReader

```csharp
public IndexReader (ArcView file, int version) {
    if (1 == version || 5 == version)
    {
        Decrypt = buffer => {
            Offset       = buffer.ToUInt32 (0x24);
            UnpackedSize = buffer.ToUInt32 (0x28);
            PackedSize   = buffer.ToUInt32 (0x2C);
        };
        return;
    }
    else if (2 == version || 6 == version)
        m_key = uint.MaxValue;
    else
        m_key = file.View.ReadUInt32 (0x1C);

    Action<byte[]> read = buffer => {
        Offset       = buffer.ToUInt32 (0x24) ^ m_key;
        UnpackedSize = buffer.ToUInt32 (0x28) ^ m_key;
        PackedSize   = buffer.ToUInt32 (0x2C) ^ m_key;
    };
    Action transform;
    if (9 == version)
    {
        transform = () => {
            Offset       = (Offset       & 0xFFFF) << 15 | Offset       >> 17;
            UnpackedSize = (UnpackedSize & 0xFFFF) << 14 | UnpackedSize >> 18;
            PackedSize   = (PackedSize   & 0xFFFF) << 13 | PackedSize   >> 19;
        };
    }
    else
    {
        transform = () => {
            Offset       >>= 1;
            UnpackedSize >>= 2;
            PackedSize   >>= 3;
        };
    }

    Action<byte[]> decrypt_name = buffer => { };
    if (9 == version || 4 == version || 8 == version)
    {
        var key_bytes = new byte[4];
        LittleEndian.Pack (m_key, key_bytes, 0);
        decrypt_name = buffer => {
            for (int i = 0; i < 28; ++i)
                buffer[i] ^= key_bytes[i & 3];
        };
    }
    Decrypt = buffer => {
        read (buffer);
        transform ();
        decrypt_name (buffer);
    };
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/AdvScripter/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
