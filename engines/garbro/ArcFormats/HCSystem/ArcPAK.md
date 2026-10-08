# HCSystem / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/HCSYSTEM` / `GameRes.Formats.HCSystem.PakOpener` | `pak` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PakOpener.TryOpen` | `bool is_encrypted = file.View.ReadByte (8) == 1;` |
| `PakOpener.TryOpen` | `var index = file.View.ReadBytes (0xC, entry_size * (uint)count);` |
| `PakOpener.TryOpen` | `entry.UnpackedSize = index.ToUInt32 (index_offset);` |
| `PakOpener.TryOpen` | `entry.Size         = index.ToUInt32 (index_offset+4);` |
| `PakOpener.TryOpen` | `entry.Offset       = index.ToUInt32 (index_offset+8);` |
| `PakOpener.CheckFirstOffset` | `uint first_offset = file.View.ReadUInt32 (0xC + entry_size - 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.HCSystem.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    bool is_encrypted = file.View.ReadByte (8) == 1;
    bool is_unicode = false;
    uint entry_size = 0x2C;
    if (!CheckFirstOffset (file, count, entry_size, is_encrypted))
    {
        entry_size = 0x4C;
        if (!CheckFirstOffset (file, count, entry_size, is_encrypted))
            return null;
        is_unicode = true;
    }
    var index = file.View.ReadBytes (0xC, entry_size * (uint)count);
    if (is_encrypted)
        DecryptIndex (index);

    int name_size = is_unicode ? 0x40 : 0x20;
    Func<int, string> read_name;
    if (is_unicode)
    {
        read_name = pos => {
            int len = 0;
            for (; len < name_size; len += 2)
            {
                if (index[pos+len] == 0 && index[pos+len+1] == 0)
                    break;
            }
            return Encoding.Unicode.GetString (index, pos, len);
        };
    }
    else
        read_name = pos => Binary.GetCString (index, pos, name_size);

    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = read_name (index_offset);
        index_offset += name_size;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.UnpackedSize = index.ToUInt32 (index_offset);
        entry.Size         = index.ToUInt32 (index_offset+4);
        entry.Offset       = index.ToUInt32 (index_offset+8);
        entry.IsPacked = entry.Size != 0;
        if (!entry.IsPacked)
            entry.Size = entry.UnpackedSize;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0xC;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new LzssStream (input);
}
```

#### CheckFirstOffset

```csharp
private bool CheckFirstOffset (ArcView file, int count, uint entry_size, bool is_encrypted) {
    uint data_offset = 0xC + entry_size * (uint)count;
    uint first_offset = file.View.ReadUInt32 (0xC + entry_size - 4);
    if (is_encrypted)
        first_offset = (first_offset >> 4) & 0x0F0F0F0F | (first_offset << 4) & 0xF0F0F0F0;
    return first_offset == data_offset;
}
```

#### DecryptIndex

```csharp
void DecryptIndex (byte[] data) {
    for (int i = 0; i < data.Length; ++i)
        data[i] = Binary.RotByteL (data[i], 4);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/HCSystem/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
