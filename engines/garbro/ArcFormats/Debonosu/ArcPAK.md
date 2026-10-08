# Debonosu / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/Debonosu` / `GameRes.Formats.Debonosu.PakOpener` | `pak` | `50414b00` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `uint index_offset = file.View.ReadUInt16 (4);` |
| `PakOpener.TryOpen` | `if (0 != file.View.ReadUInt16 (10))` |
| `PakOpener.TryOpen` | `uint info_size = file.View.ReadUInt32 (index_offset);` |
| `PakOpener.TryOpen` | `int root_count = file.View.ReadInt32 (index_offset+8);` |
| `PakOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (index_offset+0xC);` |
| `PakOpener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (index_offset+0x10);` |
| `IndexReader.ReadDir` | `long offset = m_input.ReadInt64();` |
| `IndexReader.ReadDir` | `long unpacked = m_input.ReadInt64();` |
| `IndexReader.ReadDir` | `long packed = m_input.ReadInt64();` |
| `IndexReader.ReadDir` | `uint flags = m_input.ReadUInt32();` |
| `IndexReader.ReadDir` | `m_input.ReadUInt64();` |
| `IndexReader.ReadName` | `int b = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Debonosu.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt16 (4);
    if (0 != file.View.ReadUInt16 (10))
        return null;

    uint info_size = file.View.ReadUInt32 (index_offset);
    int root_count = file.View.ReadInt32 (index_offset+8);
    uint unpacked_size = file.View.ReadUInt32 (index_offset+0xC);
    uint packed_size = file.View.ReadUInt32 (index_offset+0x10);
    using (var packed = file.CreateStream (index_offset+info_size, packed_size))
    using (var unpacked = new DeflateStream (packed, CompressionMode.Decompress))
    using (var reader = new IndexReader (unpacked, index_offset+info_size+packed_size))
    {
        var dir = reader.ReadRoot (root_count);
        if (null == dir)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var packed = entry as PackedEntry;
    if (null == packed || !packed.IsPacked)
        return input;
    return new DeflateStream (input, CompressionMode.Decompress);
}
```

### GameRes.Formats.Debonosu.PakOpener.IndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
BinaryReader    m_input ;

long            m_base_offset ;

List<Entry>     m_dir = new List<Entry>() ;

byte[] name_buffer = new byte[32] ;

bool _disposed = false ;
```

#### IndexReader

```csharp
public IndexReader (Stream input, long base_offset) {
    m_input = new ArcView.Reader (input);
    m_base_offset = base_offset;
}
```

#### ReadRoot

```csharp
public List<Entry> ReadRoot (int root_count) {
    ReadDir ("", root_count);
    return m_dir;
}
```

#### ReadDir

```csharp
void ReadDir (string path, int count) {
    for (int i = 0; i < count; ++i)
    {
        long offset = m_input.ReadInt64();
        long unpacked = m_input.ReadInt64();
        long packed = m_input.ReadInt64();
        uint flags = m_input.ReadUInt32();
        m_input.ReadUInt64();
        m_input.ReadUInt64();
        m_input.ReadUInt64();
        var name = Path.Combine (path, ReadName());
        if (0 != (flags & 0x10))
        {
            ReadDir (name, (int)unpacked);
        }
        else
        {
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = m_base_offset + offset;
            entry.Size = (uint)packed;
            entry.UnpackedSize = (uint)unpacked;
            entry.IsPacked = true;
            m_dir.Add (entry);
        }
    }
}
```

#### ReadName

```csharp
string ReadName () {
    int size = 0;
    for (;;)
    {
        int b = m_input.ReadByte();
        if (0 == b)
            break;
        if (name_buffer.Length == size)
        {
            Array.Resize (ref name_buffer, checked(size/2*3));
        }
        name_buffer[size++] = (byte)b;
    }
    return Encodings.cp932.GetString (name_buffer, 0, size);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Debonosu/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
