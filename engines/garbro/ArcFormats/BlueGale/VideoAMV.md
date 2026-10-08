# BlueGale / VideoAMV：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AMPV` / `GameRes.Formats.BlueGale.AmvOpener` | `amv` | `616d7056` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AmvOpener.TryOpen` | `if (file.View.ReadInt16 (4) != 1)` |
| `AmvOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (0x16);` |
| `AmvOpener.TryOpen` | `uint width  = file.View.ReadUInt32 (0x1A);` |
| `AmvOpener.TryOpen` | `uint height = file.View.ReadUInt32 (0x1E);` |
| `AmvOpener.TryOpen` | `int count = file.View.ReadInt32 (0x2A);` |
| `AmvOpener.TryOpen` | `uint size = file.View.ReadUInt32 (offset);` |
| `AmvOpener.OpenEntry` | `int header_size = LittleEndian.ToInt32 (output, 0xE);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlueGale.AmvOpener

继承/接口：`ArchiveFormat`。

#### AmvOpener

```csharp
public AmvOpener () {
    Extensions = new string[] { "amv" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadInt16 (4) != 1)
        return null;
    uint unpacked_size = file.View.ReadUInt32 (0x16);
    uint width  = file.View.ReadUInt32 (0x1A);
    uint height = file.View.ReadUInt32 (0x1E);
    int count = file.View.ReadInt32 (0x2A);
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint offset = 0x32;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint size = file.View.ReadUInt32 (offset);
        var entry = new PackedEntry
        {
            Name = string.Format ("{0}#{1:D4}.bmp", base_name, i),
            Type = "image",
            Offset = offset + 4,
            Size = size,
            IsPacked = true,
            UnpackedSize = unpacked_size + 0x36,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        offset += 4 + size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    var output = new byte[pent.UnpackedSize];
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
        ZbmFormat.Unpack (input, output, 0xE);

    output[0] = (byte)'B';
    output[1] = (byte)'M';
    LittleEndian.Pack (pent.UnpackedSize, output, 2);
    int header_size = LittleEndian.ToInt32 (output, 0xE);
    LittleEndian.Pack (header_size+0xE, output, 0xA);
    return new BinMemoryStream (output, entry.Name);
}
```

## 配套算法与外部条件

- [ArcFormats/BlueGale/ImageZBM.cs](ImageZBM.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/BlueGale/VideoAMV.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
