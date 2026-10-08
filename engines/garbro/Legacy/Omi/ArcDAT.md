# Omi / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/OMI` / `GameRes.Formats.Omi.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.DecompressRle` | `int size = input.ReadInt32();` |
| `DatOpener.DecompressRle` | `ushort rle_marker = input.ReadUInt16();` |
| `DatOpener.DecompressRle` | `if (output.ToUInt16 (dst) == rle_marker)` |
| `DatOpener.DecompressRle` | `int count = input.ReadUInt16() - 1;` |
| `DecryptedStream.ReadByte` | `public override int ReadByte () {` |
| `DecryptedStream.ReadByte` | `int b = BaseStream.ReadByte();` |
| `DecryptedStream.ReadLine` | `int b = ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Omi.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal const uint DefaultKey = 7654321u ;
```

#### DatOpener

```csharp
public DatOpener () {
    ContainedFormats = new[] { "BMP", "TGA", "WAV", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "scrdat"))
        return null;
    using (var input = file.CreateStream())
    using (var index = new DecryptedStream (input, DefaultKey, 0))
    {
        var line = index.ReadLine();
        int count = int.Parse (line);
        if (!IsSaneCount (count))
            return null;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadLine();
            line = index.ReadLine();
            uint size = uint.Parse (line);
            var entry = Create<PackedEntry> (name);
            entry.Size = size;
            entry.IsPacked = entry.Type == "image";
            dir.Add (entry);
        }
        long data_pos = index.Position;
        for (int i = 0; i < count; ++i)
        {
            dir[i].Offset = data_pos;
            if (!dir[i].CheckPlacement (file.MaxOffset))
                return null;
            data_pos += dir[i].Size;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    input = new DecryptedStream (input, DefaultKey, (uint)entry.Offset);
    if (!pent.IsPacked)
        return input;
    using (var packed = new BinaryStream (input, pent.Name))
    {
        var unpacked = DecompressRle (packed);
        if (pent.UnpackedSize == 0)
            pent.UnpackedSize = (uint)unpacked.Length;
        return new BinMemoryStream (unpacked, pent.Name);
    }
}
```

#### DecompressRle

```csharp
internal static byte[] DecompressRle (IBinaryStream input) {
    int size = input.ReadInt32();
    var output = new byte[size * 2];
    ushort rle_marker = input.ReadUInt16();
    int dst = 0;
    while (dst < output.Length)
    {
        input.Read (output, dst, 2);
        if (output.ToUInt16 (dst) == rle_marker)
        {
            input.Read (output, dst, 2);
            dst += 2;
            int count = input.ReadUInt16() - 1;
            if (count > 0)
            {
                count *= 2;
                Binary.CopyOverlapped (output, dst-2, dst, count);
                dst += count;
            }
        }
        else
        {
            dst += 2;
        }
    }
    return output;
}
```

### GameRes.Formats.Omi.DecryptedStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
private uint        m_key ;

static readonly Encoding Encoding = Encodings.cp932 ;

public override bool CanSeek { get => false; }

public override long Position {
    get => BaseStream.Position;
    set => throw new NotSupportedException ("Stream.Position property is not supported");
}

byte[] m_byte_buffer = new byte[1] ;

byte[] m_buffer ;
```

#### DecryptedStream

```csharp
public DecryptedStream (Stream stream, uint key, uint start_offset) : base (stream) {
    if (start_offset > 0)
    {
        do
        {
            key = 5 * key - 3;
        }
        while (--start_offset > 0);
    }
    m_key = key;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int read = BaseStream.Read (buffer, offset, count);
    Decrypt (buffer, offset, read);
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = BaseStream.ReadByte();
    if (-1 != b)
    {
        m_byte_buffer[0] = (byte)b;
        Decrypt (m_byte_buffer, 0, 1);
        b = m_byte_buffer[0];
    }
    return b;
}
```

#### Decrypt

```csharp
internal void Decrypt (byte[] data, int offset, int count) {
    for (int i = 0; i < count; ++i)
    {
        data[offset+i] = (byte)(Binary.RotByteR (data[offset+i], 1) - m_key);
        m_key = 5 * m_key - 3;
    }
}
```

#### ReadLine

```csharp
public string ReadLine () {
    if (null == m_buffer)
        m_buffer = new byte[32];
    int size = 0;
    for (;;)
    {
        int b = ReadByte();
        if (-1 == b || '\n' == b)
            break;
        if (m_buffer.Length == size)
        {
            Array.Resize (ref m_buffer, checked(size/2*3));
        }
        m_buffer[size++] = (byte)b;
    }
    return Encoding.GetString (m_buffer, 0, size);
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Omi/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
