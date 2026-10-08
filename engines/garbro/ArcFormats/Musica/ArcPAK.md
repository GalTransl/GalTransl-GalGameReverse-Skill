# Musica / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK` / `GameRes.Formats.Musica.PakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int count = reader.ReadInt32();` |
| `PakOpener.TryOpen` | `uint indexLen = reader.ReadUInt32();` |
| `PakOpener.TryOpen` | `string name = input.ReadCString();` |
| `PakOpener.TryOpen` | `uint size = reader.ReadUInt32();` |
| `PakOpener.TryOpen` | `uint offset = reader.ReadUInt32();` |
| `NegStream.ReadByte` | `public override int ReadByte() {` |
| `NegStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Musica.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly HashSet<string> PakImageNames = new HashSet<string>() {
    "bg", "st",
}

static readonly HashSet<string> PakAudioNames = new HashSet<string>() {
    "bgm", "se", "voice",
}
```

#### PakOpener

```csharp
public PakOpener() {
    Extensions = new[] { "pak" };
    ContainedFormats = new string[] { "PNG", "OGG" };
}
```

#### GetType

```csharp
private string GetType(string pakName, string entryName) {
    if (PakImageNames.Contains(pakName))
    {
        return "image";
    }

    if (PakAudioNames.Contains(pakName))
    {
        return "audio";
    }

    return FormatCatalog.Instance.GetTypeFromName(entryName, ContainedFormats);
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView view) {
    Stream input = view.CreateStream();
    using(input = new NegStream(input))
    {
        using(ArcView.Reader reader = new ArcView.Reader(input))
        {
            int count = reader.ReadInt32();
            if (count <= 0)
            {
                return null;
            }

            List<Entry> entries = new List<Entry>(count);
            for(int i = 0; i < count; ++i)
            {
                uint indexLen = reader.ReadUInt32();
                long indexStart = input.Position;

                string name = input.ReadCString();
                if (string.IsNullOrWhiteSpace(name))
                {
                    return null;
                }
                uint size = reader.ReadUInt32();
                uint offset = reader.ReadUInt32();

                Entry entry = new Entry() { Name = name, Offset = offset, Size = size };
                if (!entry.CheckPlacement(view.MaxOffset))
                {
                    return null;
                }
                entry.Type = this.GetType(Path.GetFileNameWithoutExtension(view.Name), entry.Name);
                entries.Add(entry);

                input.Position = indexStart + indexLen;
            }
            return new PakArchive(view, this, entries, input.Position);
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    if (!(arc is PakArchive pakArc))
    {
        return base.OpenEntry(arc, entry);
    }

    return new NegStream(base.OpenEntry(arc, pakArc.GetEntry(entry)));
}
```

### GameRes.Formats.Musica.PakArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
private long m_IndexSize ;
```

#### PakArchive

```csharp
public PakArchive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, long indexSize) : base(arc, impl, dir) {
    m_IndexSize = indexSize;
}
```

#### GetEntry

```csharp
public Entry GetEntry(Entry e) {
    return new Entry
    {
        Name = e.Name,
        Offset = e.Offset + m_IndexSize,
        Size = e.Size,
        Type = e.Type,
    };
}
```

### GameRes.Formats.Musica.NegStream

继承/接口：`ProxyStream`。

#### 状态与常量

```csharp
byte[] write_buf ;
```

#### Read

```csharp
public override int Read(byte[] buffer, int offset, int count) {
    int read = BaseStream.Read(buffer, offset, count);
    for (int i = 0; i < read; ++i)
    {
        buffer[offset + i] = (byte)-buffer[offset + i];
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte() {
    int b = BaseStream.ReadByte();
    if (-1 != b)
    {
        b = (byte)-b;
    }
    return b;
}
```

#### WriteByte

```csharp
public override void WriteByte(byte value) {
    BaseStream.WriteByte((byte)-value);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Musica/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
