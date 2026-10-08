# Ads / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/ADS` / `GameRes.Formats.Ads.PacOpener` | `pac` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0);` |
| `IndexReader.ReadDir` | `int dir_count = m_input.ReadInt32();` |
| `IndexReader.ReadDir` | `int file_count = m_input.ReadInt32();` |
| `IndexReader.ReadDir` | `var root_name = ReadCString();` |
| `IndexReader.ReadDir` | `var name = ReadCString();` |
| `IndexReader.ReadDir` | `entry.Size = m_input.ReadUInt32();` |
| `IndexReader.ReadDir` | `entry.Offset = m_input.ReadUInt32();` |
| `IndexReader.ReadDir` | `entry.CompressionMethod = m_input.ReadInt32();` |
| `IndexReader.ReadDir` | `uint offset = m_input.ReadUInt32();` |
| `IndexReader.ReadCString` | `internal string ReadCString () {` |
| `RleDecompressor.Unpack` | `int ctl = m_input.ReadByte();` |
| `RleDecompressor.Unpack` | `int count = buffer.ToInt32 (4) - 1;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ads.AdsEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int  CompressionMethod ;
```

### GameRes.Formats.Ads.PacOpener

继承/接口：`ArchiveFormat`。

#### PacOpener

```csharp
public PacOpener () {
    ContainedFormats = new[] { "TGA", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".pac"))
        return null;
    uint index_size = file.View.ReadUInt32 (0);
    if (index_size < 0x110 || index_size >= file.MaxOffset)
        return null;
    using (var reader = new IndexReader (file, index_size))
    {
        var dir = reader.ReadIndex();
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
    var pent = entry as AdsEntry;
    if (null == pent || pent.CompressionMethod != 1)
        return input;
    return new PackedStream<RleDecompressor> (input);
}
```

### GameRes.Formats.Ads.IndexReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
ArcViewStream   m_input ;

List<Entry>     m_dir ;

readonly long   m_max_offset ;

byte[]          m_buffer = new byte[0x104] ;

bool m_disposed = false ;
```

#### IndexReader

```csharp
public IndexReader (ArcView file, uint index_size) {
    m_input = file.CreateStream (0, index_size);
    m_dir = new List<Entry>();
    m_max_offset = file.MaxOffset;
}
```

#### ReadDir

```csharp
bool ReadDir (uint dir_offset, string dir_name) {
    m_input.Position = dir_offset;
    int dir_count = m_input.ReadInt32();
    if (dir_count < 0 || dir_count > 0x200)
        return false;
    int file_count = m_input.ReadInt32();
    if (file_count < 0 || file_count > 0x40000)
        return false;
    if (string.IsNullOrEmpty (dir_name))
    {
        var root_name = ReadCString();
        if (string.IsNullOrWhiteSpace (root_name))
            return false;
    }
    m_dir.Capacity = m_dir.Count + file_count;
    for (int j = 0; j < file_count; ++j)
    {
        var name = ReadCString();
        if (string.IsNullOrWhiteSpace (name))
            return false;
        if (dir_name.Length > 0)
            name = dir_name + '/' + name;
        var entry = new AdsEntry { Name = name };
        entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
        entry.Size = m_input.ReadUInt32();
        entry.Offset = m_input.ReadUInt32();
        if (!entry.CheckPlacement (m_max_offset))
            return false;
        entry.CompressionMethod = m_input.ReadInt32();
        entry.IsPacked = entry.CompressionMethod != 0;
        m_dir.Add (entry);
    }
    for (int j = 0; j < dir_count; ++j)
    {
        uint offset = m_input.ReadUInt32();
        if (offset >= m_input.Length)
            return false;
        var name = ReadCString();
        if (string.IsNullOrWhiteSpace (name))
            return false;
        if (dir_name.Length > 0)
            name = dir_name + '/' + name;
        var current_pos = m_input.Position;
        if (!ReadDir (offset, name))
            return false;
        m_input.Position = current_pos;
    }
    return true;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    if (!ReadDir (4, ""))
        return null;
    return m_dir;
}
```

#### ReadCString

```csharp
internal string ReadCString () {
    int length = m_input.Read (m_buffer, 0, 0x104);
    int end = 0;
    while (end < length && m_buffer[end] != 0)
    {
        m_buffer[end++] ^= 0xFF;
    }
    return Encodings.cp932.GetString (m_buffer, 0, end);
}
```

### GameRes.Formats.Ads.RleDecompressor

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
Stream          m_input ;
```

#### Initialize

```csharp
public override void Initialize (Stream input) {
    m_input = input;
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    var buffer = new byte[8];
    int chunk_size = 3;
    for (;;)
    {
        int ctl = m_input.ReadByte();
        if (-1 == ctl)
            yield break;
        if (ctl != 0)
        {
            if (m_input.Read (buffer, 4, 4) != 4)
                yield break;
            int count = buffer.ToInt32 (4) - 1;
            while (count --> 0)
            {
                for (int i = 0; i < chunk_size; ++i)
                {
                    m_buffer[m_pos++] = buffer[i];
                    if (0 == --m_length)
                        yield return m_pos;
                }
            }
        }
        else
        {
            chunk_size = m_input.Read (buffer, 0, 3);
            if (0 == chunk_size)
                yield break;
            for (int i = 0; i < chunk_size; ++i)
            {
                m_buffer[m_pos++] = buffer[i];
                if (0 == --m_length)
                    yield return m_pos;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ads/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
