# Inspire / ArcIDA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IDA` / `GameRes.Formats.Inspire.IdaOpener` | `ida`, `mha` | `58414600` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IdaOpener.TryOpen` | `int version = file.View.ReadInt32 (4);` |
| `IdaOpener.TryOpen` | `uint entry_length = index.ReadUInt32();` |
| `IdaOpener.TryOpen` | `uint offset = index.ReadUInt32();` |
| `IdaOpener.TryOpen` | `uint size   = index.ReadUInt32();` |
| `IdaOpener.TryOpen` | `uint flags  = index.ReadUInt32();` |
| `IdaOpener.TryOpen` | `uint key    = index.ReadUInt32();` |
| `IdaOpener.DeserializeString` | `return input.ReadCString (length);` |
| `IdaOpener.DeserializeString` | `var chars = input.ReadBytes (length);` |
| `IdaOpener.DeserializeLength` | `int length = input.ReadUInt8();` |
| `IdaOpener.DeserializeLength` | `length = input.ReadUInt16();` |
| `IdaOpener.DeserializeLength` | `length = input.ReadInt32();` |
| `RleDecompressor.Unpack` | `int output_size = m_input.ReadInt32();` |
| `RleDecompressor.Unpack` | `int ctl = m_input.ReadByte();` |
| `RleDecompressor.Unpack` | `count = m_input.ReadUInt8();` |
| `RleDecompressor.Unpack` | `count = m_input.ReadUInt16();` |
| `RleDecompressor.Unpack` | `count = m_input.ReadInt32();` |
| `RleDecompressor.Unpack` | `byte v = m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Inspire.IdaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint Flags ;

public uint Key ;
```

### GameRes.Formats.Inspire.IdaOpener

继承/接口：`ArchiveFormat`。

#### IdaOpener

```csharp
public IdaOpener () {
    Extensions = new[] { "ida", "mha" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (4);
    if (version > 0x011400)
        return null;
    using (var index = file.CreateStream())
    {
        var dir = new List<Entry>();
        bool has_packed = false;
        long index_pos = 8;
        do
        {
            index.Position = index_pos;
            uint entry_length = index.ReadUInt32();
            if (0 == entry_length)
                break;
            uint offset = index.ReadUInt32();
            uint size   = index.ReadUInt32();
            index.Seek (8, SeekOrigin.Current);
            uint flags  = index.ReadUInt32();
            uint key    = index.ReadUInt32();
            index.Seek (0x10, SeekOrigin.Current);
            var name = DeserializeString (index);
            index_pos += entry_length;

            var entry = FormatCatalog.Instance.Create<IdaEntry> (name);
            entry.Offset = offset;
            entry.Size   = entry.UnpackedSize = size;
            if (offset > file.MaxOffset || offset < index_pos)
                return null;
            entry.IsPacked = (flags & 0x14) != 0;
            entry.Flags = flags;
            entry.Key = key;
            has_packed = has_packed || entry.IsPacked;
            dir.Add (entry);
        }
        while (index_pos < dir[0].Offset);
        if (0 == dir.Count)
            return null;
        if (has_packed)
        {
            long last_offset = file.MaxOffset;
            for (int i = dir.Count - 1; i >= 0; --i)
            {
                dir[i].Size = (uint)(last_offset - dir[i].Offset);
                last_offset = dir[i].Offset;
            }
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var ient = entry as IdaEntry;
    if (null == ient || 0 == ient.Flags)
        return base.OpenEntry (arc, entry);
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (0 != (ient.Flags & 0xB))
        input = DecryptEntry (input, ient);
    if (0 != (ient.Flags & 4))
        input = new PackedStream<RleDecompressor> (input);
    if (0 != (ient.Flags & 0x10))
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

#### DecryptEntry

```csharp
Stream DecryptEntry (Stream input, IdaEntry entry) {
    int input_size = (int)entry.Size;
    var data = new byte[input_size];
    using (input)
        input_size = input.Read (data, 0, input_size);
    byte key = (byte)entry.Key;
    for (int i = 0; i < input_size; ++i)
    {
        byte v = data[i];
        if (0 != (entry.Flags & 8))
            v += key;
        if (0 != (entry.Flags & 2))
            v ^= key;
        if (0 != (entry.Flags & 1))
            v ^= 0xFF;
        data[i] = v;
        key = v;
    }
    return new BinMemoryStream (data, 0, input_size, entry.Name);
}
```

#### DeserializeString

```csharp
string DeserializeString (IBinaryStream input) {
    int length = DeserializeLength (input);
    if (0 == length)
        return "";
    if (length != -1)
        return input.ReadCString (length);
    length = DeserializeLength (input) * 2;
    var chars = input.ReadBytes (length);
    return Encoding.Unicode.GetString (chars, 0, length);
}
```

#### DeserializeLength

```csharp
int DeserializeLength (IBinaryStream input) {
    int length = input.ReadUInt8();
    if (length < 0xFF)
        return length;
    length = input.ReadUInt16();
    if (0xFFFE == length)
        length = -1;
    else if (0xFFFF == length)
        length = input.ReadInt32();
    return length;
}
```

### GameRes.Formats.Inspire.RleDecompressor

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

bool m_disposed = false ;
```

#### Initialize

```csharp
public override void Initialize (Stream input) {
    m_input = BinaryStream.FromStream (input, "");
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    int output_size = m_input.ReadInt32();
    int processed = 0;
    while (processed < output_size)
    {
        int ctl = m_input.ReadByte();
        if (-1 == ctl)
            yield break;
        int count = 0;
        if (0 == (ctl & 0x80))
        {
            count = ctl & 0x3F;
        }
        else if (0 == (ctl & 3))
        {
            count = m_input.ReadUInt8();
        }
        else if (1 == (ctl & 3))
        {
            count = m_input.ReadUInt16();
        }
        else if (3 == (ctl & 3))
        {
            count = m_input.ReadInt32();
        }
        processed += count;
        if (0 != (ctl & 0x40))
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
                int avail = Math.Min (count, m_length);
                int read = m_input.Read (m_buffer, m_pos, avail);
                if (0 == read)
                    yield break;
                count -= read;
                m_pos += read;
                m_length -= read;
                if (0 == m_length)
                    yield return m_pos;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Inspire/ArcIDA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
