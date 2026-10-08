# uGOS / ArcDET：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DET` / `GameRes.Formats.uGOS.DetOpener` | `det` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DetIndexReader.DetIndexReader` | `m_names = name_file.View.ReadBytes (0, (uint)name_file.MaxOffset);` |
| `DetIndexReader.ReadIndex` | `int name_offset = m_index.View.ReadInt32 (idx_offset);` |
| `DetIndexReader.ReadIndex` | `entry.Offset = m_index.View.ReadUInt32 (idx_offset + 4);` |
| `DetIndexReader.ReadIndex` | `entry.Size = m_index.View.ReadUInt32 (idx_offset + 8);` |
| `DetIndexReader.ReadIndex` | `entry.UnpackedSize = m_index.View.ReadUInt32 (idx_offset + 0x10);` |
| `RleDecompressor.Unpack` | `int ctl = m_input.ReadByte();` |
| `RleDecompressor.Unpack` | `ctl = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.uGOS.DetOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".det"))
        return null;
    var name_file = Path.ChangeExtension (file.Name, "nme");
    if (!VFS.FileExists (name_file))
        return null;
    uint entry_size = 0x10;
    var index_file = Path.ChangeExtension (file.Name, "atm");
    if (!VFS.FileExists (index_file))
    {
        index_file = Path.ChangeExtension (index_file, "at2");
        if (!VFS.FileExists (index_file))
            return null;
        entry_size = 0x14;
    }
    using (var nme = VFS.OpenView (name_file))
    using (var idx = VFS.OpenView (index_file))
    {
        var reader = new DetIndexReader (file, name_file: nme, index_file: idx);
        var dir = reader.ReadIndex (entry_size);
        if (null == dir && entry_size != 0x14)
            dir = reader.ReadIndex (0x14);
        if (null == dir)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new PackedStream<RleDecompressor> (input);
}
```

### GameRes.Formats.uGOS.DetIndexReader

#### 状态与常量

```csharp
ArcView     m_arc ;

ArcView     m_index ;

byte[]      m_names ;

List<Entry> m_dir ;
```

#### DetIndexReader

```csharp
public DetIndexReader (ArcView arc_file, ArcView name_file, ArcView index_file) {
    m_arc = arc_file;
    m_names = name_file.View.ReadBytes (0, (uint)name_file.MaxOffset);
    m_index = index_file;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex (uint entry_size) {
    int count = (int)(m_index.MaxOffset / entry_size);
    if (!ArchiveFormat.IsSaneCount (count))
        return null;
    if (null == m_dir)
        m_dir = new List<Entry> (count);
    else
        m_dir.Clear();
    uint idx_offset = 0;
    for (int i = 0; i < count; ++i)
    {
        if (idx_offset + entry_size > m_index.MaxOffset)
            return null;
        int name_offset = m_index.View.ReadInt32 (idx_offset);
        if (name_offset < 0 || name_offset >= m_names.Length)
            return null;
        var name = Binary.GetCString (m_names, name_offset, m_names.Length - name_offset);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = m_index.View.ReadUInt32 (idx_offset + 4);
        entry.Size = m_index.View.ReadUInt32 (idx_offset + 8);
        if (!entry.CheckPlacement (m_arc.MaxOffset))
            return null;
        entry.IsPacked = true;
        if (entry_size >= 0x14)
            entry.UnpackedSize = m_index.View.ReadUInt32 (idx_offset + 0x10);
        if (name.EndsWith (".bmp.txt", StringComparison.OrdinalIgnoreCase))
            entry.Type = "image";
        m_dir.Add (entry);
        idx_offset += entry_size;
    }
    return m_dir;
}
```

### GameRes.Formats.uGOS.RleDecompressor

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
    var frame = new byte[0x100];
    int frame_pos = 0;
    const int frame_mask = 0xFF;
    for (;;)
    {
        int ctl = m_input.ReadByte();
        if (-1 == ctl)
            yield break;
        if (0xFF != ctl)
        {
            m_buffer[m_pos++] = frame[frame_pos++ & frame_mask] = (byte)ctl;
            if (0 == --m_length)
                yield return m_pos;
        }
        else
        {
            ctl = m_input.ReadByte();
            if (-1 == ctl)
                yield break;
            if (0xFF == ctl)
            {
                m_buffer[m_pos++] = frame[frame_pos++ & frame_mask] = 0xFF;
                if (0 == --m_length)
                    yield return m_pos;
            }
            else
            {
                int offset = frame_pos - ((ctl >> 2) + 1);
                int count = (ctl & 3) + 3;
                while (count --> 0)
                {
                    byte v = frame[offset++ & frame_mask];
                    m_buffer[m_pos++] = frame[frame_pos++ & frame_mask] = v;
                    if (0 == --m_length)
                        yield return m_pos;
                }
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/uGOS/ArcDET.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
