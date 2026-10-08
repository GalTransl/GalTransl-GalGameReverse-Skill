# Kaguya / ArcKaguya：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/ARI` / `GameRes.Formats.Kaguya.ArcOpener` | `arc` | `57464c31` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.OpenEntry` | `packed_entry.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset-4);` |
| `IndexReader.ReadAriIndex` | `int name_len = ari.View.ReadInt32 (index_offset);` |
| `IndexReader.ReadAriIndex` | `entry.Mode = ari.View.ReadUInt16 (index_offset);` |
| `IndexReader.ReadAriIndex` | `entry.Size = ari.View.ReadUInt32 (index_offset+2);` |
| `IndexReader.BuildIndex` | `int name_len = file.View.ReadInt32 (arc_offset);` |
| `IndexReader.BuildIndex` | `entry.Mode = file.View.ReadUInt16 (arc_offset);` |
| `IndexReader.BuildIndex` | `entry.Size = file.View.ReadUInt32 (arc_offset+2);` |
| `IndexReader.BuildIndex` | `entry.UnpackedSize = file.View.ReadUInt32 (arc_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.AriEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public ushort   Mode ;
```

### GameRes.Formats.Kaguya.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
    ContainedFormats = new[] { "AP", "APS3", "OGG", "DAT/GENERIC" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var reader = new IndexReader (this);
    var dir = reader.ReadIndex (file);
    if (null == dir || 0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var packed_entry = entry as PackedEntry;
    if (null == packed_entry || !packed_entry.IsPacked)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    if (0 == packed_entry.UnpackedSize)
        packed_entry.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset-4);
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    using (var reader = new LzReader (input, entry.Size, packed_entry.UnpackedSize))
    {
        reader.Unpack();
        return new BinMemoryStream (reader.Data, entry.Name);
    }
}
```

### GameRes.Formats.Kaguya.IndexReader

#### 状态与常量

```csharp
ArchiveFormat   m_format ;

byte[]          m_name_buf = new byte[0x20] ;

List<Entry>     m_dir = new List<Entry>() ;
```

#### IndexReader

```csharp
public IndexReader (ArchiveFormat format) {
    m_format = format;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex (ArcView file) {
    string ari_name = Path.ChangeExtension (file.Name, "ari");
    List<Entry> dir = null;
    if (file.Name != ari_name && VFS.FileExists (ari_name))
        dir = ReadAriIndex (file, ari_name);
    if (null == dir || 0 == dir.Count)
        dir = BuildIndex (file);
    return dir;
}
```

#### ReadAriIndex

```csharp
List<Entry> ReadAriIndex (ArcView file, string ari_name) {
    long arc_offset = 4;
    using (var ari = VFS.OpenView (ari_name))
    {
        long index_offset = 0;
        while (index_offset+4 < ari.MaxOffset)
        {
            int name_len = ari.View.ReadInt32 (index_offset);
            var name = ReadName (ari, index_offset+4, name_len);
            if (null == name)
                return null;
            var entry = new AriEntry { Name = name };
            index_offset += name_len + 4;
            entry.Mode = ari.View.ReadUInt16 (index_offset);
            entry.Size = ari.View.ReadUInt32 (index_offset+2);
            entry.UnpackedSize = 0;
            SetType (entry);
            index_offset += 6;
            arc_offset += name_len + 10;
            if (1 == entry.Mode)
            {
                entry.IsPacked = true;
                arc_offset += 4;
            }
            entry.Offset = arc_offset;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            arc_offset += entry.Size;
            m_dir.Add (entry);
        }
    }
    return m_dir;
}
```

#### BuildIndex

```csharp
List<Entry> BuildIndex (ArcView file) {
    long arc_offset = 4;
    while (arc_offset+4 < file.MaxOffset)
    {
        int name_len = file.View.ReadInt32 (arc_offset);
        var name = ReadName (file, arc_offset+4, name_len);
        if (null == name)
            return null;
        var entry = new AriEntry { Name = name };
        arc_offset += name_len + 4;
        entry.Mode = file.View.ReadUInt16 (arc_offset);
        entry.Size = file.View.ReadUInt32 (arc_offset+2);
        SetType (entry);
        arc_offset += 6;
        if (1 == entry.Mode)
        {
            entry.IsPacked = true;
            entry.UnpackedSize = file.View.ReadUInt32 (arc_offset);
            arc_offset += 4;
        }
        entry.Offset = arc_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        arc_offset += entry.Size;
        m_dir.Add (entry);
    }
    return m_dir;
}
```

#### SetType

```csharp
void SetType (AriEntry entry) {
    if (2 == entry.Mode)
        entry.Type = "audio";
    else if (1 == entry.Mode)
        entry.Type = "image";
    else
        entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name, m_format.ContainedFormats);
}
```

#### ReadName

```csharp
string ReadName (ArcView file, long offset, int name_len) {
    if (name_len <= 0 || offset+name_len+6 > file.MaxOffset || name_len > 0x100)
        return null;
    if (name_len > m_name_buf.Length)
        m_name_buf = new byte[name_len];
    file.View.Read (offset, m_name_buf, 0, (uint)name_len);
    return DecryptName (m_name_buf, name_len).TrimStart ('\\');
}
```

#### DecryptName

```csharp
string DecryptName (byte[] name_buf, int name_len) {
    for (int i = 0; i < name_len; ++i)
        name_buf[i] ^= 0xff;
    return Encodings.cp932.GetString (name_buf, 0, name_len);
}
```

### GameRes.Formats.Kaguya.LzReader

继承/接口：`IDisposable`, `IDataUnpacker`。

#### 状态与常量

```csharp
MsbBitStream    m_input ;

byte[]          m_output ;

public byte[] Data { get { return m_output; } }

bool _disposed = false ;
```

#### LzReader

```csharp
public LzReader (Stream input, uint packed_size, uint unpacked_size) {
    m_input = new MsbBitStream (input, true);
    m_output = new byte[unpacked_size];
}
```

#### Unpack

```csharp
public void Unpack () {
    int dst = 0;
    int frame_pos = 1;
    byte[] frame = new byte[4096];
    int frame_mask = frame.Length - 1;

    while (dst < m_output.Length)
    {
        int bit = m_input.GetNextBit();
        if (-1 == bit)
            break;
        if (0 != bit)
        {
            int data = m_input.GetBits (8);
            m_output[dst++] = (byte)data;
            frame[frame_pos++] = (byte)data;
            frame_pos &= frame_mask;
        }
        else
        {
            int win_offset = m_input.GetBits (12);
            if (-1 == win_offset || 0 == win_offset)
                break;

            int count = m_input.GetBits(4) + 2;
            for (int i = 0; i < count; i++)
            {
                byte data = frame[(win_offset + i) & frame_mask];
                m_output[dst++] = data;
                frame[frame_pos++] = data;
                frame_pos &= frame_mask;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcKaguya.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
