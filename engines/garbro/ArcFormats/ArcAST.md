# ArcFormats / ArcAST：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AST` / `GameRes.Formats.AST.ArcOpener` | `` | `41524332`, `41524331` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int version = file.View.ReadByte (3) - 0x30;` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `ArcOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `ArcOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index_offset+4);` |
| `ArcOpener.TryOpen` | `int name_length = file.View.ReadByte (index_offset+8);` |
| `ArcOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_offset+9+name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AST.AstArchive

继承/接口：`ArcFile`。

### GameRes.Formats.AST.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "" };
    Signatures = new uint[] { 0x32435241, 0x31435241 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadByte (3) - 0x30;
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    var name_buf = new byte[32];
    var dir = new List<Entry> (count);
    long index_offset = 8;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    for (int i = 0; i < count; ++i)
    {
        uint offset = next_offset;
        uint size   = file.View.ReadUInt32 (index_offset+4);
        int name_length = file.View.ReadByte (index_offset+8);
        if (name_length > name_buf.Length)
            name_buf = new byte[name_length];
        file.View.Read (index_offset+9, name_buf, 0, (uint)name_length);
        if (i+1 == count)
            next_offset = (uint)file.MaxOffset;
        else
            next_offset = file.View.ReadUInt32 (index_offset+9+name_length);
        if (0 != offset && offset != file.MaxOffset)
        {
            if (2 == version)
                for (int j = 0; j < name_length; ++j)
                    name_buf[j] ^= 0xff;
            uint packed_size;
            if (0 == next_offset)
                packed_size = size;
            else if (next_offset >= offset)
                packed_size = next_offset - offset;
            else
                return null;
            string name = Encodings.cp932.GetString (name_buf, 0, name_length);
            var entry = new PackedEntry
            {
                Name = name,
                Type = FormatCatalog.Instance.GetTypeFromName (name),
                Offset = offset,
                Size = packed_size,
                UnpackedSize = size,
                IsPacked = packed_size != size,
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += 9 + name_length;
    }
    if (2 == version)
        return new AstArchive (file, this, dir);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !(arc is AstArchive))
        return input;
    if (!pent.IsPacked)
    {
        if (0xB8B1AF76 == input.Signature)
            return new XoredStream (input, 0xFF);
        return input;
    }
    var lzss = new LzssStream (input);
    lzss.Config.FrameFill = 0xFF;
    return new XoredStream (lzss, 0xFF);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ArcAST.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
