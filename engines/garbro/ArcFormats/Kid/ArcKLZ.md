# Kid / ArcKLZ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `KLZ/KID` / `GameRes.Formats.Kid.KlzOpener` | `klz` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `KlzOpener.TryOpen` | `uint unpacked_size = Binary.BigEndian(file.View.ReadUInt32(0));` |
| `KlzOpener.GetEntries` | `uint sign = m_input.ReadUInt32();` |
| `KlzOpener.GetEntries` | `m_input.ReadBytes(12);` |
| `KlzOpener.GetEntries` | `uint size = m_input.ReadUInt32() + 16;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kid.KlzOpener

继承/接口：`ArchiveFormat`。

#### KlzOpener

```csharp
public KlzOpener() {
    Extensions = new string[] { "klz" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.Name.HasExtension(".klz"))
        return null;
    uint unpacked_size = Binary.BigEndian(file.View.ReadUInt32(0));
    if (unpacked_size <= 0x20 || unpacked_size > 0x5000000)
        return null;

    var backend = file.CreateStream();
    var input = KlzFormat.LzhStreamDecode(backend);
    var base_name = Path.GetFileNameWithoutExtension(file.Name);
    var dir = GetEntries(input, base_name);
    if (dir == null || dir.Count == 0)
    {
        return null;
    }
    else
    {
        return new KlzArchive(file, this, dir, input);
    }

}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    return new StreamRegion(((KlzArchive)arc).Source, entry.Offset, entry.Size, true);
}
```

#### GetEntries

```csharp
internal static List<Entry> GetEntries (Stream input, string base_name) {
    var entries = new List<Entry>();
    BinaryReader m_input = new ArcView.Reader(input);
    int count = 0;
    m_input.BaseStream.Position = 0;
    while (m_input.BaseStream.Position < m_input.BaseStream.Length)
    {
        while (true)
        {
            try
            {
                uint sign = m_input.ReadUInt32();
                m_input.ReadBytes(12);
                if (sign == 0x324D4954)
                {

                    break;
                }
            }
            catch (EndOfStreamException)
            {
                return entries;
            }
        }
        long tell = m_input.BaseStream.Position - 16;
        uint size = m_input.ReadUInt32() + 16;
        string name = base_name + "_" + count.ToString("D2");
        if (tell + size > m_input.BaseStream.Length)
        {
            size = (uint)(m_input.BaseStream.Length - tell);
            name += "_incomplete";
        }
        var entry = new Entry {
            Name = name + ".tm2",
            Size = size,
            Offset = tell,
            Type = "image"
        };
        count++;
        entries.Add(entry);
        m_input.BaseStream.Position = tell + size;
    }
    return entries;
}
```

### GameRes.Formats.Kid.KlzArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Stream Source ;

bool _spc_disposed = false ;
```

#### KlzArchive

```csharp
public KlzArchive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Stream input)
    : base (arc, impl, dir) {
    Source = input;
}
```

## 配套算法与外部条件

- [ArcFormats/Kid/ImageKLZ.cs](ImageKLZ.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kid/ArcKLZ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
