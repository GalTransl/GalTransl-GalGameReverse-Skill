# CatSystem / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/CSPACK` / `GameRes.Formats.CatSystem.DatOpener` | `dat` | `43735061` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "CsPack"))` |
| `DatOpener.TryOpen` | `int version = file.View.ReadByte (6) - '0';` |
| `DatOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (8);` |
| `DatOpener.TryOpen` | `next_offset = entry_buffer.ToUInt32 (0)` |
| `DatOpener.TryOpen` | `^ entry_buffer.ToUInt32 (4)` |
| `DatOpener.TryOpen` | `^ entry_buffer.ToUInt32 (entry_size - 4);` |
| `CsNameDecryptor.Decrypt` | `uint num = buffer.ToUInt32 (pos);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CatSystem.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "CsPack"))
        return null;
    int version = file.View.ReadByte (6) - '0';
    if (version < 1 || version > 2)
        return null;
    uint data_offset = file.View.ReadUInt32 (8);
    int entry_size = 12 * version;
    int count = (int)(data_offset - 12) / entry_size;
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    uint next_offset = data_offset;
    var name_decoder = new CsNameDecryptor (version == 1 ? 0xC : 0x1E,
                                            version == 1 ? 0x8 : 0x10);
    var entry_buffer = new byte[entry_size];
    int index_pos = 12;
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_pos, entry_buffer, 0, (uint)entry_size);
        var name = name_decoder.Decrypt (entry_buffer);
        var entry = Create<Entry> (name);
        entry.Offset = next_offset;
        next_offset = entry_buffer.ToUInt32 (0)
                    ^ entry_buffer.ToUInt32 (4)
                    ^ entry_buffer.ToUInt32 (entry_size - 4);
        entry.Size = (uint)(next_offset - entry.Offset);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.CatSystem.CsNameDecryptor

#### 状态与常量

```csharp
int             m_name_length ;

int             m_extension_pos ;

byte[]          m_buffer ;

StringBuilder   m_name ;

const string Alphabet = "_0123456789abcdefghijklmnopqrstuvwxyz_" ;
```

#### CsNameDecryptor

```csharp
public CsNameDecryptor (int name_length, int extension_pos) {
    m_name_length = name_length;
    m_extension_pos = extension_pos;
    m_buffer = new byte[m_name_length];
    m_name = new StringBuilder (m_name_length);
}
```

#### Decrypt

```csharp
public string Decrypt (byte[] buffer) {
    int length = m_name_length / 6 * 4;
    int dst = 0;
    for (int pos = 0; pos < length; pos += 4)
    {
        uint num = buffer.ToUInt32 (pos);
        for (int i = 5; i >= 0; --i)
        {
            uint val = num % 40;
            num /= 40;
            m_buffer[dst+i] = (byte)val;
        }
        dst += 6;
    }
    m_name.Clear();
    AppendChars (0, m_name_length - 4);
    if (m_buffer[m_extension_pos] != 0)
    {
        m_name.Append ('.');
        AppendChars (m_extension_pos, 3);
    }
    return m_name.ToString();
}
```

#### AppendChars

```csharp
void AppendChars (int pos, int length) {
    for (int i = 0; i < length; ++i)
    {
        if (0 == m_buffer[pos+i])
            break;
        m_name.Append (Alphabet[m_buffer[pos+i]]);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/CatSystem/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
