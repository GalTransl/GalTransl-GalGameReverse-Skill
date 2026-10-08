# Unison / ArcVCT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `VCT` / `GameRes.Formats.Unison.VctOpener` | `vct` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VctOpener.TryOpen` | `int idx_count = file.View.ReadByte (0);` |
| `VctOpener.TryOpen` | `int count = file.View.ReadInt32 (index_offset);` |
| `VctOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x14).TrimEnd();` |
| `VctOpener.TryOpen` | `string ext  = file.View.ReadString (index_offset+0x14, 3);` |
| `VctOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x18);` |
| `VctOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x1C);` |
| `VctOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "LZS\0"))` |
| `VctOpener.OpenEntry` | `if (data.AsciiEqual ("BM") && 32 == data.ToUInt16 (0x1C))` |
| `VctOpener.LzsUnpack` | `input.ReadInt32();` |
| `VctOpener.LzsUnpack` | `int unpacked_size = input.ReadInt32();` |
| `VctOpener.LzsUnpack` | `int packed_size = input.ReadInt32();` |
| `VctOpener.LzsUnpack` | `int ctl_size = input.ReadInt32();` |
| `VctOpener.LzsUnpack` | `var ctl = input.ReadBytes (ctl_size);` |
| `VctOpener.LzsUnpack` | `output[dst++] = frame[frame_pos++ & 0xFFF] = input.ReadUInt8();` |
| `VctOpener.LzsUnpack` | `int offset = input.ReadUInt16();` |
| `VctOpener.FixBitmapAlpha` | `int img_start = bmp.ToInt32 (0xA);` |
| `VctOpener.FixBitmapAlpha` | `if (img_start == 0x42 && bmp.ToInt32 (0x36) == 0xFF && bmp.ToInt32 (0x3E) == 0xFF0000)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unison.VctOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int idx_count = file.View.ReadByte (0);
    if (0 == idx_count)
        return null;
    int index_offset = 1 + idx_count * 3;
    int count = file.View.ReadInt32 (index_offset);
    if (!IsSaneCount (count))
        return null;
    index_offset += 4;
    uint index_size = (uint)count * 0x20;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x14).TrimEnd();
        if (string.IsNullOrWhiteSpace (name))
            return null;
        string ext  = file.View.ReadString (index_offset+0x14, 3);
        if (!string.IsNullOrWhiteSpace (ext))
            name += '.' + ext;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x18);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x1C);
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
    if (!arc.File.View.AsciiEqual (entry.Offset, "LZS\0"))
        return base.OpenEntry (arc, entry);
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var data = LzsUnpack (input);
        if (data.AsciiEqual ("BM") && 32 == data.ToUInt16 (0x1C))
            FixBitmapAlpha (data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### LzsUnpack

```csharp
byte[] LzsUnpack (IBinaryStream input) {
    input.ReadInt32();
    int unpacked_size = input.ReadInt32();
    int packed_size = input.ReadInt32();
    int ctl_size = input.ReadInt32();
    var ctl = input.ReadBytes (ctl_size);
    var output = new byte[unpacked_size];
    var frame = new byte[0x1000];
    int frame_pos = 1;
    int src = 0;
    int dst = 0;
    int bits = 2;
    while (dst < unpacked_size)
    {
        bits >>= 1;
        if (1 == bits)
        {
            bits = ctl[src++] | 0x100;
        }
        if (0 != (bits & 1))
        {
            output[dst++] = frame[frame_pos++ & 0xFFF] = input.ReadUInt8();
        }
        else
        {
            int offset = input.ReadUInt16();
            int count = (offset >> 12) + 2;
            while (count --> 0)
            {
                byte b = frame[offset++ & 0xFFF];
                output[dst++] = frame[frame_pos++ & 0xFFF] = b;
            }
        }
    }
    return output;
}
```

#### FixBitmapAlpha

```csharp
void FixBitmapAlpha (byte[] bmp) {
    int img_start = bmp.ToInt32 (0xA);
    for (int pos = img_start; pos < bmp.Length; pos += 4)
    {
        byte r = bmp[pos];
        bmp[pos] = bmp[pos+2];
        bmp[pos+2] = r;
        bmp[pos+3] ^= 0xFF;
    }
    if (img_start == 0x42 && bmp.ToInt32 (0x36) == 0xFF && bmp.ToInt32 (0x3E) == 0xFF0000)
    {
        LittleEndian.Pack (0xFF0000, bmp, 0x36);
        LittleEndian.Pack (0x0000FF, bmp, 0x3E);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Unison/ArcVCT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
