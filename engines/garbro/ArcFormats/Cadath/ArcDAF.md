# Cadath / ArcDAF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/DAF` / `GameRes.Formats.Cadath.DafOpener` | `arc` | `4441461a` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DafOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `DafOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `DafOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index_offset+4);` |
| `DafOpener.TryOpen` | `var name = file.View.ReadString (index_offset+8, 0x18);` |
| `DafOpener.OpenEntry` | `\|\| !arc.File.View.AsciiEqual (entry.Offset, "SNR\x1A"))` |
| `DafOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset+12, entry.Size-12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Cadath.DafOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 8;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        uint size   = file.View.ReadUInt32 (index_offset+4);
        var name = file.View.ReadString (index_offset+8, 0x18);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Offset = offset;
        entry.Size = size;
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
    if (!entry.Name.HasExtension (".snr")
        || !arc.File.View.AsciiEqual (entry.Offset, "SNR\x1A"))
        return base.OpenEntry (arc, entry);
    try
    {
        var data = arc.File.View.ReadBytes (entry.Offset+12, entry.Size-12);
        DecryptSnr (data);
        CgfDecoder.Decrypt (data, data.Length);

        var input = new MemoryStream (data, 4, data.Length-4);
        return new ZLibStream (input, CompressionMode.Decompress);
    }
    catch
    {
        return base.OpenEntry (arc, entry);
    }
}
```

#### DecryptSnr

```csharp
void DecryptSnr (byte[] data) {
    byte key = 0x84;
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] -= key;
        for (int count = ((i & 0xF) + 2) / 3; count > 0; --count)
        {
            key += 0x99;
        }
    }

}
```

## 配套算法与外部条件

- [ArcFormats/Cadath/ImageCGF.cs](ImageCGF.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cadath/ArcDAF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
