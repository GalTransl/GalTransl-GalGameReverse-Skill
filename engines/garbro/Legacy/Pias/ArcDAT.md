# Pias / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PIAS` / `GameRes.Formats.Pias.DatOpener` | `dat` | `26c00200` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IndexReader.FillEntries` | `entry.Size = m_arc.View.ReadUInt32 (entry.Offset) + header_size;` |
| `IndexReader.FillEntries` | `uint entry_size = m_arc.View.ReadUInt32(offset);` |
| `DatOpener.OpenAudioEntry` | `uint size = arc.File.View.ReadUInt32 (entry.Offset);` |
| `TextReader.GetResourceList` | `byte op_code = m_input.ReadUInt8();` |
| `TextReader.GetResourceList` | `uint offset = m_input.ReadUInt32();` |
| `TextReader.ReadInt` | `int result = m_input.ReadUInt8();` |
| `TextReader.ReadInt` | `result = (result & 0x3F) << 8 \| m_input.ReadUInt8();` |
| `TextReader.ReadInt` | `result = result << 8 \| m_input.ReadUInt8();` |
| `TextReader.ReadInt` | `return result << 8 \| m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum ResourceType
    {
        Undefined = -1,
        Graphics = 1,
        Sound = 2,
    }
```

### GameRes.Formats.Pias.IndexReader

#### 状态与常量

```csharp
internal const bool UseOffsetAsName = true ;

protected ArcView       m_arc ;

protected ResourceType  m_res ;

protected List<Entry>   m_dir ;

public bool IsEncrypted { get; protected set; }
```

#### IndexReader

```csharp
public IndexReader (ArcView arc, ResourceType res) {
    m_arc = arc;
    m_res = res;
    m_dir = null;
}
```

#### GetIndex

```csharp
public List<Entry> GetIndex () {
    if (m_res > 0)
    {
        var text_name = VFS.ChangeFileName (m_arc.Name, "text.dat");
        if (!VFS.FileExists (text_name))
            return null;
        IBinaryStream input = VFS.OpenBinaryStream (text_name);
        try
        {
            if (DatOpener.EncryptedSignatures.Contains (input.Signature))
                return null;
            var reader = new TextReader (input);
            m_dir = reader.GetResourceList ((int)m_res);
        }
        finally
        {
            input.Dispose();
        }
    }
    if (null == m_dir)
        m_dir = new List<Entry>();
    if (!FillEntries())
        return null;
    return m_dir;
}
```

#### FillEntries

```csharp
protected bool FillEntries () {
    uint header_size = 4;
    string entry_type = "audio";
    if (ResourceType.Graphics == m_res)
    {
        header_size = 8;
        entry_type = "image";
    }
    for (int i = m_dir.Count - 1; i >= 0; --i)
    {
        var entry = m_dir[i];
        entry.Size = m_arc.View.ReadUInt32 (entry.Offset) + header_size;
        entry.Name = i.ToString("D4");
        entry.Type = entry_type;
    }
    var known_offsets = new HashSet<long> (m_dir.Select (e => e.Offset));
    long offset = 0;
    while (offset < m_arc.MaxOffset)
    {
        uint entry_size = m_arc.View.ReadUInt32(offset);
        if (uint.MaxValue == entry_size)
        {
            entry_size = 4;
        }
        else
        {
            entry_size += header_size;
            if (!known_offsets.Contains (offset))
            {
                var entry = new Entry {
                    Name = GetName (offset, m_dir.Count),
                    Type = entry_type,
                    Offset = offset,
                    Size = entry_size,
                };
                if (!entry.CheckPlacement (m_arc.MaxOffset))
                    return false;
                m_dir.Add (entry);
            }
        }
        offset += entry_size;
    }
    return true;
}
```

#### GetName

```csharp
internal string GetName (long offset, int num) {
    return UseOffsetAsName ? offset.ToString ("D8") : num.ToString("D4");
}
```

### GameRes.Formats.Pias.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal static readonly HashSet<uint> EncryptedSignatures = new HashSet<uint> { 0x03184767u }
```

#### DatOpener

```csharp
public DatOpener () {
    Signatures = new[] { 0x0002C026u, 0u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name).ToLowerInvariant();

    ResourceType resource_type = ResourceType.Undefined;
    if ("sound.dat" == arc_name)
        resource_type = ResourceType.Sound;
    else if ("graph.dat" == arc_name)
        resource_type = ResourceType.Graphics;
    else if ("voice.dat" != arc_name && "music.dat" != arc_name)
        return null;

    var index = new IndexReader (file, resource_type);
    var dir = index.GetIndex();
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Type != "audio")
        return base.OpenEntry (arc, entry);
    var format = new WaveFormat
    {
        FormatTag = 1,
        SamplesPerSecond = 22050,
        BitsPerSample = 8,
    };
    if (VFS.IsPathEqualsToFileName (arc.File.Name, "sound.dat"))
    {
        format.Channels = 2;
        format.BlockAlign = 2;
    }
    else
    {
        format.Channels = 1;
        format.BlockAlign = 1;
    }
    format.SetBPS();
    return OpenAudioEntry (arc, entry, format);
}
```

#### OpenAudioEntry

```csharp
public Stream OpenAudioEntry (ArcFile arc, Entry entry, WaveFormat format) {
    uint size = arc.File.View.ReadUInt32 (entry.Offset);
    byte[] header;
    using (var buffer = new MemoryStream())
    {
        WaveAudio.WriteRiffHeader (buffer, format, size);
        header = buffer.ToArray();
    }
    var data = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
    return new PrefixStream (header, data);
}
```

### GameRes.Formats.Pias.TextReader

#### 状态与常量

```csharp
IBinaryStream m_input ;
```

#### TextReader

```csharp
public TextReader (IBinaryStream input) {
    m_input = input;
}
```

#### GetResourceList

```csharp
public List<Entry> GetResourceList (int resource_type) {
    List<Entry> dir = null;
    while (m_input.PeekByte() != -1)
    {
        byte op_code = m_input.ReadUInt8();
        if (op_code != 0x68)
        {
            Trace.WriteLine (string.Format ("unknown opcode 0x{0:X2} in text.dat", op_code), "DAT/PIAS");
            return null;
        }
        int type = ReadInt();
        int count = ReadInt();
        Action<uint> action = off => {};
        if (type == resource_type)
        {
            if (!ArchiveFormat.IsSaneCount (count))
                return null;
            dir = new List<Entry> (count);
            action = off => dir.Add (new Entry { Offset = off });
        }
        for (int i = 0; i < count; ++i)
        {
            uint offset = m_input.ReadUInt32();
            action (offset);
        }
        if (type == resource_type)
            break;
    }
    return dir;
}
```

#### ReadInt

```csharp
private int ReadInt () {
    int result = m_input.ReadUInt8();
    int code = result & 0xC0;
    if (0 == code)
        return result;
    result = (result & 0x3F) << 8 | m_input.ReadUInt8();
    if (0x40 == code)
        return result;
    result = result << 8 | m_input.ReadUInt8();
    if (0x80 == code)
        return result;
    return result << 8 | m_input.ReadUInt8();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Pias/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
