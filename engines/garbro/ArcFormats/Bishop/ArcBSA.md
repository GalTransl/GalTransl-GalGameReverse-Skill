# Bishop / ArcBSA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BSA` / `GameRes.Formats.Bishop.BsaOpener` | `bsa` | `42534172` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BsaOpener.TryOpen` | `if ('c' != file.View.ReadInt16 (4))` |
| `BsaOpener.TryOpen` | `int version = file.View.ReadInt16 (8);` |
| `BsaOpener.TryOpen` | `int count = file.View.ReadInt16 (0xA);` |
| `BsaOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xC);` |
| `IndexReader.ReadV1` | `string name = m_file.View.ReadString (index_offset, 0x20);` |
| `IndexReader.ReadV1` | `entry.Offset = m_file.View.ReadUInt32 (index_offset+0x20);` |
| `IndexReader.ReadV1` | `entry.Size   = m_file.View.ReadUInt32 (index_offset+0x24);` |
| `IndexReader.ReadV2` | `int name_offset = m_file.View.ReadInt32 (index_offset);` |
| `IndexReader.ReadV2` | `entry.Offset = m_file.View.ReadUInt32 (index_offset+4);` |
| `IndexReader.ReadV2` | `entry.Size   = m_file.View.ReadUInt32 (index_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Bishop.BsaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if ('c' != file.View.ReadInt16 (4))
        return null;
    int version = file.View.ReadInt16 (8);
    if (version < 1 || version > 3)
        return null;
    int count = file.View.ReadInt16 (0xA);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (0xC);
    if (index_offset >= file.MaxOffset)
        return null;
    var reader = new IndexReader (file);
    List<Entry> dir = null;
    if (version > 1)
        dir = reader.ReadV2 (count, index_offset);
    if (null == dir)
        dir = reader.ReadV1 (count, index_offset);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Bishop.IndexReader

#### 状态与常量

```csharp
ArcView         m_file ;

List<Entry>     m_dir ;

List<string>    m_path ;
```

#### IndexReader

```csharp
public IndexReader (ArcView file) {
    m_file = file;
    m_dir = new List<Entry>();
    m_path = new List<string>();
}
```

#### ReadV1

```csharp
public List<Entry> ReadV1 (int count, uint index_offset) {
    m_file.View.Reserve (index_offset, (uint)(m_file.MaxOffset - index_offset));
    m_dir.Capacity = count;
    m_dir.Clear();
    m_path.Clear();
    for (int i = 0; i < count; ++i)
    {
        string name = m_file.View.ReadString (index_offset, 0x20);
        if (0 == name.Length)
            return null;
        if ('>' == name[0])
        {
            m_path.Add (name.Substring (1));
        }
        else if ('<' == name[0])
        {
            if (m_path.Count > 0)
                m_path.RemoveAt (m_path.Count-1);
        }
        else
        {
            if (m_path.Count > 0)
                name = Path.Combine (GetPathName (name).ToArray());
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = m_file.View.ReadUInt32 (index_offset+0x20);
            entry.Size   = m_file.View.ReadUInt32 (index_offset+0x24);
            if (!entry.CheckPlacement (m_file.MaxOffset))
                return null;
            m_dir.Add (entry);
        }
        index_offset += 0x28;
    }
    return m_dir;
}
```

#### ReadV2

```csharp
public List<Entry> ReadV2 (int count, uint index_offset) {
    m_file.View.Reserve (index_offset, (uint)(m_file.MaxOffset - index_offset));
    m_dir.Capacity = count;
    m_dir.Clear();
    m_path.Clear();
    uint filenames_offset = index_offset + (uint)(count * 12);
    byte[] names_buf = new byte[m_file.MaxOffset - filenames_offset];
    m_file.View.Read (filenames_offset, names_buf, 0, (uint)names_buf.Length);

    for (int i = 0; i < count; ++i)
    {
        int name_offset = m_file.View.ReadInt32 (index_offset);
        if (name_offset >= names_buf.Length)
            return null;
        string name = Binary.GetCString (names_buf, name_offset, names_buf.Length-name_offset);
        if (0 == name.Length)
            return null;
        if ('>' == name[0])
        {
            m_path.Add (name.Substring (1));
        }
        else if ('<' == name[0])
        {
            if (m_path.Count > 0)
                m_path.RemoveAt (m_path.Count-1);
        }
        else
        {
            if (m_path.Count > 0)
                name = Path.Combine (GetPathName (name).ToArray());
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = m_file.View.ReadUInt32 (index_offset+4);
            entry.Size   = m_file.View.ReadUInt32 (index_offset+8);
            if (!entry.CheckPlacement (m_file.MaxOffset))
                return null;
            m_dir.Add (entry);
        }
        index_offset += 0xC;
    }
    return m_dir;
}
```

#### GetPathName

```csharp
IEnumerable<string> GetPathName (string name) {
    foreach (var dir in m_path)
        yield return dir;
    yield return name;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Bishop/ArcBSA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
