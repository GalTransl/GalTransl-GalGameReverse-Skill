# Silky / ArcAi6Win：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/AI6WIN` / `GameRes.Formats.Silky.Ai6Opener` | `arc` | 无固定签名或来源表达式未解析 | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Ai6Opener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `Ai6Opener.TryOpen` | `entry.Size          = Binary.BigEndian (file.View.ReadUInt32 (index_offset));` |
| `Ai6Opener.TryOpen` | `entry.UnpackedSize  = Binary.BigEndian (file.View.ReadUInt32 (index_offset+4));` |
| `Ai6Opener.TryOpen` | `entry.Offset        = Binary.BigEndian (file.View.ReadUInt32 (index_offset+8));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Silky.Ai6Opener

继承/接口：`ArchiveFormat`。

#### Ai6Opener

```csharp
public Ai6Opener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    long index_offset = 4;
    uint index_size = (uint)(count * (0x104 + 12));
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var name_buffer = new byte[0x104];
    var dir = new List<Entry>();
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_offset, name_buffer, 0, (uint)name_buffer.Length);
        int name_length = Array.IndexOf<byte> (name_buffer, 0);
        if (0 == name_length)
            return null;
        if (-1 == name_length)
            name_length = name_buffer.Length;
        byte key = (byte)(name_length+1);
        for (int j = 0; j < name_length; ++j)
        {
            name_buffer[j] -= key--;
            char c = (char)name_buffer[j];
            if (VFS.InvalidFileNameChars.Contains (c) && c != '/')
                return null;
        }
        var name = Encodings.cp932.GetString (name_buffer, 0, name_length);
        index_offset += 0x104;
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Size          = Binary.BigEndian (file.View.ReadUInt32 (index_offset));
        entry.UnpackedSize  = Binary.BigEndian (file.View.ReadUInt32 (index_offset+4));
        entry.Offset        = Binary.BigEndian (file.View.ReadUInt32 (index_offset+8));
        if (entry.Offset < index_size+4 || !entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        dir.Add (entry);
        index_offset += 12;
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

来源文件标识 `ArcFormats/Silky/ArcAi6Win.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
