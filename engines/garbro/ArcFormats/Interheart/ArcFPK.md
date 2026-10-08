# Interheart / ArcFPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FPK` / `GameRes.Formats.CandySoft.FpkOpener` | `fpk` | `01000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `FpkOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `FpkOpener.ReadIndex` | `string name = file.View.ReadString (index_offset+8, (uint)name_size);` |
| `FpkOpener.ReadIndex` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `FpkOpener.ReadIndex` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |
| `FpkOpener.ReadEncryptedIndex` | `uint index_offset = file.View.ReadUInt32 (file.MaxOffset-4);` |
| `FpkOpener.ReadEncryptedIndex` | `var key = file.View.ReadBytes (file.MaxOffset-8, 4);` |
| `FpkOpener.ReadEncryptedIndex` | `var index = file.View.ReadBytes (index_offset, (uint)index_size);` |
| `FpkOpener.ReadEncryptedIndex` | `entry.Offset = LittleEndian.ToUInt32 (index, index_pos);` |
| `FpkOpener.ReadEncryptedIndex` | `entry.Size   = LittleEndian.ToUInt32 (index, index_pos+4);` |
| `Zlc2Reader.Zlc2Reader` | `uint output_length = m_input.ReadUInt32();` |
| `Zlc2Reader.Unpack` | `int ctl = m_input.ReadUInt8();` |
| `Zlc2Reader.Unpack` | `int offset = m_input.ReadUInt8();` |
| `Zlc2Reader.Unpack` | `int count  = m_input.ReadUInt8();` |
| `Zlc2Reader.Unpack` | `m_output[dst++] = m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CandySoft.FpkOpener

继承/接口：`ArchiveFormat`。

#### FpkOpener

```csharp
public FpkOpener () {
    Signatures = new uint[] { 0, 1 };
    ContainedFormats = new[] { "BMP", "KG", "OGG", "SCR", "TXT", "DAT/GENERIC" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset < 0x10)
        return null;
    int count = file.View.ReadInt32 (0);
    List<Entry> dir = null;
    if (count < 0)
    {
        count &= 0x7FFFFFFF;
        if (!IsSaneCount (count))
            return null;
        dir = ReadEncryptedIndex (file, count);
    }
    else
    {
        if (!IsSaneCount (count))
            return null;
        try
        {
            dir = ReadIndex (file, count, 0x10);
        }
        catch {  }
        if (null == dir)
            dir = ReadIndex (file, count, 0x18);
    }
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### ReadIndex

```csharp
private List<Entry> ReadIndex (ArcView file, int count, int name_size) {
    long index_offset = 4;
    uint index_size = (uint)((8 + name_size) * count);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    uint data_offset = 4 + index_size;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset+8, (uint)name_size);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset);
        entry.Size   = file.View.ReadUInt32 (index_offset+4);
        if (entry.Offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8 + name_size;
    }
    return dir;
}
```

#### ReadEncryptedIndex

```csharp
private List<Entry> ReadEncryptedIndex (ArcView file, int count) {
    uint index_offset = file.View.ReadUInt32 (file.MaxOffset-4);
    if (index_offset < 4 || index_offset >= file.MaxOffset-8)
        return null;
    var key = file.View.ReadBytes (file.MaxOffset-8, 4);
    int name_size = 0x18;
    int index_size = count * (12 + name_size);
    var index = file.View.ReadBytes (index_offset, (uint)index_size);
    if (index.Length != index_size)
        return null;
    for (int i = 0; i < index.Length; ++i)
        index[i] ^= key[i & 3];

    int index_pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = Binary.GetCString (index, index_pos+8, name_size);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = LittleEndian.ToUInt32 (index, index_pos);
        entry.Size   = LittleEndian.ToUInt32 (index, index_pos+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += 12 + name_size;
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    IBinaryStream input = arc.File.CreateStream (entry.Offset, entry.Size);
    while (input.Length > 8 && input.Signature == 0x32434C5A)
    {
        IBinaryStream unpacked;
        using (input)
        using (var reader = new Zlc2Reader (input, (int)input.Length))
        {
            reader.Unpack();
            unpacked = new BinMemoryStream (reader.Data, entry.Name);
        }
        input = unpacked;
    }
    return input.AsStream;
}
```

### GameRes.Formats.CandySoft.Zlc2Reader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

byte[]          m_output ;

int             m_size ;

public byte[] Data { get { return m_output; } }
```

#### Zlc2Reader

```csharp
public Zlc2Reader (IBinaryStream input, int input_length) {
    input.Position = 4;
    m_input = input;
    uint output_length = m_input.ReadUInt32();
    m_output = new byte[output_length];
    m_size = input_length - 8;
}
```

#### Unpack

```csharp
public void Unpack () {
    int remaining = m_size;
    int dst = 0;
    while (remaining > 0 && dst < m_output.Length)
    {
        int ctl = m_input.ReadUInt8();
        remaining--;
        for (int mask = 0x80; mask != 0 && remaining > 0 && dst < m_output.Length; mask >>= 1)
        {
            if (0 != (ctl & mask))
            {
                if (remaining < 2)
                    return;

                int offset = m_input.ReadUInt8();
                int count  = m_input.ReadUInt8();
                remaining -= 2;
                offset |= (count & 0xF0) << 4;
                count   = (count & 0x0F) + 3;

                if (0 == offset)
                    offset = 4096;
                if (dst + count > m_output.Length)
                    count = m_output.Length - dst;

                Binary.CopyOverlapped (m_output, dst-offset, dst, count);
                dst += count;
            }
            else
            {
                m_output[dst++] = m_input.ReadUInt8();
                remaining--;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Interheart/ArcFPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
