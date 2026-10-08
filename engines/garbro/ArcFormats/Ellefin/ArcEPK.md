# Ellefin / ArcEPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `EPK/Ellefin` / `GameRes.Formats.Ellefin.EpkOpener` | `epk` | `45504b1a`, `45504b1e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `EpkOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "EPK"))` |
| `EpkOpener.TryOpen` | `int flags = file.View.ReadByte (3);` |
| `EpkOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `EpkOpener.TryOpen` | `var index = file.View.ReadBytes (8, index_size);` |
| `EpkIndexReader.Read` | `int count = m_index.ReadInt32();` |
| `EpkIndexReader.ParseEncryptedIndex` | `int header_length = m_index.ReadUInt8();` |
| `EpkIndexReader.ParseEncryptedIndex` | `m_info.Prefix = m_index.ReadBytes (header_length);` |
| `EpkIndexReader.ParseEncryptedIndex` | `m_wide_offset = m_index.ReadByte() != 0;` |
| `EpkIndexReader.ParseEncryptedIndex` | `int name_tree_length = m_index.ReadInt32();` |
| `EpkIndexReader.ParseRegularIndex` | `int name_length = m_index.ReadByte();` |
| `EpkIndexReader.ParseRegularIndex` | `var name = m_index.ReadCString (name_length);` |
| `EpkIndexReader.ReadEntry` | `entry.Offset        = m_index.ReadUInt32();` |
| `EpkIndexReader.ReadEntry` | `entry.Size          = m_index.ReadUInt32();` |
| `EpkIndexReader.ReadEntry` | `entry.UnpackedSize  = m_index.ReadUInt32();` |
| `EpkIndexReader.TraverseIndex` | `int count = m_index.ReadByte();` |
| `EpkIndexReader.TraverseIndex` | `byte next_letter = m_index.ReadUInt8();` |
| `EpkIndexReader.TraverseIndex` | `int next_offset = m_wide_offset ? m_index.ReadInt32() : (int)m_index.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ellefin.EpkEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int DirIndex ;
```

### GameRes.Formats.Ellefin.EpkInfo

继承/接口：`LpkInfo`。

#### 状态与常量

```csharp
public bool IndexEncrypted ;
```

### GameRes.Formats.Ellefin.EpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly EncryptionScheme DefaultScheme = new EncryptionScheme {
    BaseKey = new LpkOpener.Key (0xA6BD375E, 0x375D916B), ContentXor = 0xD9, RotatePattern = 0x17236351
}
```

#### EpkOpener

```csharp
public EpkOpener () {
    Signatures = new uint[] { 0x1A4B5045, 0x1E4B5045, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "EPK"))
        return null;
    int flags = file.View.ReadByte (3);
    if (0 == (flags & 2))
        return null;
    var scheme = DefaultScheme;
    uint arc_key   = scheme.BaseKey.Key1;
    uint index_key = scheme.BaseKey.Key2;
    var arc_info = new EpkInfo
    {
        AlignedOffset = 0 != (flags & 1),
        Flag1         = 0 != (flags & 2),
        WholeCrypt    = 0 != (flags & 4),
        IsEncrypted   = 0 != (flags & 8),
        IndexEncrypted = 0 != (flags & 0xF0),
        PackedEntries = true,
    };
    uint index_size = file.View.ReadUInt32 (4);
    if (arc_info.IndexEncrypted)
    {
        var base_name = Path.GetFileNameWithoutExtension (file.Name).ToUpperInvariant();
        var name_bytes = Encodings.cp932.GetBytes (base_name);
        int back = name_bytes.Length-1;
        for (int i = 0; i < name_bytes.Length; ++i)
        {
            arc_key   ^= name_bytes[back-i];
            index_key ^= name_bytes[i];
            arc_key    = Binary.RotR (arc_key, 8);
            index_key  = Binary.RotL (index_key, 8);
        }
        index_size ^= index_key;
    }
    arc_info.Key = arc_key;
    if (arc_info.AlignedOffset)
        index_size <<= 11;
    if (!arc_info.IndexEncrypted || arc_info.AlignedOffset)
        index_size -= 8;
    if (index_size >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (8, index_size);
    if (arc_info.IndexEncrypted)
        scheme.DecryptIndex (index, index.Length, index_key);

    var reader = new EpkIndexReader (arc_info);
    var dir = reader.Read (index);
    if (null == dir)
        return null;
    if (arc_info.IndexEncrypted)
        return new LuciArchive (file, this, dir, scheme, arc_info);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    var epk_ent = entry as PackedEntry;
    if (null == epk_ent)
        return input;
    if (epk_ent.IsPacked)
    {
        input = new LzssStream (input);
    }
    var epk = arc as LuciArchive;
    if (null == epk || (!epk.Info.WholeCrypt && !epk.Info.IsEncrypted && null == epk.Info.Prefix))
        return input;
    var data = new byte[epk_ent.UnpackedSize];
    using (input)
    {
        input.Read (data, 0, data.Length);
    }
    if (epk.Info.WholeCrypt)
    {
        epk.Scheme.DecryptContent (data);
    }
    if (epk.Info.IsEncrypted)
    {
        int count = Math.Min (data.Length, 0x10);
        epk.Scheme.DecryptEntry (data, count, epk.Info.Key);
    }
    var header = epk.Info.Prefix;
    if (header != null && header.Length <= data.Length)
        Buffer.BlockCopy (header, 0, data, 0, header.Length);
    return new BinMemoryStream (data, entry.Name);
}
```

### GameRes.Formats.Ellefin.EpkIndexReader

#### 状态与常量

```csharp
IBinaryStream   m_index ;

EpkInfo         m_info ;

List<Entry>     m_dir ;

byte[]          m_name_buf ;

bool            m_wide_offset ;
```

#### EpkIndexReader

```csharp
public EpkIndexReader (EpkInfo info) {
    m_info = info;
}
```

#### Read

```csharp
public List<Entry> Read (byte[] index) {
    using (m_index = new BinMemoryStream (index))
    {
        int count = m_index.ReadInt32();
        if (!ArchiveFormat.IsSaneCount (count))
            return null;
        m_dir = new List<Entry> (count);
        if (m_info.IndexEncrypted)
            ParseEncryptedIndex (count);
        else
            ParseRegularIndex (count);
        return m_dir.Count > 0 ? m_dir : null;
    }
}
```

#### ParseEncryptedIndex

```csharp
void ParseEncryptedIndex (int count) {
    int header_length = m_index.ReadUInt8();
    if (0 != header_length)
    {
        m_info.Prefix = m_index.ReadBytes (header_length);
    }
    m_wide_offset = m_index.ReadByte() != 0;
    int name_tree_length = m_index.ReadInt32();
    var entry_table_offset = m_index.Position + name_tree_length;

    m_name_buf = new byte[0x110];
    TraverseIndex (m_index.Position, 0);
    if (m_dir.Count != count)
        throw new InvalidFormatException();

    foreach (EpkEntry entry in m_dir)
    {
        m_index.Position = entry_table_offset + entry.DirIndex * 12;
        ReadEntry (entry);
    }
}
```

#### ParseRegularIndex

```csharp
void ParseRegularIndex (int count) {
    for (int i = 0; i < count; ++i)
    {
        int name_length = m_index.ReadByte();
        var name = m_index.ReadCString (name_length);
        var entry = FormatCatalog.Instance.Create<EpkEntry> (name);
        ReadEntry (entry);
        m_dir.Add (entry);
    }
}
```

#### ReadEntry

```csharp
void ReadEntry (PackedEntry entry) {
    entry.Offset        = m_index.ReadUInt32();
    entry.Size          = m_index.ReadUInt32();
    entry.UnpackedSize  = m_index.ReadUInt32();
    if (m_info.AlignedOffset)
    {
        entry.Offset <<= 11;
        entry.Size   <<= 11;
    }
    entry.IsPacked = entry.UnpackedSize != 0;
    if (!entry.IsPacked)
        entry.UnpackedSize = entry.Size;
}
```

#### TraverseIndex

```csharp
void TraverseIndex (long pos, int name_length) {
    if (name_length >= m_name_buf.Length)
        throw new InvalidFormatException ("Entry filename is too long");
    m_index.Position = pos;
    int count = m_index.ReadByte();
    for (int i = 0; i < count; ++i)
    {
        byte next_letter = m_index.ReadUInt8();
        int next_offset = m_wide_offset ? m_index.ReadInt32() : (int)m_index.ReadUInt16();
        if (0 == next_letter)
        {
            var name = Encodings.cp932.GetString (m_name_buf, 0, name_length);
            var entry = FormatCatalog.Instance.Create<EpkEntry> (name);
            entry.DirIndex = next_offset;
            m_dir.Add (entry);
        }
        else
        {
            m_name_buf[name_length] = next_letter;
            pos = m_index.Position;
            TraverseIndex (pos + next_offset, name_length+1);
            m_index.Position = pos;
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Lucifen/ArcLPK.cs](../Lucifen/ArcLPK.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Ellefin/ArcEPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
