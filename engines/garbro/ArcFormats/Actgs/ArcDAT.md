# Actgs / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/ACTGS` / `GameRes.Formats.Actgs.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `DatOpener.TryOpen` | `if (0 != (file.View.ReadInt32 (4) \| file.View.ReadInt32 (8) \| file.View.ReadInt32 (12)))` |
| `DatOpener.OpenEntry` | `if ('X' != arc.File.View.ReadByte (entry.Offset))` |
| `DatOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset, "PAK "))` |
| `DatOpener.OpenEntry` | `uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `DatOpener.OpenEntry` | `if (entry.Name.HasExtension (".wav") && arc.File.View.AsciiEqual (entry.Offset, "RIFF"))` |
| `DatOpener.ReadEntryHeader` | `var header = arc.File.View.ReadBytes (entry.Offset, length);` |
| `IndexReader.Read` | `uint offset = input.ReadUInt32();` |
| `IndexReader.Read` | `uint size   = input.ReadUInt32();` |
| `IndexReader.Read` | `var name = input.ReadCString (0x18);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Actgs.ActressArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[]  Key ;
```

#### ActressArchive

```csharp
public ActressArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Actgs.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static ActressScheme DefaultScheme = new ActressScheme { KnownKeys = Array.Empty<byte[]>() }
```

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    if (0 != (file.View.ReadInt32 (4) | file.View.ReadInt32 (8) | file.View.ReadInt32 (12)))
        return null;
    const int entry_size = 0x20;
    uint index_length = (uint)(count * entry_size);
    IBinaryStream input = file.CreateStream (0x10, index_length);
    try
    {
        uint first_offset = 0x10u + index_length;
        uint actual_offset = input.Signature;
        byte[] key = null;
        if (actual_offset != first_offset)
        {
            key = FindKey (first_offset, actual_offset);
            if (null == key)
                return null;
            var decrypted = new ByteStringEncryptedStream (input.AsStream, key);
            input = new BinaryStream (decrypted, file.Name);
        }
        var reader = new IndexReader (file.MaxOffset);
        var dir = reader.Read (input, count);
        if (null == dir)
            return null;
        if (null == key)
            return new ArcFile (file, this, dir);
        else
            return new ActressArchive (file, this, dir, key);
    }
    finally
    {
        input.Dispose();
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var actarc = arc as ActressArchive;
    if (null == actarc || null == actarc.Key)
        return base.OpenEntry (arc, entry);
    if (entry.Name.HasExtension (".scr"))
    {
        if ('X' != arc.File.View.ReadByte (entry.Offset))
            return base.OpenEntry (arc, entry);
        var data = new byte[entry.Size];
        arc.File.View.Read (entry.Offset, data, 0, entry.Size);
        Decrypt (data, 1, data.Length-1, actarc.Key);
        data[0] = (byte)'N';
        return new BinMemoryStream (data, entry.Name);
    }
    if (arc.File.View.AsciiEqual (entry.Offset, "PAK "))
    {
        uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+4);
        var input = arc.File.CreateStream (entry.Offset+12, packed_size);
        return new LzssStream (input);
    }
    if (entry.Name.HasExtension (".wav") && arc.File.View.AsciiEqual (entry.Offset, "RIFF"))
    {
        return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    var header = ReadEntryHeader (actarc, entry);
    if (entry.Size <= 0x20)
        return new BinMemoryStream (header, entry.Name);
    var rest = arc.File.CreateStream (entry.Offset+0x20, entry.Size-0x20);
    return new PrefixStream (header, rest);
}
```

#### FindKey

```csharp
byte[] FindKey (uint first_offset, uint actual_offset) {
    var pattern = new byte[4];
    LittleEndian.Pack (first_offset ^ actual_offset, pattern, 0);
    return Array.Find (KnownKeys, k => k.Take (4).SequenceEqual (pattern));
}
```

#### Decrypt

```csharp
internal static void Decrypt (byte[] data, int index, int length, byte[] key) {
    for (int i = 0; i < length; ++i)
    {
        data[index+i] ^= key[i % key.Length];
    }
}
```

#### ReadEntryHeader

```csharp
internal byte[] ReadEntryHeader (ActressArchive arc, Entry entry) {
    uint length = Math.Min (entry.Size, 0x20u);
    var header = arc.File.View.ReadBytes (entry.Offset, length);
    Decrypt (header, 0, header.Length, arc.Key);
    return header;
}
```

### GameRes.Formats.Actgs.IndexReader

#### 状态与常量

```csharp
long            m_arc_length ;

List<Entry>     m_dir = new List<Entry>() ;
```

#### IndexReader

```csharp
public IndexReader (long arc_length) {
    m_arc_length = arc_length;
}
```

#### Read

```csharp
public List<Entry> Read (IBinaryStream input, int count) {
    m_dir.Clear();
    if (m_dir.Capacity < count)
        m_dir.Capacity = count;
    try
    {
        for (int i = 0; i < count; ++i)
        {
            uint offset = input.ReadUInt32();
            uint size   = input.ReadUInt32();
            var name = input.ReadCString (0x18);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = offset;
            entry.Size   = size;
            if (!entry.CheckPlacement (m_arc_length))
                return null;
            m_dir.Add (entry);
        }
        return m_dir;
    }
    catch
    {
        return null;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Actgs/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
