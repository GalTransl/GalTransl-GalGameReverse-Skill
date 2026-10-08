# MAGES / ArcGTF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GTF/Rozen` / `GameRes.Formats.MAGES.GTFOpener` | `gtf` | `020200ff` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GTFOpener.TryOpen` | `int count = Binary.BigEndian(file.View.ReadInt32(8));` |
| `GTFOpener.TryOpen` | `entry.Offset = Binary.BigEndian(file.View.ReadUInt32(16 + 36 * i));` |
| `GTFOpener.TryOpen` | `entry.Size = Binary.BigEndian(file.View.ReadUInt32(16 + 36 * i + 4));` |
| `GTFOpener.TryOpen` | `entry.width = Binary.BigEndian(file.View.ReadUInt16(32 + 36 * i));` |
| `GTFOpener.TryOpen` | `entry.height = Binary.BigEndian(file.View.ReadUInt16(32 + 36 * i + 2));` |
| `GTFOpener.ReadImageGTF` | `byte[] inputData = input.ReadBytes((int)input.Length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MAGES.GTFOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    int count = Binary.BigEndian(file.View.ReadInt32(8));
    if (!IsSaneCount(count))
        return null;
    string filename = Path.GetFileNameWithoutExtension(file.Name);
    var dir = new List<Entry>(count);
    for (int i = 0; i < count; i++)
    {
        var entry = Create<Entry_RawImage>(filename + '_' + i.ToString());
        entry.Offset = Binary.BigEndian(file.View.ReadUInt32(16 + 36 * i));
        entry.Size = Binary.BigEndian(file.View.ReadUInt32(16 + 36 * i + 4));
        entry.width = Binary.BigEndian(file.View.ReadUInt16(32 + 36 * i));
        entry.height = Binary.BigEndian(file.View.ReadUInt16(32 + 36 * i + 2));
        entry.Type = "image";
        dir.Add(entry);
    }
    return new ArcFile(file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var compentry = (Entry_RawImage)entry;
    IBinaryStream input = arc.File.CreateStream(entry.Offset, entry.Size, entry.Name);
    return ReadImageGTF(input, compentry.width, compentry.height);
}
```

#### ReadImageGTF

```csharp
static Stream ReadImageGTF(IBinaryStream input, ushort width, ushort height) {

    byte[] widths = BitConverter.GetBytes(width);
    byte[] heights = BitConverter.GetBytes(height);
    byte[] bpp = BitConverter.GetBytes((uint)32);

    byte[] inputData = input.ReadBytes((int)input.Length);
    byte[] outputData = new byte[widths.Length + heights.Length + bpp.Length + inputData.Length];
    Buffer.BlockCopy(widths, 0, outputData, 0, widths.Length);
    Buffer.BlockCopy(heights, 0, outputData, widths.Length, heights.Length);
    Buffer.BlockCopy(bpp, 0, outputData, widths.Length + heights.Length, bpp.Length);
    Buffer.BlockCopy(inputData, 0, outputData, widths.Length + heights.Length + bpp.Length, inputData.Length);
    return new BinMemoryStream(outputData);

}
```

### GameRes.Formats.MAGES.GTFOpener.Entry_RawImage

继承/接口：`Entry`。

#### 状态与常量

```csharp
public ushort width { get; set; }

public ushort height { get; set; }
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MAGES/ArcGTF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
