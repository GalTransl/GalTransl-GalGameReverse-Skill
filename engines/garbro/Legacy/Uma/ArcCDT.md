# Uma / ArcCDT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CDT/UMA` / `GameRes.Formats.Uma.CdtOpener` | `cdt`, `spt` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CdtOpener.TryOpen` | `var name = input.ReadCString (0x10);` |
| `CdtOpener.TryOpen` | `entry.UnpackedSize = input.ReadUInt32();` |
| `CdtOpener.TryOpen` | `entry.Size         = input.ReadUInt32();` |
| `CdtOpener.TryOpen` | `entry.IsPacked     = input.ReadInt32() != 0;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Uma.CdtOpener

继承/接口：`ArchiveFormat`。

#### CdtOpener

```csharp
public CdtOpener () {
    Extensions = new string[] { "cdt", "spt" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasAnyOfExtensions ("cdt", "spt"))
        return null;
    using (var input = file.CreateStream())
    {
        var dir = new List<Entry>();
        while (input.PeekByte() != -1)
        {
            var name = input.ReadCString (0x10);
            if (string.IsNullOrWhiteSpace (name))
                return null;
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.UnpackedSize = input.ReadUInt32();
            entry.Size         = input.ReadUInt32();
            entry.IsPacked     = input.ReadInt32() != 0;
            entry.Offset       = input.Position;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            input.Seek (entry.Size, SeekOrigin.Current);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new LzssStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Uma/ArcCDT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
