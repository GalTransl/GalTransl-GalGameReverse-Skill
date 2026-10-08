# elf / ArcAi5DAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/AI5WIN` / `GameRes.Formats.Elf.DatAI5Opener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatAI5Opener.TryOpen` | `uint key = file.View.ReadUInt32 (4);` |
| `DatAI5Opener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (0) ^ key);` |
| `DatAI5Opener.TryOpen` | `byte name_key = file.View.ReadByte (0x23);` |
| `Ai5DatIndexReader.Read` | `uint size   = m_file.View.ReadUInt32 (index_offset)   ^ scheme.SizeKey;` |
| `Ai5DatIndexReader.Read` | `uint offset = m_file.View.ReadUInt32 (index_offset+4) ^ scheme.OffsetKey;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Elf.DatAI5Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint key = file.View.ReadUInt32 (4);
    int count = (int)(file.View.ReadUInt32 (0) ^ key);
    if (!IsSaneCount (count))
        return null;
    byte name_key = file.View.ReadByte (0x23);
    var scheme = new ArcIndexScheme {
        NameLength = 0x14, NameKey = name_key, SizeKey = key, OffsetKey = key
    };
    var reader = new Ai5DatIndexReader (file, count);
    var dir = reader.Read (scheme);
    if (dir != null)
        return new ArcFile (file, this, dir);
    return null;
}
```

### GameRes.Formats.Elf.Ai5DatIndexReader

继承/接口：`Ai5ArcIndexReader`。

#### Read

```csharp
new public List<Entry> Read (ArcIndexScheme scheme) {
    if (scheme.NameLength > m_name_buf.Length)
        m_name_buf = new byte[scheme.NameLength];
    m_dir.Clear();
    int  index_offset = 8;
    uint index_size = (uint)(m_count * (scheme.NameLength + 8));
    if (index_size > m_file.View.Reserve (index_offset, index_size))
        return null;
    for (int i = 0; i < m_count; ++i)
    {
        uint size   = m_file.View.ReadUInt32 (index_offset)   ^ scheme.SizeKey;
        uint offset = m_file.View.ReadUInt32 (index_offset+4) ^ scheme.OffsetKey;
        if (offset < index_size+8)
            return null;
        index_offset += 8;
        m_file.View.Read (index_offset, m_name_buf, 0, (uint)scheme.NameLength);
        string name = DecryptName (scheme);
        if (null == name)
            return null;
        index_offset += scheme.NameLength;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return null;
        m_dir.Add (entry);
    }
    return m_dir;
}
```

## 配套算法与外部条件

- [ArcFormats/elf/ArcAi5Win.cs](ArcAi5Win.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/elf/ArcAi5DAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
