# StudioJikkenshitsu / ArcUMPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/UMPK` / `GameRes.Formats.Umut.PakOpener` | `pac` | `554d504b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "0001"))` |
| `PakOpener.TryOpen` | `uint name_length = file.View.ReadByte (0x18);` |
| `PakOpener.TryOpen` | `if (file.View.ReadUInt32 (base_offset) != 0)` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (base_offset+8);` |
| `PakOpener.TryOpen` | `uint rec_length = file.View.ReadUInt32 (index_offset);` |
| `PakOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index_offset+4);` |
| `PakOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset+8);` |
| `PakOpener.TryOpen` | `uint id     = file.View.ReadUInt32 (index_offset+12);` |
| `PakOpener.TryOpen` | `name_length = file.View.ReadUInt32 (index_offset+16);` |
| `PakOpener.TryOpen` | `var name = file.View.ReadString (index_offset+20, name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Umut.UmEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte Key ;
```

### GameRes.Formats.Umut.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "0001"))
        return null;
    uint name_length = file.View.ReadByte (0x18);
    uint base_offset = 0x1A + name_length;
    if (file.View.ReadUInt32 (base_offset) != 0)
        return null;
    int count = file.View.ReadInt32 (base_offset+8);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = base_offset + 12;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint rec_length = file.View.ReadUInt32 (index_offset);
        uint size   = file.View.ReadUInt32 (index_offset+4);
        uint offset = file.View.ReadUInt32 (index_offset+8);
        uint id     = file.View.ReadUInt32 (index_offset+12);
        name_length = file.View.ReadUInt32 (index_offset+16);
        var name = file.View.ReadString (index_offset+20, name_length);
        var entry = Create<UmEntry> (name);
        entry.Offset = 8L + base_offset + offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Key = GetEntryKey (name, size, id);
        dir.Add (entry);
        index_offset += rec_length + 4;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var ument = entry as UmEntry;
    if (null == ument)
        return input;
    return new XoredStream (input, ument.Key);
}
```

#### GetEntryKey

```csharp
internal static byte GetEntryKey (string name, uint size, uint id) {
    uint name_sum = 0;
    for (int i = 0; i < name.Length; ++i)
    {
        name_sum += (uint)name[i];
    }
    uint key = size + id;
    key += name_sum + (key >> 8) + (key >> 16) + (key >> 24);
    key &= 0xFF;
    if (0 == key)
        key = 0x37;
    return (byte)key;
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/StudioJikkenshitsu/ArcUMPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
