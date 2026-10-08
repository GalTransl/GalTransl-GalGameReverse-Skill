# Ism / ArcISA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ISA` / `GameRes.Formats.ISM.IsaOpener` | `isa` | `49534d20` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IsaOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "ARCHIVED") && !file.View.AsciiEqual(4, "ENGLISH "))` |
| `IsaOpener.TryOpen` | `int count = file.View.ReadInt16 (0x0C);` |
| `IsaOpener.TryOpen` | `int version = file.View.ReadUInt16 (0x0E);` |
| `IsaIndexReader.ReadIndex` | `var name = m_file.View.ReadString (index_offset, name_length);` |
| `IsaIndexReader.ReadIndex` | `entry.Offset = m_file.View.ReadUInt32 (index_offset+4);` |
| `IsaIndexReader.ReadIndex` | `entry.Size = m_file.View.ReadUInt32 (index_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ISM.IsaOpener

继承/接口：`ArchiveFormat`。

#### IsaOpener

```csharp
public IsaOpener () {
    ContainedFormats = new[] { "ISG", "PNG/ISM", "OGG", };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "ARCHIVED") && !file.View.AsciiEqual(4, "ENGLISH "))
        return null;
    int count = file.View.ReadInt16 (0x0C);
    if (!IsSaneCount (count))
        return null;
    int version = file.View.ReadUInt16 (0x0E);
    bool is_encrypted = (version & 0x8000) != 0;
    version &= 0x7FFF;
    var reader = new IsaIndexReader (file, count);
    List<Entry> dir = null;
    if (version != 1)
        dir = reader.ReadIndex (0x0C, 0x14);
    if (null == dir)
        dir = reader.ReadIndex (0x30, 0x10);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.ISM.IsaIndexReader

#### 状态与常量

```csharp
ArcView     m_file ;

List<Entry> m_dir ;

int         m_count ;
```

#### IsaIndexReader

```csharp
public IsaIndexReader (ArcView file, int count) {
    m_file = file;
    m_dir = new List<Entry> (count);
    m_count = count;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex (uint name_length, uint record_length) {
    m_dir.Clear();
    uint index_offset = 0x10;
    for (int i = 0; i < m_count; ++i)
    {
        var name = m_file.View.ReadString (index_offset, name_length);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        index_offset += name_length;
        entry.Offset = m_file.View.ReadUInt32 (index_offset+4);
        entry.Size = m_file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (m_file.MaxOffset))
            return null;
        if (string.IsNullOrEmpty (entry.Type) && name_length < 0x20)
        {
            if (name.EndsWith (".OG"))
                entry.Type = "audio";
            else if (name.EndsWith (".PN"))
                entry.Type = "image";
        }
        m_dir.Add (entry);
        index_offset += record_length;
    }
    return m_dir;
}
```

#### DecryptIndex

```csharp
unsafe void DecryptIndex (byte[] data) {
    int length = data.Length / 4;
    if (0 == length)
        return;
    fixed (byte* data8 = data)
    {
        int* data32 = (int*)data8;
        for (int i = 0; i < length; ++i)
        {
            data32[i] ^= ~(data.Length + length - i);
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ism/ArcISA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
