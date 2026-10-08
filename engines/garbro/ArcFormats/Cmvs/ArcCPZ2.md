# Cmvs / ArcCPZ2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CPZ2` / `GameRes.Formats.Purple.Cpz2Opener` | `cpz` | `43505a32` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Cpz2Opener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (4) ^ 0xE47C59F3);` |
| `Cpz2Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (8) ^ 0x3F71DE2Au;` |
| `Cpz2Opener.TryOpen` | `uint key = file.View.ReadUInt32 (0x10) ^ 0x40DE832Cu;` |
| `Cpz2Opener.TryOpen` | `var index = file.View.ReadBytes (0x14, index_size);` |
| `Cpz2Opener.TryOpen` | `int entry_size = LittleEndian.ToInt32 (index, index_offset);` |
| `Cpz2Opener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `Cpz2Opener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset+8) + base_offset;` |
| `Cpz2Opener.TryOpen` | `entry.Key = LittleEndian.ToUInt32 (index, index_offset+0x14) ^ 0x796C3AFDu;` |
| `Cpz2Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Cpz2Opener.OpenEntry` | `if (Binary.AsciiEqual (data, "PSS0"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Purple.Cpz2Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly uint[] EncryptionTable = {
    0x3A68CDBF, 0xD3C3A711, 0x8414876E, 0x657BEFDB, 0xCDD7C125, 0x09328580, 0x288FFEDD, 0x99EBF13A,
    0x5A471F95, 0x1EA3F4F1, 0xF4FF524E, 0xD358E8A9, 0xC5B71015, 0xA913046F, 0x2D6FD2BD, 0x68C8BE19
}
```

#### Cpz2Opener

```csharp
public Cpz2Opener () {
    Extensions = new string[] { "cpz" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = (int)(file.View.ReadUInt32 (4) ^ 0xE47C59F3);
    if (!IsSaneCount (count))
        return null;
    uint index_size = file.View.ReadUInt32 (8) ^ 0x3F71DE2Au;
    uint key = file.View.ReadUInt32 (0x10) ^ 0x40DE832Cu;
    var index = file.View.ReadBytes (0x14, index_size);
    DecryptData (index, key);
    long base_offset = 0x14 + index_size;
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int entry_size = LittleEndian.ToInt32 (index, index_offset);
        if (entry_size <= 0 || entry_size > index.Length - index_offset)
            return null;
        var name = Binary.GetCString (index, index_offset+0x18);
        var entry = FormatCatalog.Instance.Create<CpzEntry> (name);
        entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset+8) + base_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Key = LittleEndian.ToUInt32 (index, index_offset+0x14) ^ 0x796C3AFDu;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var cent = entry as CpzEntry;
    if (null == cent)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, cent.Key);
    if (Binary.AsciiEqual (data, "PSS0"))
        data = CpzOpener.UnpackLzss (data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, uint key) {
    int shift = 5;
    int k = (int)key;
    for (int i = 0; i < 8; ++i)
    {
        shift ^= k & 0xF;
        k >>= 4;
    }
    shift += 8;
    unsafe
    {
        fixed (byte* data_fixed = data)
        {
            uint* data32 = (uint*)data_fixed;
            int table_ptr = 0;
            for (int count = data.Length >> 2; count > 0; --count)
            {
                uint t = (*data32 ^ (EncryptionTable[table_ptr++ & 0xF] + key)) - 0x15C3E7u;
                *data32++ = Binary.RotR (t, shift);
            }
            byte* data8 = (byte*)data32;
            shift = 0;
            for (int count = data.Length & 3; count > 0; --count)
            {
                *data8 = (byte)((*data8 ^ ((EncryptionTable[table_ptr++ & 0xF] + key) >> shift)) + 0x37);
                shift += 4;
                ++data8;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Cmvs/ArcCPZ.cs](ArcCPZ.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cmvs/ArcCPZ2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
