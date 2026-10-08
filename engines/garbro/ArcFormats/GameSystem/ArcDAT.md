# GameSystem / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/0verflow` / `GameRes.Formats.GameSystem.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0);` |
| `DatOpener.TryOpen` | `long offset = (long)file.View.ReadUInt32 (index_offset+12) << 9;` |
| `DatOpener.TryOpen` | `var entry_buf = file.View.ReadBytes (index_offset, 12);` |
| `DatOpener.TryOpen` | `long next_offset = (long)file.View.ReadUInt32 (index_offset+12) << 9;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.GameSystem.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (0);
    if (index_size <= 2 || index_size >= (uint.MaxValue >> 9))
        return null;
    index_size <<= 9;
    if (index_size >= file.MaxOffset)
        return null;
    uint index_offset = 0x400;
    long offset = (long)file.View.ReadUInt32 (index_offset+12) << 9;
    if (offset != index_size)
        return null;
    var dir = new List<Entry>();
    var entry_buf = file.View.ReadBytes (index_offset, 12);
    while (!Array.TrueForAll (entry_buf, x => x == 0xFF))
    {
        index_offset += 0x10;
        if (index_offset >= index_size)
            return null;
        var name = RestoreName (entry_buf);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        file.View.Read (index_offset, entry_buf, 0, 12);
        long next_offset = (long)file.View.ReadUInt32 (index_offset+12) << 9;
        if (next_offset < offset || next_offset > file.MaxOffset)
            return null;
        if (name.EndsWith (".CRGB") || name.EndsWith (".CHAR"))
            entry.Type = "image";
        entry.Offset = offset;
        entry.Size = (uint)(next_offset - offset);
        dir.Add (entry);
        offset = next_offset;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### RestoreName

```csharp
static string RestoreName (byte[] index) {
    var name_buf = new byte[0x10];
    int dst = 0;
    for (int i = 0; i < 12; i += 3)
    {
        int word = index[i] << 16 | index[i+1] << 8 | index[i+2];
        name_buf[dst++] = (byte)(0x20 + ((word >> 18) & 0x3F));
        name_buf[dst++] = (byte)(0x20 + ((word >> 12) & 0x3F));
        name_buf[dst++] = (byte)(0x20 + ((word >> 6) & 0x3F));
        name_buf[dst++] = (byte)(0x20 +  (word & 0x3F));
    }
    int name_end = Array.IndexOf<byte> (name_buf, 0x20, 0, 12);
    if (0 == name_end)
        throw new InvalidFormatException();
    if (-1 == name_end)
        name_end = 12;
    var name = Encoding.ASCII.GetString (name_buf, 0, name_end);
    int ext_end = Array.IndexOf<byte> (name_buf, 0x20, 12, 4);
    if (12 == ext_end)
        return name;
    if (-1 == ext_end)
        ext_end = 16;
    var ext = Encoding.ASCII.GetString (name_buf, 12, ext_end-12);
    return name + '.' + ext;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/GameSystem/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
