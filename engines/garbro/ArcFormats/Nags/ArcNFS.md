# Nags / ArcNFS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NFS` / `GameRes.Formats.Nags.NfsOpener` | `nfs` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NfsOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `NfsOpener.TryOpen` | `int first_offset = file.View.ReadInt32 (0x1C);` |
| `NfsOpener.TryOpen` | `var index = file.View.ReadBytes (4, index_size);` |
| `NfsOpener.TryOpen` | `entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_offset+0x18);` |
| `NfsOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset+0x1C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nags.NfsOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    uint index_size = (uint)count * 0x20;
    if (index_size > file.View.Reserve (4, (uint)index_size))
        return null;
    int first_offset = file.View.ReadInt32 (0x1C);
    byte key = (byte)count;
    first_offset ^= key | key << 8 | key << 16 | key << 24;
    if (first_offset != 0)
        return null;

    var index = file.View.ReadBytes (4, index_size);
    for (int i = 0; i < index.Length; ++i)
        index[i] ^= key;

    long base_offset = 4 + index_size;
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, index_offset, 0x18);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_offset+0x18);
        entry.Size   = LittleEndian.ToUInt32 (index, index_offset+0x1C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (!entry.Name.HasExtension (".scb"))
        return input;
    return new InputCryptoStream (input, new NotTransform());
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Nags/ArcNFS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
