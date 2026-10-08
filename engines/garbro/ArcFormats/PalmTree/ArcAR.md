# PalmTree / ArcAR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/AR` / `GameRes.Formats.PalmTree.ArcOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArPkStream.BuildDirectory` | `if (read < 4 \|\| !pk_buffer.AsciiEqual ("AR"))` |
| `ArPkStream.BuildDirectory` | `uint block_type = pk_buffer.ToUInt16 (2);` |
| `ArPkStream.BuildDirectory` | `uint name_length  = pk_buffer.ToUInt16 (0x1C);` |
| `ArPkStream.BuildDirectory` | `uint extra_length = pk_buffer.ToUInt16 (0x1E);` |
| `ArPkStream.BuildDirectory` | `uint cmt_length   = pk_buffer.ToUInt16 (0x20);` |
| `ArPkStream.BuildDirectory` | `uint packed_size  = pk_buffer.ToUInt32 (0x12);` |
| `ArPkStream.BuildDirectory` | `uint name_length  = pk_buffer.ToUInt16 (0x1A);` |
| `ArPkStream.BuildDirectory` | `uint extra_length = pk_buffer.ToUInt16 (0x1C);` |
| `ArPkStream.BuildDirectory` | `uint cmt_length = pk_buffer.ToUInt16 (0x14);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.PalmTree.ArcOpener

继承/接口：`ZipOpener`。

#### 状态与常量

```csharp
static readonly byte[] ArDirSignature = { (byte)'A', (byte)'R', 5, 6 }
```

#### ArcOpener

```csharp
public ArcOpener () {
    Settings = null;
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (-1 == SearchForSignature (file, ArDirSignature))
        return null;
    var input = new ArPkStream (file.CreateStream());
    try
    {
        return OpenZipArchive (file, input);
    }
    catch
    {
        input.Dispose();
        throw;
    }
}
```

### GameRes.Formats.PalmTree.ArPkStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
List<long>  m_ar_blocks ;

long        m_last_scan_pos ;

bool        m_scan_failed ;

byte[] pk_buffer = new byte[0x22] ;
```

#### ArPkStream

```csharp
public ArPkStream (Stream input) : base (input) {
    m_ar_blocks = new List<long>();
    m_last_scan_pos = 0;
    m_scan_failed = false;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    long pos = this.Position;
    if (pos + count > m_last_scan_pos && !m_scan_failed)
    {
        BuildDirectory (pos + count);
        this.Position = pos;
    }
    count = BaseStream.Read (buffer, offset, count);
    if (0 == count)
        return count;
    long buf_pos = pos;
    long buf_end = buf_pos + count;
    int index = m_ar_blocks.BinarySearch (buf_pos-1);
    if (index < 0)
        index = ~index;
    for (; index < m_ar_blocks.Count; ++index)
    {
        var ar_pos = m_ar_blocks[index];
        if (buf_end <= ar_pos)
            break;
        if (buf_pos >= ar_pos+2)
            continue;
        int signature_pos = (int)(ar_pos - pos);
        if (signature_pos >= 0)
            buffer[offset+signature_pos] = (byte)'P';
        ++signature_pos;
        if (signature_pos >= 0 && signature_pos < count)
            buffer[offset+signature_pos] = (byte)'K';
        buf_pos = ar_pos + 2;
    }
    return count;
}
```

#### BuildDirectory

```csharp
void BuildDirectory (long last_pos) {
    long pos = m_last_scan_pos;
    while (pos < last_pos)
    {
        this.Position = pos;
        int read = BaseStream.Read (pk_buffer, 0, 0x22);
        if (read < 4 || !pk_buffer.AsciiEqual ("AR"))
        {
            m_scan_failed = true;
            break;
        }
        m_ar_blocks.Add (pos);
        uint block_type = pk_buffer.ToUInt16 (2);
        if (0x0201 == block_type && read >= 0x22)
        {
            uint name_length  = pk_buffer.ToUInt16 (0x1C);
            uint extra_length = pk_buffer.ToUInt16 (0x1E);
            uint cmt_length   = pk_buffer.ToUInt16 (0x20);
            pos += 0x2EL + name_length + extra_length + cmt_length;
        }
        else if (0x0403 == block_type && read >= 0x1E)
        {
            uint packed_size  = pk_buffer.ToUInt32 (0x12);
            uint name_length  = pk_buffer.ToUInt16 (0x1A);
            uint extra_length = pk_buffer.ToUInt16 (0x1C);
            pos += 0x1EL + name_length + extra_length + packed_size;
        }
        else if (0x0605 == block_type && read >= 0x16)
        {
            uint cmt_length = pk_buffer.ToUInt16 (0x14);
            pos += 0x16L + cmt_length;
        }
        else
        {
            pos += 4;
            m_scan_failed = true;
        }
    }
    m_last_scan_pos = pos;
}
```

## 配套算法与外部条件

- [ArcFormats/PkWare/ArcZIP.cs](../PkWare/ArcZIP.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/PalmTree/ArcAR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
