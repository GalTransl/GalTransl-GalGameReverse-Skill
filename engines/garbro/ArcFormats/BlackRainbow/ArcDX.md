# BlackRainbow / ArcDX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/DX` / `GameRes.Formats.BlackRainbow.PackOpener` | `pak` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `uint index_length = file.View.ReadUInt32 (4);` |
| `PackOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `IndexReader.ReadDir` | `int dir_count = m_index.ReadInt32();` |
| `IndexReader.ReadDir` | `var  name        = m_index.ReadCString (0x20);` |
| `IndexReader.ReadDir` | `uint offset      = m_index.ReadUInt32();` |
| `IndexReader.ReadDir` | `uint data_offset = m_index.ReadUInt32();` |
| `IndexReader.ReadDir` | `int count = m_index.ReadInt32();` |
| `IndexReader.ReadDir` | `var name = m_index.ReadCString (0x20);` |
| `IndexReader.ReadDir` | `entry.Offset = m_index.ReadUInt32() + base_offset;` |
| `IndexReader.ReadDir` | `entry.Size   = m_index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackRainbow.PackOpener

继承/接口：`ArchiveFormat`。

#### PackOpener

```csharp
public PackOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_length = file.View.ReadUInt32 (4);
    if (index_length >= file.MaxOffset)
        return null;
    using (var input = file.CreateStream (0, index_length))
    {
        var reader = new IndexReader (input, file.MaxOffset);
        if (!reader.ReadDir ("", 8, index_length) || 0 == reader.Dir.Count)
            return null;
        return new ArcFile (file, this, reader.Dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!entry.Name.HasExtension (".hse"))
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 0; i < data.Length; ++i)
        data[i] = (byte)-data[i];
    return new BinMemoryStream (data, entry.Name);
}
```

### GameRes.Formats.BlackRainbow.PackOpener.IndexReader

#### 状态与常量

```csharp
IBinaryStream       m_index ;

long                m_max_offset ;

List<Entry>         m_dir ;

public List<Entry> Dir { get { return m_dir; } }
```

#### IndexReader

```csharp
public IndexReader (IBinaryStream input, long max_offset) {
    m_index = input;
    m_max_offset = max_offset;
    m_dir = new List<Entry>();
}
```

#### ReadDir

```csharp
public bool ReadDir (string root, uint dir_offset, uint base_offset) {
    m_index.Position = dir_offset;
    int dir_count = m_index.ReadInt32();
    dir_offset += 4;
    for (int i = 0; i < dir_count; ++i)
    {
        var  name        = m_index.ReadCString (0x20);
        uint offset      = m_index.ReadUInt32();
        uint data_offset = m_index.ReadUInt32();
        if (offset <= dir_offset || offset > m_index.Length || data_offset > m_max_offset)
            return false;
        if (!ReadDir (Path.Combine (root, name), offset, data_offset))
            return false;
        dir_offset += 0x28;
        m_index.Position = dir_offset;
    }
    int count = m_index.ReadInt32();
    if (0 == count)
        return true;
    if (!IsSaneCount (count))
        return false;
    for (int i = 0; i < count; ++i)
    {
        var name = m_index.ReadCString (0x20);
        name = Path.Combine (root, name);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = m_index.ReadUInt32() + base_offset;
        entry.Size   = m_index.ReadUInt32();
        if (!entry.CheckPlacement (m_max_offset))
            return false;
        if (name.HasExtension (".hse"))
            entry.Type = "image";
        m_dir.Add (entry);
    }
    return true;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/BlackRainbow/ArcDX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
