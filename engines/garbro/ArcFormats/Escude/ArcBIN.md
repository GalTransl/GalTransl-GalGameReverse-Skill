# Escude / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/ESC-ARC` / `GameRes.Formats.Escude.BinOpener` | `bin` | `4553432d` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "ARC"))` |
| `BinOpener.TryOpen` | `int version = file.View.ReadByte (7) - '0';` |
| `IndexReader.IndexReader` | `m_seed = m_file.View.ReadUInt32 (8);` |
| `IndexReader.IndexReader` | `m_count = file.View.ReadUInt32 (0xC) ^ NextKey();` |
| `IndexReader.ReadIndexV1` | `var index = m_file.View.ReadBytes (0x10, index_size);` |
| `IndexReader.ReadIndexV1` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset+0x80);` |
| `IndexReader.ReadIndexV1` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset+0x84);` |
| `IndexReader.ReadIndexV2` | `uint names_size = m_file.View.ReadUInt32 (0x10) ^ NextKey();` |
| `IndexReader.ReadIndexV2` | `var index = m_file.View.ReadBytes (0x14, index_size);` |
| `IndexReader.ReadIndexV2` | `var names = m_file.View.ReadBytes (filenames_base, names_size);` |
| `IndexReader.ReadIndexV2` | `int filename_offset = LittleEndian.ToInt32 (index, index_offset);` |
| `IndexReader.ReadIndexV2` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `IndexReader.ReadIndexV2` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Escude.BinOpener

继承/接口：`FVP.BinOpener`。

#### BinOpener

```csharp
public BinOpener () {
    Signatures = new uint[] { 0x2D435345 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "ARC"))
        return null;
    int version = file.View.ReadByte (7) - '0';
    var reader = new IndexReader (file);
    List<Entry> dir = null;
    if (1 == version)
        dir = reader.ReadIndexV1();
    else if (2 == version)
        dir = reader.ReadIndexV2();
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Escude.IndexReader

#### 状态与常量

```csharp
ArcView   m_file ;

uint      m_seed ;

uint      m_count ;
```

#### IndexReader

```csharp
public IndexReader (ArcView file) {
    m_file = file;
    m_seed = m_file.View.ReadUInt32 (8);
    m_count = file.View.ReadUInt32 (0xC) ^ NextKey();
}
```

#### ReadIndexV1

```csharp
public List<Entry> ReadIndexV1 () {
    if (!ArchiveFormat.IsSaneCount ((int)m_count))
        return null;
    uint index_size = m_count * 0x88;
    var index = m_file.View.ReadBytes (0x10, index_size);
    if (index.Length != index_size)
        return null;
    Decrypt (index);
    int index_offset = 0;
    var dir = new List<Entry> ((int)m_count);
    for (uint i = 0; i < m_count; ++i)
    {
        var name = Binary.GetCString (index, index_offset, 0x80);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset+0x80);
        entry.Size   = LittleEndian.ToUInt32 (index, index_offset+0x84);
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return null;
        index_offset += 0x88;
        dir.Add (entry);
    }
    return dir;
}
```

#### ReadIndexV2

```csharp
public List<Entry> ReadIndexV2 () {
    if (!ArchiveFormat.IsSaneCount ((int)m_count))
        return null;

    uint names_size = m_file.View.ReadUInt32 (0x10) ^ NextKey();
    uint index_size = m_count * 12;
    var index = m_file.View.ReadBytes (0x14, index_size);
    if (index.Length != index_size)
        return null;
    uint filenames_base = 0x14 + index_size;
    var names = m_file.View.ReadBytes (filenames_base, names_size);
    if (names.Length != names_size)
        return null;
    Decrypt (index);
    int index_offset = 0;
    var dir = new List<Entry> ((int)m_count);
    for (uint i = 0; i < m_count; ++i)
    {
        int filename_offset = LittleEndian.ToInt32 (index, index_offset);
        if (filename_offset < 0 || filename_offset >= names.Length)
            return null;
        var name = Binary.GetCString (names, filename_offset, names.Length-filename_offset);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset+4);
        entry.Size   = LittleEndian.ToUInt32 (index, index_offset+8);
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return null;
        index_offset += 12;
        dir.Add (entry);
    }
    return dir;
}
```

#### Decrypt

```csharp
unsafe void Decrypt (byte[] data) {
    fixed (byte* raw = data)
    {
        uint* data32 = (uint*)raw;
        for (int i = data.Length/4; i > 0; --i)
        {
            *data32++ ^= NextKey();
        }
    }
}
```

#### NextKey

```csharp
uint NextKey () {
    m_seed ^= 0x65AC9365;
    m_seed ^= (((m_seed >> 1) ^ m_seed) >> 3)
            ^ (((m_seed << 1) ^ m_seed) << 3);
    return m_seed;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Escude/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
