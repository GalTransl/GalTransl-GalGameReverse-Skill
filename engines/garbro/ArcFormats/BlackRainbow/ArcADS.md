# BlackRainbow / ArcADS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ADS` / `GameRes.Formats.BlackRainbow.AdsOpener` | `ads` | `4e51d984` | `False` |

## 类型别名

| 摘录中的名称 | 来源类型 |
|---|---|
| `EncryptedViewStream` | `NScripter.EncryptedViewStream` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AdsOpener.ReadIndex` | `int count = reader.ReadInt32();` |
| `AdsOpener.ReadIndex` | `uint base_offset = reader.ReadUInt32();` |
| `AdsOpener.ReadIndex` | `uint offset = reader.ReadUInt32();` |
| `AdsOpener.ReadIndex` | `entry.Size = reader.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackRainbow.AdsOpener

继承/接口：`ArchiveFormat`。

#### AdsOpener

```csharp
public AdsOpener () {
    Signatures = new uint[] { 0x84D9514E, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".ads"))
        return null;
    var arc_name = Path.GetFileNameWithoutExtension (file.Name);
    foreach (var key in KnownKeys.Values)
    {
        using (var arc = new EncryptedViewStream (file, key))
        {
            uint signature = FormatCatalog.ReadSignature (arc);
            if (2 == signature || 4 == signature || 5 == signature)
            {
                var dir = ReadIndex (arc, key, arc_name);
                if (dir != null)
                    return new AdsArchive (file, this, dir, key);
            }
        }
    }
    return null;
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (Stream arc, byte[] key, string arc_name) {
    arc.Position = 8;
    using (var reader = new ArcView.Reader (arc))
    {
        int count = reader.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        uint base_offset = reader.ReadUInt32();
        uint index_size = 4u * (uint)count;
        var max_offset = arc.Length;
        if (base_offset >= max_offset || base_offset < (0x10+index_size))
            return null;
        var index = new List<uint> (count);
        for (int i = 0; i < count; ++i)
        {
            uint offset = reader.ReadUInt32();
            if (offset != 0xffffffff)
            {
                if (offset >= max_offset-base_offset)
                    return null;
                index.Add (base_offset + offset);
            }
        }
        var name_buffer = new byte[0x20];
        var dir = new List<Entry> (index.Count);
        for (int i = 0; i < index.Count; ++i)
        {
            long offset = index[i];
            reader.BaseStream.Position = offset;
            reader.Read (name_buffer, 0, 0x20);
            string name = Binary.GetCString (name_buffer, 0, 0x20);
            Entry entry;
            if (0 == name.Length)
                entry = new Entry { Name = string.Format ("{0}#{1:D5}", arc_name, i), Type = "image" };
            else
                entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = offset + 0x24;
            entry.Size = reader.ReadUInt32();
            dir.Add (entry);
        }
        return dir;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var ads_arc = arc as AdsArchive;
    if (null == ads_arc)
        return base.OpenEntry (arc, entry);
    var input = new EncryptedViewStream (ads_arc.File, ads_arc.Key);
    return new StreamRegion (input, entry.Offset, entry.Size);
}
```

### GameRes.Formats.BlackRainbow.AdsArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### AdsArchive

```csharp
public AdsArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

## 配套算法与外部条件

- [ArcFormats/NScripter/EncryptedStream.cs](../NScripter/EncryptedStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/BlackRainbow/ArcADS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
