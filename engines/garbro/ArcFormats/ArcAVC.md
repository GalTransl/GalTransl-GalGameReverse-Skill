# ArcFormats / ArcAVC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AVC` / `GameRes.Formats.AVC.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AdvReader.ReadIndex` | `int entry_size = LittleEndian.ToInt32 (m_header, 0x14);` |
| `AdvReader.ReadIndex` | `m_index_offset = LittleEndian.ToInt32 (m_header, 0x10);` |
| `AdvReader.ReadIndex` | `m_count = LittleEndian.ToInt32 (m_header, 0x20);` |
| `AdvReader.ParseIndex` | `entry.Offset = m_header_offset + LittleEndian.ToUInt32 (m_index, index_offset);` |
| `AdvReader.ParseIndex` | `entry.Size   = LittleEndian.ToUInt32 (m_index, index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AVC.ArchiveFile

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;

public readonly int    HeaderOffset ;
```

#### ArchiveFile

```csharp
public ArchiveFile (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int offset, byte[] key)
    : base (arc, impl, dir) {
    HeaderOffset = offset;
    Key = key;
}
```

### GameRes.Formats.AVC.ArchiveScheme

#### 状态与常量

```csharp
public string   Password ;

public int      KeyOffset ;

public int      HeaderOffset ;
```

### GameRes.Formats.AVC.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var reader = new AdvReader (file);
    var dir = reader.GetIndex();
    if (null == dir)
        return null;
    return new ArchiveFile (file, this, dir, reader.HeaderOffset, reader.Key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var arcf = arc as ArchiveFile;
    if (null == arcf)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = new byte[entry.Size];
    arc.File.View.Read (entry.Offset, data, 0, entry.Size);
    int base_offset = (int)(entry.Offset-arcf.HeaderOffset);
    for (int i = 0; i < data.Length; ++i)
        data[i] ^= arcf.Key[((base_offset+i)&7)];
    return new BinMemoryStream (data, entry.Name);
}
```

### GameRes.Formats.AVC.DatOpener.AdvReader

#### 状态与常量

```csharp
ArcView     m_file ;

byte[]      m_input = new byte[0x80] ;

byte[]      m_header = new byte[0x24] ;

byte[]      m_key = new byte[8] ;

byte[]      m_index ;

int         m_index_offset ;

int         m_count ;

int         m_header_offset ;

public byte[]       Key { get { return m_key; } }

public int HeaderOffset { get { return m_header_offset; } }

internal static ArchiveScheme[] KnownSchemes = new ArchiveScheme[0] ;
```

#### AdvReader

```csharp
public AdvReader (ArcView file) {
    m_file = file;
}
```

#### GetIndex

```csharp
public List<Entry> GetIndex () {
    if (m_input.Length != m_file.View.Read (0, m_input, 0, (uint)m_input.Length))
        return null;
    foreach (var scheme in KnownSchemes)
    {
        if (!ReadIndex (scheme.KeyOffset, scheme.HeaderOffset))
            continue;
        try
        {
            var dir = ParseIndex();
            if (null != dir)
                return dir;
        }
        catch {  }
    }
    return null;
}
```

#### ReadIndex

```csharp
bool ReadIndex (int key_offset, int header_offset) {

    for (int i = 0; i < 8; ++i)
    {
        var symbol = m_input[header_offset+i] ^ "ARCHIVE\0"[i];
        var check = (char)(m_input[key_offset+i] ^ symbol);
        if (!check.IsAsciiVisible())
            return false;
        Key[i] = (byte)symbol;
    }
    for (int i = 0x10; i < 0x24; ++i)
        m_header[i] = (byte)(m_input[header_offset+i] ^ Key[i&7]);
    int entry_size = LittleEndian.ToInt32 (m_header, 0x14);
    if (0x114 != entry_size)
        return false;
    m_index_offset = LittleEndian.ToInt32 (m_header, 0x10);
    m_count = LittleEndian.ToInt32 (m_header, 0x20);
    if (m_index_offset < 0x24 || (long)m_index_offset+header_offset >= m_file.MaxOffset
        || m_count <= 0 || m_count > 0xffff)
        return false;
    int index_size = entry_size * m_count;
    if (null == m_index || m_index.Length < index_size)
        m_index = new byte[index_size];
    if (index_size != m_file.View.Read (m_index_offset+header_offset, m_index, 0, (uint)index_size))
        return false;
    m_header_offset = header_offset;
    return true;
}
```

#### ParseIndex

```csharp
List<Entry> ParseIndex() {
    for (int i = 0; i < 0x114 * m_count; ++i)
        m_index[i] ^= Key[(m_index_offset+i)&7];
    var dir = new List<Entry> (m_count);
    int index_offset = 0;
    for (int i = 0; i < m_count; ++i)
    {
        if (0 != m_index[index_offset++])
            return null;
        int name_length = 0;
        while (name_length < 0x100 && 0 != m_index[index_offset+name_length])
            name_length++;
        if (0 == name_length)
        {
            index_offset += 0x113;
            continue;
        }
        var name = Encodings.cp932.GetString (m_index, index_offset, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        index_offset += 0x107;
        entry.Offset = m_header_offset + LittleEndian.ToUInt32 (m_index, index_offset);
        entry.Size   = LittleEndian.ToUInt32 (m_index, index_offset+4);
        index_offset += 0x0c;
        dir.Add (entry);
    }
    return dir;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ArcAVC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
