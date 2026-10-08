# Qlie / ArcABMP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ABMP7` / `GameRes.Formats.Qlie.Abmp7Opener` | `b` | `41424d50` | `False` |
| `ABMP/QLIE` / `GameRes.Formats.Qlie.AbmpOpener` | `b` | `61626d70` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AbmpOpener.TryOpen` | `int version = file.View.ReadByte (4) * 10 + file.View.ReadByte (5) - '0' * 11;` |
| `AbmpOpener.TryOpen` | `if (file.View.ReadByte (6) != 0 \|\| version < 10 \|\| version > 12)` |
| `AbmpOpener.OpenEntry` | `if (0xFF435031 != arc.File.View.ReadUInt32 (entry.Offset))` |
| `AbmpOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `AbmpReader.ReadIndex` | `if (Binary.AsciiEqual (type_buf, "abdata"))` |
| `AbmpReader.ReadIndex` | `uint size = m_input.ReadUInt32();` |
| `AbmpReader.ReadIndex` | `else if (Binary.AsciiEqual (type_buf, "abimage10\0") \|\|` |
| `AbmpReader.ReadIndex` | `Binary.AsciiEqual (type_buf, "absound10\0"))` |
| `AbmpReader.ReadIndex` | `int count = m_input.ReadByte();` |
| `AbmpReader.ReadIndex` | `int version = m_input.ReadInt32();` |
| `AbmpReader.ReadIndex` | `int name_length = m_input.ReadUInt16();` |
| `AbmpReader.ReadIndex` | `var name_bytes = m_input.ReadBytes (name_length*2);` |
| `AbmpReader.ReadIndex` | `name_length = m_input.ReadUInt16();` |
| `AbmpReader.ReadIndex` | `name = m_input.ReadCString (name_length);` |
| `AbmpReader.ReadIndex` | `byte type = m_input.ReadUInt8();` |
| `AbmpReader.ReadIndex` | `Skip (m_input.ReadUInt16());` |
| `AbmpReader.ReadIndex` | `m_input.ReadByte();` |
| `AbmpReader.ReadIndex` | `var size = m_input.ReadUInt32();` |
| `AbmpReader.DetectFileType` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `Abmp7Opener.TryOpen` | `if (file.View.ReadUInt16 (4) != '7')` |
| `Abmp7Opener.TryOpen` | `uint size = file.View.ReadUInt32 (offset);` |
| `Abmp7Opener.TryOpen` | `size = file.View.ReadUInt32 (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Qlie.AbmpOpener

继承/接口：`ArchiveFormat`。

#### AbmpOpener

```csharp
public AbmpOpener () {
    Extensions = new string[] { "b" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadByte (4) * 10 + file.View.ReadByte (5) - '0' * 11;
    if (file.View.ReadByte (6) != 0 || version < 10 || version > 12)
        return null;
    using (var reader = new AbmpReader (file, version))
    {
        var dir = reader.ReadIndex();
        if (null == dir || 0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0xFF435031 != arc.File.View.ReadUInt32 (entry.Offset))
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    data = PackOpener.Decompress (data) ?? data;
    return new BinMemoryStream (data, entry.Name);
}
```

### GameRes.Formats.Qlie.AbmpReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
ArcView             m_file ;

IBinaryStream       m_input ;

string              m_base_name ;

int                 m_version ;

List<Entry>         m_dir ;

static readonly Regex s_InvalidChars = new Regex (@"[:/\\*?]") ;

bool _disposed = false ;
```

#### AbmpReader

```csharp
public AbmpReader (ArcView file, int version) {
    m_file = file;
    m_input = file.CreateStream();
    m_base_name = Path.GetFileNameWithoutExtension (file.Name);
    m_version = version;
    m_dir = new List<Entry>();
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    m_input.Position = 0x10;
    int n = 0;
    var type_buf = new byte[0x10];
    while (0x10 == m_input.Read (type_buf, 0, 0x10))
    {
        if (Binary.AsciiEqual (type_buf, "abdata"))
        {
            uint size = m_input.ReadUInt32();
            var entry = new Entry {
                Name = string.Format ("{0}#{1}.dat", m_base_name, n++),
                Offset = m_input.Position,
                Size = size,
            };
            m_dir.Add (entry);
            Skip (size);
        }
        else if (Binary.AsciiEqual (type_buf, "abimage10\0") ||
                 Binary.AsciiEqual (type_buf, "absound10\0"))
        {
            int count = m_input.ReadByte();
            for (int i = 0; i < count; ++i)
            {
                if (0x10 != m_input.Read (type_buf, 0, 0x10))
                    break;
                var tag = Binary.GetCString (type_buf, 0, 0x10, Encoding.ASCII);
                string name = null;
                if ("abimgdat15" == tag)
                {
                    int version = m_input.ReadInt32();
                    int name_length = m_input.ReadUInt16();
                    if (name_length > 0)
                    {
                        var name_bytes = m_input.ReadBytes (name_length*2);
                        name = Encoding.Unicode.GetString (name_bytes);
                    }
                    name_length = m_input.ReadUInt16();
                    if (name_length > 0)
                    {
                        if (string.IsNullOrEmpty (name))
                            name = m_input.ReadCString (name_length);
                        else
                            Skip ((uint)name_length);
                    }
                    byte type = m_input.ReadUInt8();

                    if (2 == version)
                        Skip (0x1D);
                    else
                        Skip (0x11);
                }
                else if ("absnddat12" == tag)
                {
                    int version = m_input.ReadInt32();
                    int name_length = m_input.ReadUInt16();
                    if (name_length > 0)
                    {
                        var name_bytes = m_input.ReadBytes (name_length*2);
                        name = Encoding.Unicode.GetString (name_bytes);
                    }
                    if (m_input.Length - m_input.Position <= 7)
                        break;
                    Skip (7);
                }
                else
                {
                    int name_length = m_input.ReadUInt16();
                    name = m_input.ReadCString (name_length);

                    if (tag != "abimgdat10" && tag != "absnddat10")
                    {
                        Skip (m_input.ReadUInt16());
                        if ("abimgdat13" == tag)
                            Skip (0x0C);
                        else if ("abimgdat14" == tag)
                            Skip (0x4C);
                    }
                    m_input.ReadByte();
                }
                var size = m_input.ReadUInt32();
                if (0 != size)
                {
                    if (string.IsNullOrEmpty (name))
                        name = string.Format ("{0}#{1}", m_base_name, n++);
                    else
                        name = s_InvalidChars.Replace (name, "_");
                    var entry = new Entry {
                        Name = name,
                        Type = tag.StartsWith ("abimg") ? "image" : tag.StartsWith ("absnd") ? "audio" : "",
                        Offset = m_input.Position,
                        Size = size,
                    };
                    if (entry.CheckPlacement (m_file.MaxOffset))
                    {
                        DetectFileType (m_file, entry);
                        m_dir.Add (entry);
                    }
                }
                Skip (size);
            }
        }
        else
        {
            var entry = new Entry {
                Name = string.Format ("{0}#{1}#{2}", m_base_name, n++, GetTypeName (type_buf)),
                Offset = m_input.Position,
                Size = (uint)(m_file.MaxOffset - m_input.Position),
            };
            m_dir.Add (entry);
            Skip (entry.Size);
        }
    }
    return m_dir;
}
```

#### Skip

```csharp
void Skip (uint amount) {
    m_input.Seek (amount, SeekOrigin.Current);
}
```

#### DetectFileType

```csharp
static internal void DetectFileType (ArcView file, Entry entry) {
    uint signature = file.View.ReadUInt32 (entry.Offset);
    var res = AutoEntry.DetectFileType (signature);
    if (null != res)
        entry.ChangeType (res);
}
```

#### GetTypeName

```csharp
static string GetTypeName (byte[] type_buf) {
    if (!type_buf.IsAsciiVisible (0, true))
        return "unknown";
    return Binary.GetCString (type_buf, 0).Trim();
}
```

### GameRes.Formats.Qlie.Abmp7Opener

继承/接口：`AbmpOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt16 (4) != '7')
        return null;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint offset = 0xC;
    var dir = new List<Entry>();
    uint size = file.View.ReadUInt32 (offset);
    offset += 4;
    var entry = new Entry {
        Name = string.Format ("{0}#0.dat", base_name),
        Offset = offset,
        Size = size,
    };
    if (!entry.CheckPlacement (file.MaxOffset))
        return null;
    dir.Add (entry);
    offset += size;
    int n = 1;
    while (offset < file.MaxOffset)
    {
        size = file.View.ReadUInt32 (offset);
        if (0 == size)
            break;
        offset += 4;
        entry = new Entry {
            Name = string.Format ("{0}#{1}", base_name, n++),
            Type = "image",
            Offset = offset,
            Size = size,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            break;
        AbmpReader.DetectFileType (file, entry);
        dir.Add (entry);
        offset += size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/Qlie/ArcQLIE.cs](ArcQLIE.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Qlie/ArcABMP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
