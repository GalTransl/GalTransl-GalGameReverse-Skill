# Cmvs / ArcCPZ3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CPZ3` / `GameRes.Formats.Purple.Cpz3Opener` | `cpz` | `43505a33` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Cpz3Opener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (4) ^ 0x5E9C4F37);` |
| `Cpz3Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (8) ^ 0xF32AED17u;` |
| `Cpz3Opener.TryOpen` | `uint key = file.View.ReadUInt32 (0x10) ^ 0xA62978E4u;` |
| `Cpz3Opener.TryOpen` | `var index = file.View.ReadBytes (0x14, index_size);` |
| `Cpz3Opener.TryOpen` | `int entry_size = LittleEndian.ToInt32 (index, index_offset);` |
| `Cpz3Opener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `Cpz3Opener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset+8) + base_offset;` |
| `Cpz3Opener.TryOpen` | `entry.Key = LittleEndian.ToUInt32 (index, index_offset+0x14) ^ 0xC7F5DA63u;` |
| `Cpz3Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Cpz3Opener.OpenEntry` | `if (data.Length > 0x30 && Binary.AsciiEqual (data, 0, "PS2A"))` |
| `Cpz3Opener.OpenEntry` | `else if (data.Length > 0x40 && Binary.AsciiEqual (data, 0, "PB3B"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Purple.Cpz3Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly uint[] EncryptionTable = {
    0x4D0D4A5E, 0xB3ABF3E1, 0x3C37336D, 0x86C3F5F3, 0x7D4F9B89, 0x58D7DE11, 0x6367778D, 0xA5F34629,
    0x067FA4B5, 0xED0AE742, 0xB19450CC, 0xE7204A5A, 0xD9AF04F5, 0x5D3B687F, 0xC1C7A6FD, 0xFC502289
}
```

#### Cpz3Opener

```csharp
public Cpz3Opener () {
    Extensions = new string[] { "cpz" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = (int)(file.View.ReadUInt32 (4) ^ 0x5E9C4F37);
    if (!IsSaneCount (count))
        return null;
    uint index_size = file.View.ReadUInt32 (8) ^ 0xF32AED17u;
    uint key = file.View.ReadUInt32 (0x10) ^ 0xA62978E4u;
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
        entry.Key = LittleEndian.ToUInt32 (index, index_offset+0x14) ^ 0xC7F5DA63u;
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
    if (data.Length > 0x30 && Binary.AsciiEqual (data, 0, "PS2A"))
        data = CpzOpener.UnpackPs2 (data);
    else if (data.Length > 0x40 && Binary.AsciiEqual (data, 0, "PB3B"))
        CpzOpener.DecryptPb3 (data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, uint key) {
    int shift = 0;
    int k = (int)key;
    for (int i = 0; i < 8; ++i)
    {
        shift ^= k & 0xF;
        k >>= 4;
    }
    shift ^= 0xD;
    shift += 8;
    unsafe
    {
        fixed (byte* data_fixed = data)
        {
            uint* data32 = (uint*)data_fixed;
            int table_ptr = 3;
            for (int count = data.Length >> 2; count > 0; --count)
            {
                uint t = (*data32 ^ (EncryptionTable[table_ptr++ & 0xF] + key)) + 0x6E58A5C2u;
                *data32++ = Binary.RotL (t, shift);
            }
            byte* data8 = (byte*)data32;
            for (int count = data.Length & 3; count > 0; --count)
            {
                *data8 = (byte)((*data8 ^ ((EncryptionTable[table_ptr++ & 0xF] + key) >> (count * 4))) + 0x52);
                ++data8;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Cmvs/ArcCPZ.cs](ArcCPZ.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cmvs/ArcCPZ3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
