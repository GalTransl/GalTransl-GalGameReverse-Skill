# Banana / ArcPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PK/BANANA` / `GameRes.Formats.Banana.PkOpener` | `pk`, `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `PkOpener.TryOpen` | `byte name_length = file.View.ReadByte (index_offset++);` |
| `PkOpener.TryOpen` | `entry.Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset));` |
| `PkOpener.TryOpen` | `entry.Size   = Binary.BigEndian (file.View.ReadUInt32 (index_offset+4));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Banana.PkOpener

继承/接口：`ArchiveFormat`。

#### PkOpener

```csharp
public PkOpener () {
    Extensions = new string[] { "pk", "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count) || count * 10 >= file.MaxOffset)
        return null;

    uint index_offset = 4;
    byte[] name_buffer = new byte[0x100];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        byte name_length = file.View.ReadByte (index_offset++);
        if (0 == name_length)
            return null;
        if (name_length != file.View.Read (index_offset, name_buffer, 0, name_length))
            return null;
        index_offset += name_length;
        byte key = (byte)(name_length+1);
        for (int j = 0; j < name_length; ++j)
        {
            name_buffer[j] -= key--;
            if (name_buffer[j] < 0x20 || name_buffer[j] >= 0xFD)
                return null;
        }
        string name = Encodings.cp932.GetString (name_buffer, 0, name_length);

        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = Binary.BigEndian (file.View.ReadUInt32 (index_offset));
        entry.Size   = Binary.BigEndian (file.View.ReadUInt32 (index_offset+4));
        index_offset += 8;
        if (entry.Offset < index_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".scr"))
            entry.IsPacked = true;
        dir.Add (entry);
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

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Banana/ArcPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
