# Malie / ArcLIBU：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LIBU` / `GameRes.Formats.Malie.LibUOpener` | `lib` | `4c494255` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LibUReader.ReadDir` | `if (0x5542494C != m_input.ReadUInt32())` |
| `LibUReader.ReadDir` | `m_input.ReadInt32();` |
| `LibUReader.ReadDir` | `int count = m_input.ReadInt32();` |
| `LibUReader.ReadDir` | `uint entry_size = m_input.ReadUInt32();` |
| `LibUReader.ReadDir` | `long entry_offset = base_offset + m_input.ReadInt64();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Malie.LibUOpener

继承/接口：`ArchiveFormat`。

#### LibUOpener

```csharp
public LibUOpener () {
    Extensions = new string[] { "lib" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var reader = LibUReader.Create (file))
    {
        if (!reader.ReadIndex())
            return null;
        return new ArcFile (file, this, reader.Dir);
    }
}
```

### GameRes.Formats.Malie.LibUReader

继承/接口：`ILibIndexReader`。

#### 状态与常量

```csharp
BinaryReader    m_input ;

readonly long   m_max_offset ;

List<Entry>     m_dir = new List<Entry>() ;

public List<Entry> Dir { get { return m_dir; } }

char[] m_name_buffer = new char[0x22] ;

bool m_disposed = false ;
```

#### LibUReader

```csharp
public LibUReader (Stream input) {
    m_input = new BinaryReader (input, Encoding.Unicode);
    m_max_offset = input.Length;
}
```

#### Create

```csharp
public static LibUReader Create (ArcView file) {
    var input = file.CreateStream();
    return new LibUReader (input);
}
```

#### Create

```csharp
public static LibUReader Create (ArcView file, IMalieDecryptor decryptor) {
    var input = new EncryptedStream (file, decryptor);
    return new LibUReader (input);
}
```

#### ReadIndex

```csharp
public bool ReadIndex () {
    return ReadDir ("", 0) && m_dir.Count > 0;
}
```

#### ReadDir

```csharp
bool ReadDir (string root, long base_offset) {
    m_input.BaseStream.Position = base_offset;
    if (0x5542494C != m_input.ReadUInt32())
        return false;
    m_input.ReadInt32();
    int count = m_input.ReadInt32();
    if (!ArchiveFormat.IsSaneCount (count))
        return false;
    if (m_dir.Capacity < m_dir.Count + count)
        m_dir.Capacity = m_dir.Count + count;

    long index_pos = base_offset + 0x10;
    for (int i = 0; i < count; ++i)
    {
        m_input.BaseStream.Position = index_pos;
        var name = ReadName();
        uint entry_size = m_input.ReadUInt32();
        long entry_offset = base_offset + m_input.ReadInt64();
        index_pos = m_input.BaseStream.Position;
        bool has_extension = -1 != name.IndexOf ('.');
        name = Path.Combine (root, name);
        if (!has_extension && ReadDir (name, entry_offset))
            continue;

        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = entry_offset;
        entry.Size   = entry_size;
        if (!entry.CheckPlacement (m_max_offset))
            return false;

        m_dir.Add (entry);
    }
    return true;
}
```

#### ReadName

```csharp
string ReadName () {
    m_input.Read (m_name_buffer, 0, 0x22);
    int length = Array.IndexOf (m_name_buffer, '\0');
    if (-1 == length)
        length = m_name_buffer.Length;
    return new string (m_name_buffer, 0, length);
}
```

## 配套算法与外部条件

- [ArcFormats/Malie/MalieEncryption.cs](MalieEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Malie/ArcLIBU.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
