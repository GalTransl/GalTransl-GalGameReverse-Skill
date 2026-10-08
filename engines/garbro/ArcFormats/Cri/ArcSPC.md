# Cri / ArcSPC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SPC/CRI` / `GameRes.Formats.Cri.SpcOpener` | `spc`, `bip` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SpcOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (0);` |
| `XtxIndexBuilder.ReadIndex` | `uint first_offset = m_input.ReadUInt32();` |
| `XtxIndexBuilder.ReadIndex` | `uint offset = m_input.ReadUInt32();` |
| `XtxIndexBuilder.ReadIndex` | `uint size   = m_input.ReadUInt32();` |
| `XtxIndexBuilder.ReadIndex` | `uint signature = m_input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Cri.SpcOpener

继承/接口：`ArchiveFormat`。

#### SpcOpener

```csharp
public SpcOpener () {
    Extensions = new string[] { "spc", "bip" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".spc") && !file.Name.HasExtension(".bip"))
        return null;
    uint unpacked_size = file.View.ReadUInt32 (0);
    if (unpacked_size <= 0x20 || unpacked_size > 0x5000000)
        return null;

    var backend = file.CreateStream();
    backend.Position = 4;
    var lzss = new LzssStream (backend);
    var input = new SeekableStream (lzss);
    var base_name = Path.GetFileNameWithoutExtension(file.Name);
    try
    {
        using (var spc = new XtxIndexBuilder (input, base_name))
        {
            spc.ReadIndex (0);
            if (spc.Dir.Count > 0)
                return new SpcArchive (file, this, spc.Dir, input);
            else
                throw new InvalidFormatException();
        }
    }
    catch
    {

        var dir = new List<Entry>();
        var entry = Create<PackedEntry>(base_name);
        entry.Offset = 0;
        entry.Size = (uint)input.Length;
        entry.Type = "image";
        dir.Add(entry);
        return new SpcArchive(file, this, dir, input);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    return new StreamRegion (((SpcArchive)arc).Source, entry.Offset, entry.Size, true);
}
```

### GameRes.Formats.Cri.XtxIndexBuilder

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
BinaryReader            m_input ;

string                  m_base_name ;

List<Entry>             m_dir = new List<Entry>() ;

int                     m_subdir_count = 0 ;

public List<Entry>      Dir { get { return m_dir; } }

bool _disposed = false ;
```

#### XtxIndexBuilder

```csharp
public XtxIndexBuilder (Stream input, string base_name) {
    m_input = new ArcView.Reader (input);
    m_base_name = base_name;
}
```

#### ReadIndex

```csharp
public void ReadIndex (uint base_offset, string dir_name = "") {
    m_input.BaseStream.Position = base_offset;
    uint first_offset = m_input.ReadUInt32();
    if (0 != (first_offset & 0xF))
        throw new InvalidFormatException();
    int count = (int)(first_offset / 0x10u);
    m_input.BaseStream.Position = base_offset;
    var subdir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = m_input.ReadUInt32();
        uint size   = m_input.ReadUInt32();
        if (offset < first_offset || size < 0x20)
            throw new InvalidFormatException();
        m_input.BaseStream.Seek (8, SeekOrigin.Current);
        var entry = new Entry { Offset = base_offset + offset, Size = size };
        subdir.Add (entry);
    }
    foreach (var entry in subdir)
    {
        m_input.BaseStream.Position = entry.Offset;
        uint signature = m_input.ReadUInt32();
        if (0x787478 == signature)
        {
            var file_name = string.Format ("{0}#{1:D4}.xtx", m_base_name, m_dir.Count);
            entry.Name = Path.Combine (dir_name, file_name);
            entry.Type = "image";
            m_dir.Add (entry);
        }
        else
        {
            var subdir_name = m_subdir_count++.ToString ("D4");
            ReadIndex ((uint)entry.Offset, Path.Combine (dir_name, subdir_name));
        }
    }
}
```

### GameRes.Formats.Cri.SpcArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Stream Source ;

bool _spc_disposed = false ;
```

#### SpcArchive

```csharp
public SpcArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Stream input)
    : base (arc, impl, dir) {
    Source = input;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cri/ArcSPC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
