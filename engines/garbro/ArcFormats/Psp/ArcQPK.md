# Psp / ArcQPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `QPK` / `GameRes.Formats.Psp.PakOpener` | `qpk` | `51504b00` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!index.View.AsciiEqual (0, "QPI\0"))` |
| `PakOpener.TryOpen` | `int count = index.View.ReadInt32 (4);` |
| `PakOpener.TryOpen` | `uint offset = index.View.ReadUInt32 (index_pos);` |
| `PakOpener.TryOpen` | `uint size   = index.View.ReadUInt32 (index_pos+4);` |
| `PakOpener.OpenEntry` | `if (!pent.IsPacked \|\| !arc.File.View.AsciiEqual (pent.Offset, "CZL\0"))` |
| `PakOpener.OpenEntry` | `uint size = arc.File.View.ReadUInt32 (pent.Offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Psp.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var index_name = Path.ChangeExtension (file.Name, "QPI");
    List<Entry> dir;
    using (var index = VFS.OpenView (index_name))
    {
        if (!index.View.AsciiEqual (0, "QPI\0"))
            return null;
        int count = index.View.ReadInt32 (4);
        if (!IsSaneCount (count))
            return null;

        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        string ext = "";
        string type = "";
        if ("TGA" == base_name)
        {
            ext = ".tga";
            type = "image";
        }
        dir = new List<Entry> (count);
        uint index_pos = 0x1C;
        for (int i = 0; i < count; ++i)
        {
            uint offset = index.View.ReadUInt32 (index_pos);
            uint size   = index.View.ReadUInt32 (index_pos+4);
            if (offset > file.MaxOffset)
                return null;
            index_pos += 8;
            if ((size & 0x80000000) != 0 || size == 0)
                continue;
            var entry = new PackedEntry {
                Name = string.Format ("{0}#{1:D5}{2}", base_name, i, ext),
                Type = type,
                Offset = offset,
                UnpackedSize = size & 0x3FFFFFFF,
                IsPacked = (size & 0x40000000) != 0,
            };
            dir.Add (entry);
        }
        long last_offset = file.MaxOffset;
        for (int i = dir.Count - 1; i >= 0; --i)
        {
            dir[i].Size = (uint)(last_offset - dir[i].Offset);
            last_offset = dir[i].Offset;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    if (!pent.IsPacked || !arc.File.View.AsciiEqual (pent.Offset, "CZL\0"))
        return base.OpenEntry (arc, pent);
    uint size = arc.File.View.ReadUInt32 (pent.Offset+4);
    var input = arc.File.CreateStream (pent.Offset+12, size);
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Psp/ArcQPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
