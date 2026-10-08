# Eve / ArcGM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/GM` / `GameRes.Formats.Eve.GmDatOpener` | `dat` | `474d312e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GmDatOpener.TryOpen` | `if (file.View.ReadByte (4) != '0')` |
| `GmDatOpener.TryOpen` | `var signature = index.ReadCString();` |
| `GmDatOpener.TryOpen` | `uint data_offset = index.ReadUInt16();` |
| `GmDatOpener.TryOpen` | `uint index_size = index.ReadUInt32();` |
| `GmDatOpener.TryOpen` | `uint index_offset = index.ReadUInt32();` |
| `GmDatOpener.TryOpen` | `int count = index.ReadInt32();` |
| `GmDatOpener.TryOpen` | `int key_length = index.ReadUInt16();` |
| `GmDatOpener.TryOpen` | `int flags = index.ReadUInt16();` |
| `GmDatOpener.TryOpen` | `var key = index.ReadBytes (key_length);` |
| `GmDatOpener.TryOpen` | `uint offset = index.ReadUInt32() + data_offset;` |
| `GmDatOpener.TryOpen` | `uint size   = index.ReadUInt32();` |
| `GmDatOpener.TryOpen` | `int name_len = index.ReadUInt8();` |
| `GmDatOpener.TryOpen` | `var name = index.ReadCString (name_len);` |
| `GmDatOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (entry.Offset, 25);` |
| `GmDatOpener.OpenEntry` | `int unpacked_size = header.ToInt32 (6);` |
| `GmDatOpener.OpenEntry` | `if (data.AsciiEqual ("BPR01"))` |
| `BprDecompressor.Unpack` | `int ctl = m_input.ReadByte();` |
| `BprDecompressor.Unpack` | `int count = m_input.ReadInt32();` |
| `BprDecompressor.Unpack` | `byte v = m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Eve.GmDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadByte (4) != '0')
        return null;
    using (var index = file.CreateStream())
    {
        var signature = index.ReadCString();
        index.Position = (((int)index.Position + 4) >> 2) << 2;
        uint data_offset = index.ReadUInt16();
        uint index_size = index.ReadUInt32();
        uint index_offset = index.ReadUInt32();
        int count = index.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        int key_length = index.ReadUInt16();
        int flags = index.ReadUInt16();
        index.Position = 20;
        var key = index.ReadBytes (key_length);
        index.Position = index_offset + 0xC00;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            uint offset = index.ReadUInt32() + data_offset;
            uint size   = index.ReadUInt32();
            int name_len = index.ReadUInt8();
            var name = index.ReadCString (name_len);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = offset;
            entry.Size   = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var header = arc.File.View.ReadBytes (entry.Offset, 25);
    if (header[0] < 'B' || header[0] > 'E' || header[1] != '1')
        return arc.File.CreateStream (entry.Offset, entry.Size);
    if ('E' == header[0])
    {
        byte t = header[17];
        header[17] = header[23];
        header[23] = t;
        t = header[19];
        header[19] = header[24];
        header[24] = t;
    }
    int unpacked_size = header.ToInt32 (6);
    var data = new byte[unpacked_size];
    Stream input = arc.File.CreateStream (entry.Offset+header.Length, entry.Size-(uint)header.Length);
    input = new PrefixStream (header, input);
    input.Position = 10;
    using (input = new LzssStream (input))
        input.Read (data, 0, unpacked_size);
    if (data.AsciiEqual ("BPR01"))
        return new PackedStream<BprDecompressor> (Stream.Null, new BprDecompressor (data));
    else
        return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptIndex

```csharp
void DecryptIndex (byte[] index, int length, byte[] key) {
    for (int i = 0; i < length; ++i)
    {
        index[i] ^= key[i % key.Length];
    }
}
```

### GameRes.Formats.Eve.BprDecompressor

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

bool m_disposed = false ;
```

#### BprDecompressor

```csharp
public BprDecompressor (byte[] data) {
    m_input = new BinMemoryStream (data, 5, data.Length-5);
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    for (;;)
    {
        int ctl = m_input.ReadByte();
        if (-1 == ctl || 0xFF == ctl)
            yield break;
        int count = m_input.ReadInt32();
        if (1 == ctl)
        {
            byte v = m_input.ReadUInt8();
            while (count --> 0)
            {
                m_buffer[m_pos++] = v;
                if (0 == --m_length)
                    yield return m_pos;
            }
        }
        else
        {
            while (count > 0)
            {
                int chunk = Math.Min (count, m_length);
                chunk = m_input.Read (m_buffer, m_pos, chunk);
                if (0 == chunk)
                    yield break;
                m_pos += chunk;
                m_length -= chunk;
                count -= chunk;
                if (0 == m_length)
                    yield return m_pos;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Eve/ArcGM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
