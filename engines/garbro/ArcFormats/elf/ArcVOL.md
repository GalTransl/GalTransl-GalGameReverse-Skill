# elf / ArcVOL：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `VOL/ELF` / `GameRes.Formats.Elf.VolOpener` | `vol` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VolOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0);` |
| `VolOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Elf.VolOpener

继承/接口：`ArchiveFormat`。

#### VolOpener

```csharp
public VolOpener () {
    Extensions = new string[] { "vol" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".vol"))
        return null;
    uint first_offset = file.View.ReadUInt32 (0);
    if (first_offset < 0x10 || 0 != (first_offset & 0xF) || first_offset >= file.MaxOffset)
        return null;
    int count = (int)(first_offset /4);
    if (!IsSaneCount (count))
        return null;

    var offset_table = new List<uint> (count);
    offset_table.Add (first_offset);
    uint index_offset = 4;
    for (int i = 1; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        if (offset < offset_table[i-1] || offset > file.MaxOffset)
            return null;
        offset_table.Add (offset);
        if (offset == file.MaxOffset)
            break;
        index_offset += 4;
    }
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (offset_table.Count-1);
    for (int i = 0; i < offset_table.Count-1; ++i)
    {
        uint size = offset_table[i+1] - offset_table[i];
        if (0 == size)
            continue;
        var name = string.Format ("{0}#{1:D4}", base_name, i);
        var entry = AutoEntry.Create (file, offset_table[i], name);
        entry.Size = size;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/elf/ArcVOL.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
