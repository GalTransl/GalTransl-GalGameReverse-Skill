# Cmvs / ArcCPZ1：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CPZ1` / `GameRes.Formats.Purple.Cpz1Opener` | `cpz` | `43505a31` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Cpz1Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Cpz1Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (8);` |
| `Cpz1Opener.TryOpen` | `var index = file.View.ReadBytes (0x10, index_size);` |
| `Cpz1Opener.TryOpen` | `int entry_size = LittleEndian.ToInt32 (index, index_offset);` |
| `Cpz1Opener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `Cpz1Opener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset+8) + base_offset;` |
| `Cpz1Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Cpz1Opener.OpenEntry` | `if (Binary.AsciiEqual (data, "PSS0"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Purple.Cpz1Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] DefaultKey = {
    0x92, 0xCD, 0x97, 0x90, 0x8C, 0xD7, 0x8C, 0xD5, 0x8B, 0x4B, 0x93, 0xFA, 0x9A, 0xD7, 0x8C, 0xBF,
    0x8C, 0xC9, 0x8C, 0xEB, 0x8D, 0x69, 0x8D, 0x8B, 0x8C, 0xD2, 0x8C, 0xD6, 0x8B, 0x6D, 0x8C, 0xE3,
    0x8C, 0xFB, 0x8C, 0xD0, 0x8C, 0xC8, 0x8C, 0xF0, 0x8B, 0xFE, 0x8C, 0xAA, 0x8C, 0xF4, 0x8B, 0x4B,
    0x9C, 0x58, 0x8C, 0xD3, 0x96, 0xC8, 0x8C, 0xCB, 0x8C, 0xCE, 0x8C, 0xF3, 0x8C, 0xD6, 0x8B, 0x52,
}
```

#### Cpz1Opener

```csharp
public Cpz1Opener () {
    Extensions = new string[] { "cpz" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    uint index_size = file.View.ReadUInt32 (8);
    var index = file.View.ReadBytes (0x10, index_size);
    DecryptData (index, DefaultKey);
    long base_offset = 0x10 + index_size;
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int entry_size = LittleEndian.ToInt32 (index, index_offset);
        if (entry_size <= 0 || entry_size > index.Length - index_offset)
            return null;
        var name = Binary.GetCString (index, index_offset+0x18);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset+8) + base_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, DefaultKey);
    if (Binary.AsciiEqual (data, "PSS0"))
        data = CpzOpener.UnpackLzss (data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, byte[] key) {
    if (key.Length < 0x40)
        throw new System.ArgumentException ("Invalid CPZ1 key");
    for (int i = 0; i < data.Length; i++)
    {
        data[i] = (byte)((data[i] ^ key[i & 0x3F]) - 0x6C);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Cmvs/ArcCPZ.cs](ArcCPZ.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cmvs/ArcCPZ1.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
