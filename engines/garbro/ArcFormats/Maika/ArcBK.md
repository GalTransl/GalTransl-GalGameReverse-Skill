# Maika / ArcBK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/BK` / `GameRes.Formats.Maika.BkOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BkOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0);` |
| `BkOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `BkOpener.TryOpen` | `int count = index.ReadInt32();` |
| `BkOpener.TryOpen` | `uint offset         = index.ReadUInt32();` |
| `BkOpener.TryOpen` | `uint size           = index.ReadUInt32();` |
| `BkOpener.TryOpen` | `uint unpacked_size  = index.ReadUInt32();` |
| `BkOpener.TryOpen` | `var name = index.ReadCString (0x104);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Maika.BkOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (0);
    uint index_size = file.View.ReadUInt32 (4);
    if (index_offset+index_size != file.MaxOffset)
        return null;
    using (var input = file.CreateStream (index_offset, index_size))
    using (var packed = new PackedStream<LzBitsDecompressor> (input))
    using (var index = new BinaryStream (packed, file.Name))
    {
        int count = index.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            uint offset         = index.ReadUInt32();
            uint size           = index.ReadUInt32();
            uint unpacked_size  = index.ReadUInt32();
            var name = index.ReadCString (0x104);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset        = offset;
            entry.Size          = size;
            entry.UnpackedSize  = unpacked_size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            if (name.HasExtension (".gpt"))
                entry.Type = "image";
            entry.IsPacked = entry.Size != entry.UnpackedSize;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    input = new PackedStream<LzBitsDecompressor> (input);
    input = new LimitStream (input, pent.UnpackedSize);
    if (entry.Name.HasExtension (".gpa"))
        input = new XoredStream (input, 0xFF);
    return input;
}
```

### GameRes.Formats.Maika.LzBitsDecompressor

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
MsbBitStream        m_input ;

bool m_disposed = false ;
```

#### Initialize

```csharp
public override void Initialize (Stream input) {
    m_input = new MsbBitStream (input, true);
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    var frame = new byte[0x400];
    int frame_pos = 1;
    for (;;)
    {
        int bit = m_input.GetNextBit();
        if (-1 == bit)
            yield break;
        if (bit != 0)
        {
            int v = m_input.GetBits (8);
            if (-1 == v)
                yield break;
            m_buffer[m_pos++] = frame[frame_pos++ & 0x3FF] = (byte)v;
            if (0 == --m_length)
                yield return m_pos;
        }
        else
        {
            int offset = m_input.GetBits (10);
            if (-1 == offset)
                yield break;
            int count = m_input.GetBits (5);
            if (-1 == count)
                yield break;
            count += 2;
            while (count-- > 0)
            {
                byte v = frame[offset++ & 0x3FF];
                m_buffer[m_pos++] = frame[frame_pos++ & 0x3FF] = v;
                if (0 == --m_length)
                    yield return m_pos;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Maika/ArcBK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
