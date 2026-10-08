# Witch / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/WITCH` / `GameRes.Formats.Witch.ArcOpener` | `arc` | `41524320` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `if (file.View.ReadInt32 (4) != 0)` |
| `ArcOpener.TryOpen` | `if (!id.AsciiEqual ("DIR \0\0\0\0"))` |
| `ArcOpener.TryOpen` | `index.ReadInt32();` |
| `ArcOpener.TryOpen` | `int name_length = index.ReadInt32();` |
| `ArcOpener.TryOpen` | `uint size   = index.ReadUInt32();` |
| `ArcOpener.TryOpen` | `uint offset = index.ReadUInt32();` |
| `ArcOpener.TryOpen` | `var name = index.ReadCString (name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Witch.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadInt32 (4) != 0)
        return null;
    using (var index = file.CreateStream())
    {
        long index_pos = 0x10;
        var id = new byte[8];
        var dir = new List<Entry>();
        for (;;)
        {
            index.Position = index_pos;
            if (8 != index.Read (id, 0, 8))
                return null;
            if (!id.AsciiEqual ("DIR \0\0\0\0"))
                break;
            index.ReadInt32();
            int name_length = index.ReadInt32();
            if (name_length <= 0)
                return null;
            index.Seek (0x10, SeekOrigin.Current);
            uint size   = index.ReadUInt32();
            uint offset = index.ReadUInt32();
            var name = index.ReadCString (name_length);
            index_pos += 0x28 + name_length;

            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = offset;
            entry.Size = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Witch/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
