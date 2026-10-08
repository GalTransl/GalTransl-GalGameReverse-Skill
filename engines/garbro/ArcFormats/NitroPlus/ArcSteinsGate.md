# NitroPlus / ArcSteinsGate：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NPA-SG` / `GameRes.Formats.NitroPlus.NpaSteinsGateOpener` | `npa` | 无固定签名或来源表达式未解析 | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NpaSteinsGateOpener.TryOpen` | `int index_size = file.View.ReadInt32 (0);` |
| `NpaSteinsGateOpener.TryOpen` | `int entry_count = header.ReadInt32();` |
| `NpaSteinsGateOpener.TryOpen` | `int name_length = header.ReadInt32();` |
| `NpaSteinsGateOpener.TryOpen` | `byte[] name_raw = header.ReadBytes (name_length);` |
| `NpaSteinsGateOpener.TryOpen` | `entry.Size = header.ReadUInt32();` |
| `NpaSteinsGateOpener.TryOpen` | `entry.Offset = header.ReadInt64();` |
| `SteinsGateEncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `SteinsGateEncryptedStream.ReadByte` | `int b = m_stream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NitroPlus.NpaSteinsGateOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal static readonly byte[] KeyString = {
    'B'^0xff, 'U'^0xff, 'C'^0xff, 'K'^0xff,
    'T'^0xff, 'I'^0xff, 'C'^0xff, 'K'^0xff
}
```

#### NpaSteinsGateOpener

```csharp
public NpaSteinsGateOpener () {
    Extensions = new string[] { "npa" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int index_size = file.View.ReadInt32 (0);
    if (index_size < 0x14 || index_size >= file.MaxOffset || index_size > 0xffffff)
        return null;

    var stream = new SteinsGateEncryptedStream (file, 4, (uint)index_size);
    using (var header = new BinaryReader (stream))
    {
        int entry_count = header.ReadInt32();
        if (!IsSaneCount (entry_count))
            return null;
        index_size -= 4;
        int average_entry_size = index_size / entry_count;
        if (average_entry_size < 0x11)
            return null;

        var dir = new List<Entry> (entry_count);
        for (int i = 0; i < entry_count; ++i)
        {
            int name_length = header.ReadInt32();
            if (name_length+0x10 > index_size)
                return null;
            byte[] name_raw = header.ReadBytes (name_length);
            Encoding enc = GuessEncoding (name_raw);
            string filename = enc.GetString (name_raw);

            var entry = FormatCatalog.Instance.Create<Entry> (filename);
            entry.Size = header.ReadUInt32();
            entry.Offset = header.ReadInt64();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);

            index_size -= name_length+0x10;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    return new SteinsGateEncryptedStream (arc.File, entry.Offset, entry.Size);
}
```

#### Encrypt

```csharp
internal void Encrypt (byte[] buffer, int offset, int count) {
    for (int i = 0; i < count; ++i)
    {
        buffer[offset+i] ^= KeyString[i & 7];
    }
}
```

#### GuessEncoding

```csharp
Encoding GuessEncoding (byte[] text) {
    bool has_zero = false;
    bool has_non_ascii = false;
    foreach (var symbol in text)
    {
        if (0 == symbol)
        {
            has_zero = true;
            break;
        }
        else if (symbol > 0x7f)
        {
            has_non_ascii = true;
        }
    }
    if (has_zero)
        return Encoding.Unicode;
    else if (has_non_ascii)
        return Encodings.cp932;
    else
        return Encoding.ASCII;
}
```

#### GetEncoding

```csharp
Encoding GetEncoding (string name) {
    if ("shift-jis" == name)
        return Encodings.cp932;
    if ("utf-16" == name)
        return Encoding.Unicode;
    return Encoding.Default;
}
```

### GameRes.Formats.NitroPlus.SteinsGateEncryptedStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
private Stream      m_stream ;

private long        m_base_pos ;

private bool        m_should_dispose ;

public Stream BaseStream { get { return m_stream; } }

public override bool  CanRead { get { return m_stream.CanRead; } }

public override bool  CanSeek { get { return m_stream.CanSeek; } }

public override long   Length { get { return m_stream.Length - m_base_pos; } }

public override long Position {
    get { return m_stream.Position - m_base_pos; }
    set { m_stream.Position = m_base_pos + value; }
}

bool disposed = false ;
```

#### SteinsGateEncryptedStream

```csharp
public SteinsGateEncryptedStream (ArcView file, long offset, uint size) {
    m_stream = file.CreateStream (offset, size);
    m_should_dispose = true;
    m_base_pos = 0;
}
```

#### SteinsGateEncryptedStream

```csharp
public SteinsGateEncryptedStream (Stream output) {
    m_stream = output;
    m_should_dispose = false;
    m_base_pos = m_stream.Position;
}
```

#### Flush

```csharp
public override void Flush() {
    m_stream.Flush();
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    if (SeekOrigin.Begin == origin)
        offset += m_base_pos;
    offset = m_stream.Seek (offset, origin);
    return offset - m_base_pos;
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new System.NotSupportedException ("SteinsGateEncryptedStream.SetLength method is not supported");
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int position = (int)Position & 7;
    int read = m_stream.Read (buffer, offset, count);
    if (read > 0)
    {
        for (int i = 0; i < read; ++i)
        {
            buffer[offset+i] ^= NpaSteinsGateOpener.KeyString[(position+i)&7];
        }
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int position = (int)Position & 7;
    int b = m_stream.ReadByte();
    if (-1 != b)
    {
        b ^= NpaSteinsGateOpener.KeyString[position];
    }
    return b;
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    int position = (int)Position & 7;
    m_stream.WriteByte ((byte)(value ^ NpaSteinsGateOpener.KeyString[position]));
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NitroPlus/ArcSteinsGate.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
