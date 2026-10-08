# Nekotaro / ArcNSC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NSC` / `GameRes.Formats.Nekotaro.NscOpener` | `nsc` | `4e534346` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NscOpener.TryOpen` | `uint prev_offset = file.View.ReadUInt32 (4);` |
| `NscOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nekotaro.NscOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry>();
    uint prev_offset = file.View.ReadUInt32 (4);
    for (uint index_offset = 8; index_offset < file.MaxOffset; index_offset += 4)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        if (offset <= prev_offset || offset > file.MaxOffset)
            return null;
        uint size = offset - prev_offset;
        var name = string.Format ("{0}#{1:D4}", base_name, dir.Count);
        Entry entry;
        if (size > 4)
            entry = AutoEntry.Create (file, prev_offset, name);
        else
            entry = new Entry { Name = name, Offset = prev_offset };
        entry.Size = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        if (file.MaxOffset == offset)
            break;
        prev_offset = offset;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Nekotaro/ArcNSC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
