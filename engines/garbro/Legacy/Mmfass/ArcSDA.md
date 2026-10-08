# Mmfass / ArcSDA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SDA/MMFASS` / `GameRes.Formats.Mmfass.SdaOpener` | `sda` | `53410030`, `53410000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SdaOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "SA"))` |
| `SdaOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (4);` |
| `SdaOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x14).Trim();` |
| `SdaOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x14) + data_offset;` |
| `SdaOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x18);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Mmfass.SdaOpener

继承/接口：`ArchiveFormat`。

#### SdaOpener

```csharp
public SdaOpener () {
    Signatures = new uint[] { 0x30004153, 0x4153, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "SA"))
        return null;
    uint data_offset = file.View.ReadUInt32 (4);
    if (data_offset <= 8 || data_offset >= file.MaxOffset)
        return null;
    int count = (int)(data_offset - 8) / 0x1C;
    if (!IsSaneCount (count))
        return null;
    bool is_graphic = Path.GetFileNameWithoutExtension (file.Name).Equals ("g", StringComparison.OrdinalIgnoreCase);
    uint index_offset = 8;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x14).Trim();
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x14) + data_offset;
        entry.Size   = file.View.ReadUInt32 (index_offset+0x18);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (is_graphic)
            entry.Type = "image";
        dir.Add (entry);
        index_offset += 0x1C;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Mmfass/ArcSDA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
