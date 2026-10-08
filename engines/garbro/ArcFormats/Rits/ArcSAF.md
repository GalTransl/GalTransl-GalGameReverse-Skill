# Rits / ArcSAF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SAF` / `GameRes.Formats.Rits.SafOpener` | `saf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SafOpener.TryOpen` | `int id = file.View.ReadInt16 (0);` |
| `SafOpener.TryOpen` | `int count = file.View.ReadInt16 (2);` |
| `SafOpener.TryOpen` | `int names_length = file.View.ReadInt32 (4);` |
| `SafOpener.TryOpen` | `var index_buffer = file.View.ReadBytes (8, index_size);` |
| `SafOpener.TryOpen` | `var names_buffer = file.View.ReadBytes (8 + index_size, (uint)names_length);` |
| `SafIndexReader5.Scan` | `root_index = m_index.ToInt32 (DirIndexPos);` |
| `SafIndexReader5.Scan` | `root_count = m_index.ToInt32 (DirCountPos);` |
| `SafIndexReader5.ReadDir` | `int subdir_index = m_index.ToInt32 (index_offset + DirIndexPos);` |
| `SafIndexReader5.ReadDir` | `int subdir_count = m_index.ToInt32 (index_offset + DirCountPos);` |
| `SafIndexReader5.ReadDir` | `entry.Offset = (long)m_index.ToUInt32 (index_offset+OffsetPos) << 11;` |
| `SafIndexReader5.ReadDir` | `entry.Size   = m_index.ToUInt32 (index_offset+SizePos);` |
| `SafIndexReader5.ReadDir` | `entry.UnpackedSize = m_index.ToUInt32 (index_offset+UnpackedPos);` |
| `SafIndexReader6.ReadName` | `int name_pos = m_index.ToInt32 (offset) & 0x7FFFFFFF;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Rits.SafArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly int Version ;

public bool LzssCompression { get { return (Version & 2) != 0; } }
```

#### SafArchive

```csharp
public SafArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version)
    : base (arc, impl, dir) {
    Version = version;
}
```

### GameRes.Formats.Rits.SafOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const byte DefaultKey5 = 0xDF ;

const byte DefaultKey6 = 0xEF ;
```

#### SafOpener

```csharp
public SafOpener () {
    ContainedFormats = new[] { "HBM", "BMP", "PNG", "WAV", "OGG", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int id = file.View.ReadInt16 (0);
    int count = file.View.ReadInt16 (2);
    if (!IsSaneCount (count))
        return null;
    IIndexReader reader;
    if ((id & 0xFF00) == 0x500)
    {
        var index_buffer = new byte[32 * count];
        if (index_buffer.Length != file.View.Read (4, index_buffer, 0, (uint)index_buffer.Length))
            return null;
        if (0x501 == id)
            DecryptIndex (index_buffer, count, DefaultKey5);
        reader = new SafIndexReader5 (this, index_buffer, count);
    }
    else if ((id & 0xFF00) == 0x600)
    {
        int names_length = file.View.ReadInt32 (4);
        if (names_length <= 0 || names_length >= file.MaxOffset)
            return null;
        uint index_size = (uint)count * 16;
        var index_buffer = file.View.ReadBytes (8, index_size);
        var names_buffer = file.View.ReadBytes (8 + index_size, (uint)names_length);
        if ((id & 1) != 0)
        {
            DecryptIndexV6 (index_buffer, count, DefaultKey6);
            DecryptNames (names_buffer, names_length);
        }
        reader = new SafIndexReader6 (this, index_buffer, names_buffer, count);
    }
    else
        return null;
    var dir = reader.Scan();
    if (0 == dir.Count || dir.Any (e => !e.CheckPlacement (file.MaxOffset)))
        return null;
    return new SafArchive (file, this, dir, id);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size, entry.Name);
    var packed_entry = entry as PackedEntry;
    if (null == packed_entry || !packed_entry.IsPacked)
        return input;
    var sarc = arc as SafArchive;
    if (null == sarc || !sarc.LzssCompression)
        return new ZLibStream (input, CompressionMode.Decompress);
    else
        return new LzssStream (input);
}
```

#### DecryptIndex

```csharp
void DecryptIndex (byte[] index, int count, byte start_key) {
    int offset = 0;
    for (int i = 0; i < count; ++i)
    {
        byte key = start_key;
        for (int j = 0; j < 0x20; ++j)
        {
            index[offset++] ^= key++;
        }
    }
}
```

#### DecryptIndexV6

```csharp
void DecryptIndexV6 (byte[] index, int count, byte start_key) {
    int offset = 0;
    for (int i = 0; i < count; ++i)
    {
        byte key = start_key;
        for (int j = 0; j < 0x10; ++j)
        {
            index[offset++] ^= key++;
        }
    }
}
```

#### DecryptNames

```csharp
void DecryptNames (byte[] data, int count) {
    byte key = 0xFF;
    for (int i = 0; i < count; ++i)
    {
        data[i] ^= key--;
    }
}
```

### GameRes.Formats.Rits.SafIndexReader5

继承/接口：`IIndexReader`。

#### 状态与常量

```csharp
private     ArchiveFormat   m_saf ;

protected   byte[]      m_index ;

protected   int         m_count ;

private     List<Entry> m_dir ;

protected   int         EntrySize   = 0x20 ;

protected   int         OffsetPos   = 0x14 ;

protected   int         SizePos     = 0x18 ;

protected   int         UnpackedPos = 0x1C ;

protected   int         DirIndexPos = 0x14 ;

protected   int         DirCountPos = 0x1C ;

bool m_ignore_dirs = false ;
```

#### SafIndexReader5

```csharp
public SafIndexReader5 (ArchiveFormat saf, byte[] index, int count) {
    m_saf = saf;
    m_index = index;
    m_count = count;
    m_dir = new List<Entry> (count);
}
```

#### Scan

```csharp
public List<Entry> Scan () {
    string root_name;
    int root_index;
    int root_count;
    if (!IsDir (0))
    {
        root_name = "";
        root_index = 0;
        root_count = m_count;
        m_ignore_dirs = true;
    }
    else
    {
        root_name = ReadName (0);
        if ("root" == root_name)
        {
            root_name = "";
        }
        root_index = m_index.ToInt32 (DirIndexPos);
        root_count = m_index.ToInt32 (DirCountPos);
    }
    ReadDir (root_name, root_index, root_count);
    return m_dir;
}
```

#### ReadDir

```csharp
void ReadDir (string dir_name, int index, int count) {
    if (index + count > m_count)
        throw new InvalidFormatException();
    int index_offset = index * EntrySize;
    for (int i = 0; i < count; ++i, index_offset += EntrySize)
    {
        if (IsDir (index_offset))
        {
            if (m_ignore_dirs)
                continue;
            int subdir_index = m_index.ToInt32 (index_offset + DirIndexPos);
            if (subdir_index < index + count)
                continue;
            var subdir_name = ReadName (index_offset);
            int subdir_count = m_index.ToInt32 (index_offset + DirCountPos);
            ReadDir (Path.Combine (dir_name, subdir_name), subdir_index, subdir_count);
        }
        else
        {
            var name = ReadName (index_offset);
            name = Path.Combine (dir_name, name);
            var entry = m_saf.Create<PackedEntry> (name);
            entry.Offset = (long)m_index.ToUInt32 (index_offset+OffsetPos) << 11;
            entry.Size   = m_index.ToUInt32 (index_offset+SizePos);
            entry.UnpackedSize = m_index.ToUInt32 (index_offset+UnpackedPos);
            entry.IsPacked = entry.UnpackedSize != 0;
            m_dir.Add (entry);
        }
    }
}
```

#### IsDir

```csharp
protected virtual bool IsDir (int pos) {
    return m_index[pos] > 0x7F;
}
```

#### ReadName

```csharp
protected virtual string ReadName (int pos) {
    m_index[pos] &= 0x7F;
    string name = Encodings.cp932.GetString (m_index, pos, 0x14);
    return name.TrimEnd();
}
```

### GameRes.Formats.Rits.SafIndexReader6

继承/接口：`SafIndexReader5`。

#### 状态与常量

```csharp
byte[]  m_names ;
```

#### SafIndexReader6

```csharp
public SafIndexReader6 (ArchiveFormat saf, byte[] index, byte[] names, int count) : base (saf, index, count) {
    m_names = names;

    EntrySize   = 16;
    OffsetPos   = 4;
    SizePos     = 8;
    UnpackedPos = 12;
    DirIndexPos = 4;
    DirCountPos = 12;
}
```

#### IsDir

```csharp
protected override bool IsDir (int pos) {
    return m_index[pos+3] > 0x7F;
}
```

#### ReadName

```csharp
protected override string ReadName (int offset) {
    int name_pos = m_index.ToInt32 (offset) & 0x7FFFFFFF;
    return Binary.GetCString (m_names, name_pos);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Rits/ArcSAF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
