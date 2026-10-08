# ShiinaRio / ArcWARC1.0：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WAR/1.0` / `GameRes.Formats.Forest.War0Opener` | `war` | `57415243` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `War0Opener.TryOpen` | `if (!file.View.AsciiEqual (4, " 1.0"))` |
| `War0Opener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `War0Opener.TryOpen` | `var index = file.View.ReadBytes (index_offset, 0xC000);` |
| `War0Opener.TryOpen` | `entry.Offset = index.ToUInt32 (pos+0x10);` |
| `War0Opener.TryOpen` | `entry.Size   = index.ToUInt32 (pos+0x14);` |
| `War0Opener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "Ylz"))` |
| `War0Opener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `War0Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset+8, entry.Size-8);` |
| `Ylz16Reader.GetCtlBit` | `m_ctl = LittleEndian.ToUInt16 (m_input, m_src);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Forest.War0Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, " 1.0"))
        return null;
    uint index_offset = file.View.ReadUInt32 (8);
    if (index_offset >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (index_offset, 0xC000);
    int count = index.Length / 0x18;
    if (!IsSaneCount (count))
        return null;
    for (int i = 0; i < index.Length; i += 2)
    {
        index[i  ] ^= 0xFE;
        index[i+1] ^= 0xE5;
    }
    int pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, pos, 0x10);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = index.ToUInt32 (pos+0x10);
        entry.Size   = index.ToUInt32 (pos+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.UnpackedSize = entry.Size;
        dir.Add (entry);
        pos += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent)
        return base.OpenEntry (arc, entry);
    if (!pent.IsPacked)
    {
        if (!arc.File.View.AsciiEqual (entry.Offset, "Ylz"))
            return base.OpenEntry (arc, entry);
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);
    }
    var data = arc.File.View.ReadBytes (entry.Offset+8, entry.Size-8);
    var reader = new Ylz16Reader (data);
    data = reader.Unpack ((int)pent.UnpackedSize);
    return new BinMemoryStream (data, entry.Name);
}
```

### GameRes.Formats.Forest.Ylz16Reader

#### 状态与常量

```csharp
byte[]      m_input ;

int     m_ctl ;

int     m_bit_count ;

int     m_src ;
```

#### Ylz16Reader

```csharp
public Ylz16Reader (byte[] input) {
    m_input = input;
    DecryptInput();
}
```

#### DecryptInput

```csharp
void DecryptInput () {
    for (int i = 0; i < m_input.Length; ++i)
        m_input[i] ^= 0xE6;
}
```

#### GetCtlBit

```csharp
int GetCtlBit () {
    int bit = m_ctl & 1;
    m_ctl >>= 1;
    if (--m_bit_count <= 0)
    {
        m_ctl = LittleEndian.ToUInt16 (m_input, m_src);
        m_src += 2;
        m_bit_count = 16;
    }
    return bit;
}
```

#### Unpack

```csharp
public byte[] Unpack (int unpacked_size) {
    m_src = 0;
    m_bit_count = 0;
    GetCtlBit();
    var output = new byte[unpacked_size];
    int dst = 0;
    while (dst < unpacked_size)
    {
        if (GetCtlBit() != 0)
        {
            output[dst++] = m_input[m_src++];
        }
        else
        {
            int offset, count;
            if (GetCtlBit() == 0)
            {
                count  = GetCtlBit() << 1;
                count |= GetCtlBit();
                count += 2;
                offset = m_input[m_src++] | -0x100;
            }
            else
            {
                byte lo = m_input[m_src++];
                byte hi = m_input[m_src++];
                offset = lo | (hi & ~7) << 5 | -0x2000;
                count = hi & 7;
                if (0 == count)
                {
                    count = m_input[m_src++];
                    if (0 == count)
                        break;
                    count += 9;
                }
                else
                {
                    count += 2;
                }
            }
            Binary.CopyOverlapped (output, dst + offset, dst, count);
            dst += count;
        }
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ShiinaRio/ArcWARC1.0.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
