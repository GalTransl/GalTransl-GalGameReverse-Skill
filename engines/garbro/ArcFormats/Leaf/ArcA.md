# Leaf / ArcA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `A/Leaf` / `GameRes.Formats.Leaf.AOpener` | `a` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AOpener.TryOpen` | `if (0xAF1E != file.View.ReadUInt16 (0))` |
| `AOpener.TryOpen` | `int count = file.View.ReadUInt16 (2);` |
| `AOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x17);` |
| `AOpener.TryOpen` | `entry.Key = file.View.ReadByte (index_offset+0x17);` |
| `AOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x18);` |
| `AOpener.TryOpen` | `entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x1C);` |
| `AOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |
| `AOpener.Decrypt` | `uint width = data.ToUInt32 (0);` |
| `AOpener.Decrypt` | `uint height = data.ToUInt32 (4);` |
| `AOpener.Decrypt` | `int type = data.ToUInt16 (0x10);` |
| `AOpener.Decrypt` | `int bits = data.ToUInt16 (0x12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Leaf.ALeafEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte Key ;
```

### GameRes.Formats.Leaf.AOpener

继承/接口：`ArchiveFormat`。

#### AOpener

```csharp
public AOpener () {
    Extensions = new string[] { "a" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0xAF1E != file.View.ReadUInt16 (0))
        return null;
    int count = file.View.ReadUInt16 (2);
    if (!IsSaneCount (count))
        return null;

    long base_offset = 4 + 0x20 * count;
    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x17);
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = FormatCatalog.Instance.Create<ALeafEntry> (name);
        entry.Key = file.View.ReadByte (index_offset+0x17);
        entry.IsPacked = 0 != entry.Key;
        entry.Size   = file.View.ReadUInt32 (index_offset+0x18);
        entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x1C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as ALeafEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    if (0 == pent.UnpackedSize)
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
    Stream input = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
    input = new LzssStream (input);
    if (pent.Key >= 0x7F && pent.Key <= 0x89 && pent.UnpackedSize > 0x20)
    {
        using (input)
            return Decrypt (input, pent.UnpackedSize, (byte)(pent.Key & 0xF));
    }
    return input;
}
```

#### Decrypt

```csharp
Stream Decrypt (Stream input, uint length, byte key) {
    var data = new byte[length];
    input.Read (data, 0, data.Length);
    uint width = data.ToUInt32 (0);
    uint height = data.ToUInt32 (4);
    uint image_size = width * height;
    int type = data.ToUInt16 (0x10);
    int bits = data.ToUInt16 (0x12);
    if (1 == type && 0x20 == bits && image_size > 0 && (32 + image_size * 4) <= length)
    {
        byte r = 0, g = 0, b = 0;
        int dst = 0x20;
        for (uint i = 0; i < image_size; ++i)
        {
            byte a = data[dst+3];
            b += (byte)(data[dst  ] + a - key);
            g += (byte)(data[dst+1] + a - key);
            r += (byte)(data[dst+2] + a - key);
            data[dst++] = b;
            data[dst++] = g;
            data[dst++] = r;
            data[dst++] = 0;
        }
    }
    return new BinMemoryStream (data);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Leaf/ArcA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
