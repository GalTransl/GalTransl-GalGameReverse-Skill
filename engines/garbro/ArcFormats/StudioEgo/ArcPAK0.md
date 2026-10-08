# StudioEgo / ArcPAK0：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK0/EGO` / `GameRes.Formats.Ego.Pak0Opener` | `dat` | `50414b30` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Pak0Opener.TryOpen` | `uint data_offset   = file.View.ReadUInt32 (4);` |
| `Pak0Opener.TryOpen` | `int  dir_count     = file.View.ReadInt32 (8);` |
| `Pak0Opener.TryOpen` | `int  count         = file.View.ReadInt32 (0xC);` |
| `Pak0Opener.OpenEntry` | `if (entry.Size <= 0x1C \|\| !arc.File.View.AsciiEqual (entry.Offset, "SCR "))` |
| `Pak0Opener.OpenEntry` | `uint version = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `Pak0Opener.OpenEntry` | `uint method  = arc.File.View.ReadUInt32 (entry.Offset+8);` |
| `Pak0Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Pak0Opener.DecryptScript` | `int length = LittleEndian.ToInt32 (script, 0x10);` |
| `Pak0Opener.DecryptScript` | `uint key = LittleEndian.ToUInt32 (script, 0xC);` |
| `Pak0Reader.ReadIndex` | `dirs[i].Parent    = m_file.View.ReadInt32 (index_offset);` |
| `Pak0Reader.ReadIndex` | `dirs[i].LastIndex = m_file.View.ReadInt32 (index_offset+4);` |
| `Pak0Reader.ReadIndex` | `entry.Offset = m_file.View.ReadUInt32 (index_offset);` |
| `Pak0Reader.ReadIndex` | `entry.Size   = m_file.View.ReadUInt32 (index_offset+4);` |
| `Pak0Reader.ReadNextName` | `uint length = m_file.View.ReadByte (m_name_pos++);` |
| `Pak0Reader.ReadNextName` | `var name = m_file.View.ReadString (m_name_pos, length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ego.DirEntry

#### 状态与常量

```csharp
public string   Name ;

public int      Parent ;

public int      LastIndex ;
```

### GameRes.Formats.Ego.Pak0Opener

继承/接口：`ArchiveFormat`。

#### Pak0Opener

```csharp
public Pak0Opener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint data_offset   = file.View.ReadUInt32 (4);
    int  dir_count     = file.View.ReadInt32 (8);
    int  count         = file.View.ReadInt32 (0xC);
    if (data_offset <= 0x14 || data_offset >= file.MaxOffset)
        return null;
    if (!IsSaneCount (dir_count) || !IsSaneCount (count))
        return null;
    var reader = new Pak0Reader (file, data_offset, dir_count, count);
    var dir = reader.ReadIndex();
    return null != dir ? new ArcFile (file, this, dir) : null;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size <= 0x1C || !arc.File.View.AsciiEqual (entry.Offset, "SCR "))
        return base.OpenEntry (arc, entry);
    uint version = arc.File.View.ReadUInt32 (entry.Offset+4);
    uint method  = arc.File.View.ReadUInt32 (entry.Offset+8);
    if (0 == version || !(1 == method || 2 == method))
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptScript (method, data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptScript

```csharp
unsafe void DecryptScript (uint method, byte[] script) {
    int length = LittleEndian.ToInt32 (script, 0x10);
    if (length < 4 || length > script.Length + 0x14)
        return;
    uint key = LittleEndian.ToUInt32 (script, 0xC);
    fixed (byte* data8 = &script[0x14])
    {
        uint* data32 = (uint*)data8;
        length /= 4;
        if (1 == method)
        {
            for (int i = 0; i < length; ++i)
            {
                if (0 == (i & 0xFF))
                    key = 0 == key ? 1u : 0u;
                key += 0x7654321;
                *data32++ ^= key;
            }
        }
        else if (2 == method)
        {
            for (int i = 0; i < length; ++i)
            {
                if (0 == (i & 0xFF))
                    key = ~key;
                key += 0x7654321;
                *data32++ ^= key;
            }
        }
    }
}
```

### GameRes.Formats.Ego.Pak0Reader

#### 状态与常量

```csharp
ArcView     m_file ;

uint        m_data_offset ;

int         m_dir_count ;

int         m_count ;

uint        m_name_pos ;
```

#### Pak0Reader

```csharp
public Pak0Reader (ArcView file, uint data_offset, int dir_count, int file_count) {
    m_file = file;
    m_data_offset   = data_offset;
    m_dir_count     = dir_count;
    m_count         = file_count;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    if (m_data_offset > m_file.View.Reserve (0, m_data_offset))
        return null;
    uint index_offset = 0x10;
    m_name_pos = index_offset + (uint)m_dir_count * 8u + (uint)m_count * 0x10u;
    var dirs = new DirEntry[m_dir_count];
    for (int i = 0; i < m_dir_count; ++i)
    {
        dirs[i].Parent    = m_file.View.ReadInt32 (index_offset);
        dirs[i].LastIndex = m_file.View.ReadInt32 (index_offset+4);
        if (dirs[i].Parent >= m_dir_count || dirs[i].Parent == i)
            return null;
        if (-1 != dirs[i].Parent)
            dirs[i].Name = ReadNextName();
        index_offset += 8;
    }
    var files = new List<Entry> (m_count);
    int current = 0;
    for (int i = 0; i < m_dir_count; ++i)
    {
        string parent_dir = GetPath (dirs, i);
        while (current < dirs[i].LastIndex)
        {
            string name = Path.Combine (parent_dir, ReadNextName());
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = m_file.View.ReadUInt32 (index_offset);
            entry.Size   = m_file.View.ReadUInt32 (index_offset+4);
            files.Add (entry);
            index_offset += 0x10;
            ++current;
        }
    }
    return files;
}
```

#### GetPath

```csharp
string GetPath (IList<DirEntry> dirs, int dir_index) {
    List<string> path = new List<string> (2);
    for (int i = dir_index; dirs[i].Parent != -1; i = dirs[i].Parent)
        path.Add (dirs[i].Name);
    if (0 == path.Count)
        return string.Empty;
    path.Reverse();
    return Path.Combine (path.ToArray());
}
```

#### ReadNextName

```csharp
string ReadNextName () {
    uint length = m_file.View.ReadByte (m_name_pos++);
    var name = m_file.View.ReadString (m_name_pos, length);
    m_name_pos += length;
    return name;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/StudioEgo/ArcPAK0.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
