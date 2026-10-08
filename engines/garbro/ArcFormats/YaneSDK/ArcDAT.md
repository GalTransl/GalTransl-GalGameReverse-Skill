# YaneSDK / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/YaneSDK` / `GameRes.Formats.YaneSDK.PakOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int count = (short)(file.View.ReadUInt16 (0) ^ 0x8080);` |
| `PakOpener.TryOpen` | `entry.EncryptedSize = index.ReadUInt16();` |
| `PakOpener.TryOpen` | `entry.Size = index.ReadUInt32();` |
| `PakOpener.TryOpen` | `entry.Offset = index.ReadUInt32();` |
| `PakOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (yent.Offset, yent.EncryptedSize);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.YaneSDK.YaneEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint EncryptedSize ;
```

### GameRes.Formats.YaneSDK.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = (short)(file.View.ReadUInt16 (0) ^ 0x8080);
    if (!IsSaneCount (count))
        return null;

    using (var input = file.CreateStream())
    using (var dec = new XoredStream (input, 0x80))
    using (var index = new BinaryReader (dec))
    {
        index.BaseStream.Position = 2;
        int data_offset = 2 + 0x2C * count;
        var name_buf = new byte[0x22];
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            if (0x22 != index.Read (name_buf, 0, 0x22))
                return null;
            var name = Binary.GetCString (name_buf, 0);
            if (string.IsNullOrWhiteSpace (name))
                return null;
            var entry = FormatCatalog.Instance.Create<YaneEntry> (name);
            entry.EncryptedSize = index.ReadUInt16();
            entry.Size = index.ReadUInt32();
            entry.Offset = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset) || entry.Offset < data_offset)
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var yent = entry as YaneEntry;
    if (null == yent || 0 == yent.EncryptedSize)
        return base.OpenEntry (arc, entry);
    var header = arc.File.View.ReadBytes (yent.Offset, yent.EncryptedSize);
    for (int i = 0; i < header.Length; ++i)
        header[i] ^= 0x80;
    if (yent.EncryptedSize >= yent.Size)
        return new BinMemoryStream (header);
    var rest = arc.File.CreateStream (yent.Offset + yent.EncryptedSize, yent.Size - yent.EncryptedSize);
    return new PrefixStream (header, rest);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/YaneSDK/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
