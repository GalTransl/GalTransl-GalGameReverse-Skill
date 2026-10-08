# Airyu / ArcCHR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CHR/AIRYU` / `GameRes.Formats.Airyu.ChrOpener` | `chr` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Airyu.ChrOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly uint[] ImageSizes = new[] { 0x96000u, 0x4B000u, 0x19000u }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".chr"))
        return null;
    int count = 0;
    uint image_size = 1;
    for (int i = 0; i < ImageSizes.Length; ++i)
    {
        image_size = ImageSizes[i];
        count = (int)(file.MaxOffset / image_size);
        if (IsSaneCount (count) && count * image_size == file.MaxOffset)
            break;
        count = 0;
    }
    if (0 == count)
        return null;

    uint offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = i.ToString ("D5"),
            Type = "image",
            Offset = offset,
            Size = image_size,
        };
        dir.Add (entry);
        offset += image_size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Airyu/ArcCHR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
