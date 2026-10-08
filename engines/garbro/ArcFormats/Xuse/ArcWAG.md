# Xuse / ArcWAG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WAG` / `GameRes.Formats.Xuse.WagOpener` | `wag`, `4ag`, `004` | `57414740`, `47414634` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WagOpener.TryOpen` | `int version = file.View.ReadUInt16 (4);` |
| `WagOpener.TryOpen` | `int count = file.View.ReadInt32 (0x46);` |
| `WagOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `IndexReader.ReadIndex` | `byte[] title = m_file.View.ReadBytes (6, 0x40);` |
| `IndexReader.ReadIndex` | `byte[] index = m_file.View.ReadBytes (index_offset, (uint)(4*m_count));` |
| `IndexReader.ReadIndex` | `uint next_offset = LittleEndian.ToUInt32 (index, current_offset);` |
| `IndexReader.ReadIndex` | `next_offset = LittleEndian.ToUInt32 (index, current_offset);` |
| `IndexReader.ParseEntryV2` | `var data_size = LittleEndian.ToUInt32 (m_chunk_buf, 0);` |
| `IndexReader.ParseEntryV2` | `var name_length = LittleEndian.ToInt32 (m_chunk_buf, 4);` |
| `IndexReader.ParseEntryV3` | `if (!Binary.AsciiEqual (m_chunk_buf, "DSET"))` |
| `IndexReader.ParseEntryV3` | `int chunk_count = LittleEndian.ToInt32 (m_chunk_buf, 4);` |
| `IndexReader.ParseEntryV3` | `int chunk_size = LittleEndian.ToInt32 (m_chunk_buf, 4);` |
| `IndexReader.ParseEntryV3` | `if (Binary.AsciiEqual (m_chunk_buf, "PICT"))` |
| `IndexReader.ParseEntryV3` | `else if (null == filename && Binary.AsciiEqual (m_chunk_buf, "FTAG"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Xuse.WagArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### WagArchive

```csharp
public WagArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Xuse.WagOpener

继承/接口：`ArchiveFormat`。

#### WagOpener

```csharp
public WagOpener () {
    Extensions = new string[] { "wag", "4ag", "004" };
    Signatures = new uint[] { 0x40474157, 0x34464147 };

}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadUInt16 (4);
    if (0x300 != version && 0x200 != version)
        return null;
    int count = file.View.ReadInt32 (0x46);
    if (!IsSaneCount (count))
        return null;

    var reader = new IndexReader (file, version, count);
    var dir = reader.ReadIndex();
    if (null == dir)
        return null;
    return new WagArchive (file, this, dir, reader.DataKey);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var warc = arc as WagArchive;
    if (null == warc)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    Decrypt ((uint)entry.Offset, warc.Key, data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### GenerateKey

```csharp
static private byte[] GenerateKey (byte[] keyword) {
    return GenerateKey (keyword, keyword.Length);
}
```

#### GenerateKey

```csharp
static private byte[] GenerateKey (byte[] keyword, int length) {
    int hash = 0;
    for (int i = 0; i < length; ++i)
        hash = (((sbyte)keyword[i] + i) ^ hash) + length;

    int key_length = (hash & 0xFF) + 0x40;

    for (int i = 0; i < length; ++i)
        hash += (sbyte)keyword[i];

    byte[] key = new byte[key_length--];
    key[1] = (byte)(hash >> 8);
    hash &= 0xF;
    key[0] = (byte)hash;
    key[2] = 0x46;
    key[3] = 0x88;

    for (int i = 4; i < key_length; ++i)
    {
        hash += (((sbyte)keyword[i % length] ^ hash) + i) & 0xFF;
        key[i] = (byte)hash;
    }
    return key;
}
```

#### Decrypt

```csharp
static private void Decrypt (uint offset, byte[] key, byte[] index) {
    Decrypt (offset, key, index, 0, index.Length);
}
```

#### Decrypt

```csharp
static private void Decrypt (uint offset, byte[] key, byte[] index, int pos, int length) {
    uint key_last = (uint)key.Length-1;
    for (uint i = 0; i < length; ++i)
        index[pos+i] ^= key[(offset + i) % key_last];
}
```

### GameRes.Formats.Xuse.WagOpener.IndexReader

#### 状态与常量

```csharp
ArcView     m_file ;

int         m_version ;

int         m_count ;

byte[]      m_data_key ;

public byte[] DataKey { get { return m_data_key; } }

byte[]      m_chunk_buf = new byte[0x40] ;

static readonly Regex DriveRe = new Regex (@"^(?:.+:|\.\.)?\\+") ;
```

#### IndexReader

```csharp
public IndexReader (ArcView file, int version, int count) {
    m_file = file;
    m_version = version;
    m_count = count;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    byte[] title = m_file.View.ReadBytes (6, 0x40);
    int title_length = Array.IndexOf<byte> (title, 0);
    if (-1 == title_length)
        title_length = title.Length;
    string arc_filename = Path.GetFileName (m_file.Name);
    if (0x200 != m_version)
        arc_filename = arc_filename.ToLowerInvariant();
    string base_filename = Path.GetFileNameWithoutExtension (arc_filename);

    byte[] name_key = GenerateKey (Encodings.cp932.GetBytes (arc_filename));

    uint index_offset = 0x200 + (uint)name_key.Select (x => (int)x).Sum();
    for (int i = 0; i < name_key.Length; ++i)
    {
        index_offset ^= name_key[i];
        index_offset = Binary.RotR (index_offset, 1);
    }
    for (int i = 0; i < name_key.Length; ++i)
    {
        index_offset ^= name_key[i];
        index_offset = Binary.RotR (index_offset, 1);
    }
    index_offset %= 0x401;

    index_offset += 0x4A;
    byte[] index = m_file.View.ReadBytes (index_offset, (uint)(4*m_count));
    if (index.Length != 4*m_count)
        return null;

    byte[] index_key = new byte[index.Length];
    for (int i = 0; i < index_key.Length; ++i)
    {
        int v = name_key[(i+1) % name_key.Length] ^ (name_key[i % name_key.Length] + i);
        index_key[i] = (byte)(m_count + v);
    }
    Decrypt (index_offset, index_key, index);
    m_data_key = GenerateKey (title, title_length);
    var dir = new List<Entry> (m_count);
    int current_offset = 0;
    uint next_offset = LittleEndian.ToUInt32 (index, current_offset);
    for (int i = 0; i < m_count; ++i)
    {
        current_offset += 4;
        uint entry_offset = next_offset;
        if (entry_offset >= m_file.MaxOffset)
            return null;
        if (i + 1 == m_count)
            next_offset = (uint)m_file.MaxOffset;
        else
            next_offset = LittleEndian.ToUInt32 (index, current_offset);
        uint entry_size = next_offset - entry_offset;
        var entry = ParseEntry (entry_offset, entry_size);
        if (string.IsNullOrEmpty (entry.Name))
            entry.Name = string.Format ("{0}#{1:D4}", base_filename, i);
        dir.Add (entry);
    }
    return dir;
}
```

#### ParseEntry

```csharp
Entry ParseEntry (uint entry_offset, uint entry_size) {
    ReadChunk (entry_offset, 8);
    if (0x200 == m_version)
        return ParseEntryV2 (entry_offset, entry_size);
    else
        return ParseEntryV3 (entry_offset, entry_size);
}
```

#### ReadChunk

```csharp
void ReadChunk (uint offset, int chunk_size) {
    if (chunk_size > m_chunk_buf.Length)
        m_chunk_buf = new byte[chunk_size];
    if (chunk_size != m_file.View.Read (offset, m_chunk_buf, 0, (uint)chunk_size))
        throw new InvalidFormatException();
    Decrypt (offset, m_data_key, m_chunk_buf, 0, chunk_size);
}
```

#### ParseEntryV2

```csharp
Entry ParseEntryV2 (uint entry_offset, uint entry_size) {
    var data_size = LittleEndian.ToUInt32 (m_chunk_buf, 0);
    if (data_size >= entry_size)
        throw new InvalidFormatException();
    var name_length = LittleEndian.ToInt32 (m_chunk_buf, 4);
    entry_offset += 0x10;
    var entry = new Entry();
    if (name_length > 0)
    {
        ReadChunk (entry_offset+data_size, name_length);
        if ('|' == m_chunk_buf[name_length-1])
            --name_length;
        entry.Name = Encodings.cp932.GetString (m_chunk_buf, 0, name_length);
        entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
    }
    entry.Offset = entry_offset;
    entry.Size = data_size;
    return entry;
}
```

#### ParseEntryV3

```csharp
Entry ParseEntryV3 (uint entry_offset, uint entry_size) {
    if (!Binary.AsciiEqual (m_chunk_buf, "DSET"))
        throw new InvalidFormatException();

    uint chunk_offset = entry_offset + 10;
    int chunk_count = LittleEndian.ToInt32 (m_chunk_buf, 4);
    var entry = new Entry();
    string filename = null;
    for (int chunk = 0; chunk < chunk_count; ++chunk)
    {
        ReadChunk (chunk_offset, 8);
        int chunk_size = LittleEndian.ToInt32 (m_chunk_buf, 4);
        if (chunk_size <= 0)
            throw new InvalidFormatException();
        if (Binary.AsciiEqual (m_chunk_buf, "PICT"))
        {
            if (string.IsNullOrEmpty (entry.Type))
            {
                entry.Type = "image";
                entry_offset = chunk_offset + 0x10;
                entry_size = (uint)chunk_size - 6;
            }
        }
        else if (null == filename && Binary.AsciiEqual (m_chunk_buf, "FTAG"))
        {
            ReadChunk (chunk_offset+10, chunk_size-2);
            filename = Encodings.cp932.GetString (m_chunk_buf, 0, chunk_size-2);
        }
        chunk_offset += 10 + (uint)chunk_size;
    }
    if (!string.IsNullOrEmpty (filename))
        entry.Name = DriveRe.Replace (filename, "");
    entry.Offset = entry_offset;
    entry.Size = entry_size;
    return entry;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Xuse/ArcWAG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
