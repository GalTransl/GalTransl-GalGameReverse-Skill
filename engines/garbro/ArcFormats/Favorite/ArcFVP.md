# Favorite / ArcFVP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/ACPXPK` / `GameRes.Formats.FVP.BinOpener` | `bin` | `41435058`, `4143505f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `if (!file.View.AsciiEqual (3, "XPK01") && !file.View.AsciiEqual (3, "_PK.1"))` |
| `BinOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `BinOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x20);` |
| `BinOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x20);` |
| `BinOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x24);` |
| `BinOpener.OpenEntry` | `if (!(entry.Size > 8 && arc.File.View.AsciiEqual (entry.Offset, "acp\0")))` |
| `BinOpener.OpenEntry` | `int unpacked_size = Binary.BigEndian (arc.File.View.ReadInt32 (entry.Offset+4));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FVP.BinOpener

继承/接口：`ArchiveFormat`。

#### BinOpener

```csharp
public BinOpener () {
    Extensions = new string[] { "bin" };
    Signatures = new uint[] { 0x58504341, 0x5F504341 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (3, "XPK01") && !file.View.AsciiEqual (3, "_PK.1"))
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    long index_offset = 0x0c;
    uint index_size = (uint)(0x28 * count);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x20);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x20);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x28;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!(entry.Size > 8 && arc.File.View.AsciiEqual (entry.Offset, "acp\0")))
        return base.OpenEntry (arc, entry);
    int unpacked_size = Binary.BigEndian (arc.File.View.ReadInt32 (entry.Offset+4));
    using (var input = arc.File.CreateStream (entry.Offset+8, entry.Size-8))
    using (var decoder = new LzwDecoder (input, unpacked_size))
    {
        decoder.Unpack();
        return new BinMemoryStream (decoder.Output, entry.Name);
    }
}
```

### GameRes.Formats.FVP.LzwDecoder

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
private MsbBitStream    m_input ;

private byte[]          m_output ;

public byte[] Output { get { return m_output; } }

bool _disposed = false ;
```

#### LzwDecoder

```csharp
public LzwDecoder (Stream input, int unpacked_size) {
    m_input = new MsbBitStream (input, true);
    m_output = new byte[unpacked_size];
}
```

#### Unpack

```csharp
public void Unpack () {
    int dst = 0;
    var lzw_dict = new int[0x8900];
    int token_width = 9;
    int dict_pos = 0;
    while (dst < m_output.Length)
    {
        int token = m_input.GetBits (token_width);
        if (-1 == token)
            throw new EndOfStreamException ("Invalid compressed stream");
        else if (0x100 == token)
            break;
        else if (0x101 == token)
        {
            ++token_width;
            if (token_width > 24)
                throw new InvalidFormatException ("Invalid compressed stream");
        }
        else if (0x102 == token)
        {
            token_width = 9;
            dict_pos = 0;
        }
        else
        {
            if (dict_pos >= lzw_dict.Length)
                throw new InvalidFormatException ("Invalid compressed stream");
            lzw_dict[dict_pos++] = dst;
            if (token < 0x100)
            {
                m_output[dst++] = (byte)token;
            }
            else
            {
                token -= 0x103;
                if (token >= dict_pos)
                    throw new InvalidFormatException ("Invalid compressed stream");
                int src = lzw_dict[token];
                int count = Math.Min (m_output.Length-dst, lzw_dict[token+1] - src + 1);
                if (count < 0)
                    throw new InvalidFormatException ("Invalid compressed stream");
                Binary.CopyOverlapped (m_output, src, dst, count);
                dst += count;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Favorite/ArcFVP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
