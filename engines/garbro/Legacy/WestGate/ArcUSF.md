# WestGate / ArcUSF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `USF` / `GameRes.Formats.WestGate.UsfOpener` | `alh`, `usf`, `udc`, `uwb`, `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `UsfOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0xC);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.WestGate.UsfOpener

继承/接口：`ArchiveFormat`。

#### UsfOpener

```csharp
public UsfOpener () {
    Extensions = new string[] { "alh", "usf", "udc", "uwb", "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint first_offset = file.View.ReadUInt32 (0xC);
    if (first_offset >= file.MaxOffset || 0 != (first_offset & 0xF))
        return null;
    int count = (int)(first_offset / 0x10);
    if (!IsSaneCount (count))
        return null;

    var entry_type = "";
    if (IsGraphicArchive (Path.GetFileName (file.Name)))
        entry_type = "image";
    var dir = UcaTool.ReadIndex (file, 0, count, entry_type);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### IsGraphicArchive

```csharp
bool IsGraphicArchive (string name) {
    return name.ToLowerAscii().StartsWith ("grap");
}
```

## 配套算法与外部条件

- [Legacy/WestGate/ArcUCA.cs](ArcUCA.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/WestGate/ArcUSF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
