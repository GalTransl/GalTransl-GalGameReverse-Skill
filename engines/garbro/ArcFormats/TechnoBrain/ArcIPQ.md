# TechnoBrain / ArcIPQ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IPQ` / `GameRes.Formats.TechnoBrain.IpqOpener` | `ipq` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IpqOpener.TryOpen` | `if (file.View.ReadUInt32 (0) != 0x46464952` |
| `IpqOpener.TryOpen` | `\|\| !file.View.AsciiEqual (8, "IPQ fmt "))` |
| `IpqOpener.TryOpen` | `if (ipq.ReadUInt32() != 0x6D696E61)` |
| `IpqOpener.TryOpen` | `uint index_size = ipq.ReadUInt32();` |
| `IpqOpener.TryOpen` | `int count = ipq.ReadInt32();` |
| `IpqOpener.TryOpen` | `Offset = ipq.ReadUInt32(),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.TechnoBrain.IpqArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IpfMetaData     Info ;
```

#### IpqArchive

```csharp
public IpqArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IpfMetaData info)
    : base (arc, impl, dir) {
    Info = info;
}
```

### GameRes.Formats.TechnoBrain.IpqOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<IpfFormat> Ipf = new ResourceInstance<IpfFormat>("IPF") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (0) != 0x46464952
        || !file.View.AsciiEqual (8, "IPQ fmt "))
        return null;
    IpfMetaData ipq_info;
    using (var ipq = file.CreateStream())
    {
        ipq_info = Ipf.Value.ReadIpfHeader (ipq);
        if (null == ipq_info || ipq_info.FormatString != "IPQ fmt ")
            return null;
        ipq.Position = ipq_info.DataOffset;
        if (ipq.ReadUInt32() != 0x6D696E61)
            return null;
        uint index_size = ipq.ReadUInt32();
        int count = ipq.ReadInt32();
        if (!IsSaneCount (count))
            return null;

        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var entry = new Entry {
                Name = string.Format ("{0}#{1:D3}", base_name, i),
                Type = "image",
                Offset = ipq.ReadUInt32(),
            };
            dir.Add (entry);
        }
        long last_offset = file.MaxOffset;
        for (int i = count-1; i >= 0; --i)
        {
            dir[i].Size = (uint)(last_offset - dir[i].Offset);
            last_offset = dir[i].Offset;
        }
        return new IpqArchive (file, this, dir, ipq_info);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/TechnoBrain/ImageIPF.cs](ImageIPF.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/TechnoBrain/ArcIPQ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
