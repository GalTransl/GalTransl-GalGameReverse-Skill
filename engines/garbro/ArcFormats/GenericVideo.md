# ArcFormats / GenericVideo：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GENERIC` / `GameRes.Formats.AviOpener` | `generic avi` | `52494646` | `False` |
| `GENERIC` / `GameRes.Formats.MpgOpener` | `generic mpg` | `000001ba` | `False` |
| `GENERIC` / `GameRes.Formats.WmvOpener` | `generic wmv` | `3026b275` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WmvOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != 0x11CF668E)` |
| `AviOpener.TryOpen` | `if (file.View.ReadUInt32 (8) != 0x20495641)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.WmvOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (4) != 0x11CF668E)
        return null;
    return new WrapSingleFileArchive (file, Path.GetFileNameWithoutExtension (file.Name)+".wmv");
}
```

### GameRes.Formats.AviOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (8) != 0x20495641)
        return null;
    return new WrapSingleFileArchive (file, Path.GetFileNameWithoutExtension (file.Name)+".avi");
}
```

### GameRes.Formats.MpgOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    return new WrapSingleFileArchive (file, Path.GetFileNameWithoutExtension (file.Name)+".mpg");
}
```

## 配套算法与外部条件

- [ArcFormats/SingleFileArchive.cs](SingleFileArchive.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/GenericVideo.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
