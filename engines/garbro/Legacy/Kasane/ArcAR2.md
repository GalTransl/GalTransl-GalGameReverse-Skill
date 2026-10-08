# Kasane / ArcAR2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AR2/IDX` / `GameRes.Formats.Kasane.Ar2Opener` | `ar2` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Ar2Opener.TryOpen` | `int count = idx.ReadInt32();` |
| `Ar2Opener.TryOpen` | `uint size       = idx.ReadUInt32();` |
| `Ar2Opener.TryOpen` | `uint unpacked_size = idx.ReadUInt32();` |
| `Ar2Opener.TryOpen` | `idx.ReadInt32();` |
| `Ar2Opener.TryOpen` | `int name_length = idx.ReadInt32();` |
| `Ar2Opener.TryOpen` | `uint offset     = idx.ReadUInt32();` |
| `Ar2Opener.OpenEntry` | `uint name_length = arc.File.View.ReadUInt32 (entry.Offset+0xC) ^ 0x55555555u;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kasane.Ar2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".ar2"))
        return null;
    var idx_name = Path.ChangeExtension (file.Name, ".idx");
    using (var idx_view = VFS.OpenView (idx_name))
    using (var idx = idx_view.CreateStream())
    {
        int count = idx.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        var name_buffer = new byte[0x100];
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            uint size       = idx.ReadUInt32();
            uint unpacked_size = idx.ReadUInt32();
            idx.ReadInt32();
            int name_length = idx.ReadInt32();
            uint offset     = idx.ReadUInt32();
            if (name_length > name_buffer.Length)
                return null;
            idx.Read (name_buffer, 0, name_length);
            for (int j = 0; j < name_length; ++j)
                name_buffer[j] ^= 0x55;
            var name = Encodings.cp932.GetString (name_buffer, 0, name_length);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = offset;
            entry.Size   = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    uint name_length = arc.File.View.ReadUInt32 (entry.Offset+0xC) ^ 0x55555555u;
    var input = arc.File.CreateStream (entry.Offset + 0x10 + name_length, entry.Size);
    return new XoredStream (input, 0x55);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../../ArcFormats/CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Kasane/ArcAR2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
