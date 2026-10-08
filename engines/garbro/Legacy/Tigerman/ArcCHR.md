# Tigerman / ArcCHR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CHR/TIGERMAN` / `GameRes.Formats.Tigerman.ChrOpener` | `chr`, `cls`, `ev` | `b1010000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ChrOpener.TryOpen` | `uint base_offset = file.View.ReadUInt32 (0);` |
| `ChrOpener.TryOpen` | `if (base_offset >= file.MaxOffset \|\| !file.View.AsciiEqual (base_offset, "ZT"))` |
| `ChrOpener.TryOpen` | `dir.Add (create_entry (0, base_offset, file.View.ReadUInt32 (4)));` |
| `ChrOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `ChrOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tigerman.ChrOpener

继承/接口：`ArchiveFormat`。

#### ChrOpener

```csharp
public ChrOpener () {
    Extensions = new string[] { "chr", "cls", "ev" };
    Signatures = new uint[] { 0x01B1, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint base_offset = file.View.ReadUInt32 (0);
    if (base_offset >= file.MaxOffset || !file.View.AsciiEqual (base_offset, "ZT"))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry>();
    Func<int, uint, uint, Entry> create_entry = (i, offset, size) => new Entry {
        Name = string.Format ("{0}#{1}.ZIT", base_name, i),
        Type = "image",
        Offset = offset,
        Size = size,
    };
    dir.Add (create_entry (0, base_offset, file.View.ReadUInt32 (4)));
    uint index_offset = 12;
    while (index_offset + 0x24 <= base_offset)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        if (offset != 0)
        {
            uint size   = file.View.ReadUInt32 (index_offset+4);
            var entry = create_entry (dir.Count, offset, size);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += 0x24;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Tigerman/ArcCHR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
