# BellDa / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/BLD` / `GameRes.Formats.BellDa.BldOpener` | `dat` | `424c4430` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BldOpener.TryOpen` | `var version_str = file.View.ReadString (4, 4).TrimEnd ('\x1A');` |
| `BldOpener.TryOpen` | `int count = file.View.ReadInt16 (8);` |
| `BldOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xA);` |
| `BldOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0xC);` |
| `BldOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0xC);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BellDa.BldOpener

继承/接口：`Mk2Opener`。

#### BldOpener

```csharp
public BldOpener () {
    Signatures = new[] { this.Signature };
    Settings = null;
    Scheme = null;
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var version_str = file.View.ReadString (4, 4).TrimEnd ('\x1A');
    if (version_str != "0" && version_str != "1" && version_str != "12" && version_str != "3")
        return null;
    int count = file.View.ReadInt16 (8);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (0xA);
    if (index_offset >= file.MaxOffset)
        return null;
    uint data_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0xC);
        var entry = Create<PackedEntry> (name);
        entry.Offset = data_offset;
        entry.Size   = file.View.ReadUInt32 (index_offset+0xC);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 0x10;
        data_offset += entry.Size;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/Maika/ArcMK2.cs](../Maika/ArcMK2.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/BellDa/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
