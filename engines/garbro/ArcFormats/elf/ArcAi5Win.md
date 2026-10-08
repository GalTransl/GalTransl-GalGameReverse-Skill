# elf / ArcAi5Win：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/AI5WIN` / `GameRes.Formats.Elf.ArcAI5Opener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcAI5Opener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `Ai5ArcIndexReader.Read` | `entry.Size   = m_file.View.ReadUInt32 (index_offset)   ^ scheme.SizeKey;` |
| `Ai5ArcIndexReader.Read` | `entry.Offset = m_file.View.ReadUInt32 (index_offset+4) ^ scheme.OffsetKey;` |
| `Ai5ArcIndexReader.GuessSchemes` | `byte name_key = m_file.View.ReadByte (3 + name_length);` |
| `Ai5ArcIndexReader.GuessSchemes` | `uint first_size   = m_file.View.ReadUInt32 (4 + name_length);` |
| `Ai5ArcIndexReader.GuessSchemes` | `uint first_offset = m_file.View.ReadUInt32 (8 + name_length);` |
| `Ai5ArcIndexReader.GuessSchemes` | `uint second_offset = m_file.View.ReadUInt32 ((name_length+8) * 2) ^ offset_key;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Elf.ArcIndexScheme

#### 状态与常量

```csharp
public int  NameLength ;

public byte NameKey ;

public uint SizeKey ;

public uint OffsetKey ;
```

### GameRes.Formats.Elf.ArcAI5Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static Ai5Scheme DefaultScheme = new Ai5Scheme { KnownSchemes = new Dictionary<string, ArcIndexScheme>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0 == KnownSchemes.Count)
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    var reader = new Ai5ArcIndexReader (file, count);
    var dir = reader.TrySchemes (KnownSchemes.Values);
    if (null == dir)
        dir = reader.TrySchemes (reader.GuessSchemes());
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (entry.Name.HasAnyOfExtensions ("mes", "lib", "a", "a6", "msk", "x"))
        return new LzssStream (input);
    return input;
}
```

### GameRes.Formats.Elf.Ai5ArcIndexReader

#### 状态与常量

```csharp
protected ArcView       m_file ;

protected int           m_count ;

protected List<Entry>   m_dir ;

protected byte[]        m_name_buf = new byte[0x100] ;

static readonly int[] NameLengths = { 0x14, 0x1E, 0x20, 0x100 }
```

#### Ai5ArcIndexReader

```csharp
public Ai5ArcIndexReader (ArcView file, int count) {
    m_file = file;
    m_count = count;
    m_dir = new List<Entry> (m_count);
}
```

#### TrySchemes

```csharp
public List<Entry> TrySchemes (IEnumerable<ArcIndexScheme> schemes) {
    foreach (var scheme in schemes)
    {
        try
        {
            var dir = Read (scheme);
            if (dir != null)
                return dir;
        }
        catch {  }
    }
    return null;
}
```

#### Read

```csharp
public List<Entry> Read (ArcIndexScheme scheme) {
    if (scheme.NameLength > m_name_buf.Length)
        m_name_buf = new byte[scheme.NameLength];
    m_dir.Clear();
    int  index_offset = 4;
    uint index_size = (uint)(m_count * (scheme.NameLength + 8));
    if (index_size > m_file.View.Reserve (index_offset, index_size))
        return null;
    for (int i = 0; i < m_count; ++i)
    {
        m_file.View.Read (index_offset, m_name_buf, 0, (uint)scheme.NameLength);
        string name = DecryptName (scheme);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        index_offset += scheme.NameLength;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = m_file.View.ReadUInt32 (index_offset)   ^ scheme.SizeKey;
        entry.Offset = m_file.View.ReadUInt32 (index_offset+4) ^ scheme.OffsetKey;
        if (entry.Offset < index_size+4 || !entry.CheckPlacement (m_file.MaxOffset))
            return null;
        m_dir.Add (entry);
        index_offset += 8;
    }
    return m_dir;
}
```

#### DecryptName

```csharp
internal string DecryptName (ArcIndexScheme scheme) {
    int n;
    for (n = 0; n < m_name_buf.Length; ++n)
    {
        if (n > scheme.NameLength)
            return null;
        m_name_buf[n] ^= scheme.NameKey;
        if (0 == m_name_buf[n])
            break;
        if (m_name_buf[n] < 0x20)
            return null;
    }
    if (n != 0)
        return Encodings.cp932.GetString (m_name_buf, 0, n);
    else
        return null;
}
```

#### GuessSchemes

```csharp
internal IEnumerable<ArcIndexScheme> GuessSchemes () {
    if (m_count < 2)
        yield break;
    foreach (int name_length in NameLengths)
    {
        uint data_offset = (uint)((name_length + 8) * m_count + 4);
        byte name_key = m_file.View.ReadByte (3 + name_length);
        uint first_size   = m_file.View.ReadUInt32 (4 + name_length);
        uint first_offset = m_file.View.ReadUInt32 (8 + name_length);
        uint offset_key = data_offset ^ first_offset;
        uint second_offset = m_file.View.ReadUInt32 ((name_length+8) * 2) ^ offset_key;
        if (second_offset < data_offset || second_offset >= m_file.MaxOffset)
            continue;
        uint size_key = (second_offset - data_offset) ^ first_size;
        if (0 == offset_key || 0 == size_key)
            continue;
        yield return new ArcIndexScheme {
            NameLength = name_length,
            NameKey = name_key,
            SizeKey = size_key,
            OffsetKey = offset_key,
        };
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/elf/ArcAi5Win.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
