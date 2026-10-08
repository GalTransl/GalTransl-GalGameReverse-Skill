# Winters / ArcCFP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CFP/CAPYBARA` / `GameRes.Formats.Winters.CfpOpener` | `cfp` | `43415059` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CfpOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "CAPYBARA DAT 002"))` |
| `CfpOpener.TryOpen` | `uint names_offset = file.View.ReadUInt32 (0x14);` |
| `CfpOpener.TryOpen` | `uint names_length = file.View.ReadUInt32 (0x18);` |
| `CfpOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `CfpOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Winters.CfpOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "CAPYBARA DAT 002"))
        return null;
    uint names_offset = file.View.ReadUInt32 (0x14);
    uint names_length = file.View.ReadUInt32 (0x18);
    uint index_offset = 0x20;
    var dir = new List<Entry>();
    using (var names = file.CreateStream (names_offset, names_length))
    using (var index = new StreamReader (names, Encodings.cp932))
    {
        string name;
        while (index_offset < names_offset && (name = index.ReadLine()) != null)
        {
            if (name.Length > 0)
            {
                var entry = FormatCatalog.Instance.Create<Entry> (name);
                entry.Offset = file.View.ReadUInt32 (index_offset);
                entry.Size   = file.View.ReadUInt32 (index_offset+4);
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                dir.Add (entry);
            }
            index_offset += 0xC;
        }
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Winters/ArcCFP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
