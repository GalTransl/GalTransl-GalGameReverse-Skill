# TechnoBrain / ImageIPF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IpfFormat.ReadIpfHeader` | `var header = file.ReadHeader (0x14);` |
| `IpfFormat.ReadIpfHeader` | `if (!header.AsciiEqual (0xC, "fmt "))` |
| `IpfFormat.ReadIpfHeader` | `int fmt_size = header.ToInt32 (0x10);` |
| `IpfFormat.ReadIpfHeader` | `header = file.ReadHeader (0x14 + fmt_size);` |
| `IpfFormat.ReadIpfHeader` | `HasPalette = header.ToInt32 (0x18) != 0,` |
| `IpfFormat.ReadIpfHeader` | `HasBitmap  = header.ToInt32 (0x28) != 0,` |
| `IpfFormat.ReadIpfHeader` | `if (0x206C6170 != file.ReadInt32())` |
| `IpfFormat.ReadIpfHeader` | `info.PalSize = file.ReadInt32();` |
| `IpfFormat.ReadBmpInfo` | `if (0x20706D62 != file.ReadInt32())` |
| `IpfFormat.ReadBmpInfo` | `int bmp_size = file.ReadInt32();` |
| `IpfFormat.ReadBmpInfo` | `info.Width  = file.ReadUInt16();` |
| `IpfFormat.ReadBmpInfo` | `info.Height = file.ReadUInt16();` |
| `IpfFormat.ReadBmpInfo` | `file.ReadUInt32();` |
| `IpfFormat.ReadBmpInfo` | `info.OffsetX = file.ReadInt16();` |
| `IpfFormat.ReadBmpInfo` | `info.OffsetY = file.ReadInt16();` |
| `IpfFormat.ReadBmpInfo` | `info.IsCompressed = 0 != (file.ReadByte() & 1);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.TechnoBrain.IpfMetaData

继承/接口：`ImageMetaData`, `ICloneable`。

#### 状态与常量

```csharp
public bool HasPalette ;

public bool HasBitmap ;

public bool IsCompressed ;

public long PalOffset ;

public int  PalSize ;

public long BmpOffset ;

public long DataOffset ;

public string FormatString ;
```

#### Clone

```csharp
public object Clone () {
    return MemberwiseClone();
}
```

### GameRes.Formats.TechnoBrain.IpfFormat

继承/接口：`ImageFormat`。

#### ReadIpfHeader

```csharp
internal IpfMetaData ReadIpfHeader (IBinaryStream file) {

    if (0x46464952 != file.Signature)
        return null;
    var header = file.ReadHeader (0x14);
    if (!header.AsciiEqual (0xC, "fmt "))
        return null;
    int fmt_size = header.ToInt32 (0x10);
    if (fmt_size < 0x24)
        return null;
    header = file.ReadHeader (0x14 + fmt_size);
    var info = new IpfMetaData {
        BPP = 8,
        HasPalette = header.ToInt32 (0x18) != 0,
        HasBitmap  = header.ToInt32 (0x28) != 0,
        FormatString = header.GetCString (8, 8),
    };
    if (info.HasPalette)
    {
        if (0x206C6170 != file.ReadInt32())
            return null;
        info.PalSize = file.ReadInt32();
        if (info.PalSize < 0x24)
            return null;
        info.PalOffset = file.Position;
        file.Position = info.PalOffset + info.PalSize;
    }
    info.DataOffset = file.Position;
    return info;
}
```

#### ReadBmpInfo

```csharp
internal bool ReadBmpInfo (IBinaryStream file, IpfMetaData info) {
    if (0x20706D62 != file.ReadInt32())
        return false;
    int bmp_size = file.ReadInt32();
    if (bmp_size < 0x1C)
        return false;
    info.BmpOffset = file.Position + 0x18;
    info.Width  = file.ReadUInt16();
    info.Height = file.ReadUInt16();
    file.ReadUInt32();
    info.OffsetX = file.ReadInt16();
    info.OffsetY = file.ReadInt16();
    file.Seek (6, SeekOrigin.Current);
    info.IsCompressed = 0 != (file.ReadByte() & 1);
    return true;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/TechnoBrain/ImageIPF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
