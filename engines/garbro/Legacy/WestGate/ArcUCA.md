# WestGate / ArcUCA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `UCA` / `GameRes.Formats.WestGate.UcaOpener` | `uca`, `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `UcaOpener.TryOpen` | `if (file.View.ReadUInt32 (0) != 0)` |
| `UcaOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `UcaTool.ReadIndex` | `uint next_offset = file.View.ReadUInt32 (index_offset+0xC);` |
| `UcaTool.ReadIndex` | `var name = file.View.ReadString (index_offset, 0xC);` |
| `UcaTool.ReadIndex` | `next_offset = file.View.ReadUInt32 (index_offset+0xC);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.WestGate.UcaOpener

继承/接口：`ArchiveFormat`。

#### UcaOpener

```csharp
public UcaOpener () {
    Extensions = new[] { "uca", "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (0) != 0)
        return null;
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    var dir = UcaTool.ReadIndex (file, 0x10, count, "image");
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.WestGate.UcaTool

#### ReadIndex

```csharp
public static List<Entry> ReadIndex (ArcView file, uint index_offset, int count, string entry_type) {
    uint data_offset = index_offset + (uint)count * 0x10;
    uint next_offset = file.View.ReadUInt32 (index_offset+0xC);
    if (next_offset < data_offset)
        return null;
    string last_name = null;
    var invalid_chars = Path.GetInvalidFileNameChars();
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0xC);
        if (last_name == name || string.IsNullOrWhiteSpace (name) || name.IndexOfAny (invalid_chars) != -1)
            return null;
        last_name = name;
        index_offset += 0x10;
        var entry = new Entry { Name = name, Type = entry_type };
        entry.Offset = next_offset;
        if (i+1 == count)
            next_offset = (uint)file.MaxOffset;
        else
            next_offset = file.View.ReadUInt32 (index_offset+0xC);
        if (next_offset <= entry.Offset || next_offset > file.MaxOffset)
            return null;
        entry.Size = (uint)(next_offset - entry.Offset);
        dir.Add (entry);
    }
    return dir;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/WestGate/ArcUCA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
