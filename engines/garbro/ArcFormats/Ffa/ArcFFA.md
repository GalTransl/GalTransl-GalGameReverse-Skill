# Ffa / ArcFFA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FFA/ARC` / `GameRes.Formats.Ffa.ArcOpener` | `arc` | `4d325459`, `4d32545f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `if (file.View.AsciiEqual (0, "M2TYPE_WAV"))` |
| `ArcOpener.TryOpen` | `else if (file.View.AsciiEqual (0, "M2T_BMP"))` |
| `ArcOpener.TryOpen` | `else if (file.View.AsciiEqual (0, "M2T_WORD"))` |
| `ArcOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (file.MaxOffset-12);` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (file.MaxOffset-8);` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `ArcOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x10);` |
| `ArcOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x14);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ffa.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
    Signatures = new uint[] { 0x5954324d, 0x5f54324d };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {

    string type;
    if (file.View.AsciiEqual (0, "M2TYPE_WAV"))
        type = "wave";
    else if (file.View.AsciiEqual (0, "M2T_BMP"))
        type = "bmp_";
    else if (file.View.AsciiEqual (0, "M2T_WORD"))
        type = "word";
    else
        return null;

    uint index_size = file.View.ReadUInt32 (file.MaxOffset-12);
    long index_offset = file.MaxOffset-0x14-index_size;
    int count = file.View.ReadInt32 (file.MaxOffset-8);
    if (index_offset <= 0 || count <= 0 || count > 0xfffff)
        return null;
    file.View.Reserve (index_offset, index_size);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x10);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ffa/ArcFFA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
