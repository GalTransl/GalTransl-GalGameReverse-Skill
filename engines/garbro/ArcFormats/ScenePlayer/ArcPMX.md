# ScenePlayer / ArcPMX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PMX` / `GameRes.Formats.ScenePlayer.PmxOpener` | `pmx` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PmxOpener.TryOpen` | `\|\| file.View.ReadByte (0) != (0x78^0x21))` |
| `PmxOpener.TryOpen` | `int count = index.ReadInt32();` |
| `PmxOpener.TryOpen` | `var name = index.ReadCString (0x20);` |
| `PmxOpener.TryOpen` | `uint size = index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ScenePlayer.PmxOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".pmx")
        || file.View.ReadByte (0) != (0x78^0x21))
        return null;

    var input = CreatePmxStream (file);
    bool index_complete = false;
    try
    {
        using (var index = new BinaryStream (input, file.Name, true))
        {
            int count = index.ReadInt32();
            if (!IsSaneCount (count))
                return null;
            var dir = new List<Entry> (count);
            uint data_offset = 4 + (uint)count * 0x24;
            for (int i = 0; i < count; ++i)
            {
                var name = index.ReadCString (0x20);

                if (string.IsNullOrWhiteSpace (name) || Path.IsPathRooted (name))
                    return null;
                uint size = index.ReadUInt32();
                var entry = new Entry {
                    Name = name,
                    Type = "script",
                    Offset = data_offset,
                    Size =  size,
                };
                dir.Add (entry);
                data_offset += size;
            }
            index_complete = true;
            return new PmxArchive (file, this, dir, input);
        }
    }
    finally
    {
        if (!index_complete)
            input.Dispose();
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = (PmxArchive)arc;
    return new StreamRegion (parc.BaseStream, entry.Offset, entry.Size, true);
}
```

#### CreatePmxStream

```csharp
internal Stream CreatePmxStream (ArcView file) {
    Stream input = file.CreateStream();
    input = new XoredStream (input, 0x21);
    input = new ZLibStream (input, CompressionMode.Decompress);
    return new SeekableStream (input);
}
```

### GameRes.Formats.ScenePlayer.PmxArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Stream BaseStream ;

bool m_disposed = false ;
```

#### PmxArchive

```csharp
public PmxArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Stream base_stream)
    : base (arc, impl, dir) {
    BaseStream = base_stream;
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ScenePlayer/ArcPMX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
