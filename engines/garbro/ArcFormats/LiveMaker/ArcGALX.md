# LiveMaker / ArcGALX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GAL/X` / `GameRes.Formats.LiveMaker.GalXOpener` | `gal` | `47616c65` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GalXOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "X200"))` |
| `GalXOpener.TryOpen` | `uint layer_size = gal.ReadUInt32();` |
| `GalXOpener.TryOpen` | `uint alpha_size = gal.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.LiveMaker.GalXEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public GalXMetaData     Info ;

public XmlNode          Layers ;

public bool             AlphaOn ;
```

### GameRes.Formats.LiveMaker.GalXOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<GalXFormat> s_GalXFormat = new ResourceInstance<GalXFormat> ("GAL/X200") ;

GalXFormat GalXFormat { get { return s_GalXFormat.Value; } }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "X200"))
        return null;
    using (var gal = file.CreateStream())
    {
        var info = GalXFormat.ReadMetaData (gal) as GalXMetaData;
        if (null == info || !IsSaneCount (info.FrameCount))
            return null;
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        gal.Position = info.DataOffset;
        var dir = new List<Entry> (info.FrameCount);
        foreach (XmlNode node in info.FrameXml.SelectNodes ("Frame"))
        {
            var layers = node.SelectSingleNode ("Layers");
            var entry = new GalXEntry {
                Name = string.Format ("{0}#{1:D4}", base_name, dir.Count),
                Type = "image",
                Offset = gal.Position,
                Layers = layers,
                Info = info,
            };
            var nodes = layers.SelectNodes ("Layer");
            entry.AlphaOn = nodes.Count > 0 && nodes[0].Attributes["AlphaOn"].Value != "0";
            foreach (XmlNode layer in nodes)
            {
                bool alpha_on = layer.Attributes["AlphaOn"].Value != "0";
                uint layer_size = gal.ReadUInt32();
                gal.Seek (layer_size, SeekOrigin.Current);
                if (alpha_on)
                {
                    uint alpha_size = gal.ReadUInt32();
                    gal.Seek (alpha_size, SeekOrigin.Current);
                }
            }
            entry.Size = (uint)(gal.Position - entry.Offset);
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LiveMaker/ImageGALX.cs](ImageGALX.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/LiveMaker/ArcGALX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
