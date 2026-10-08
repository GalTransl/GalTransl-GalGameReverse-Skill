# SquadraD / ArcSDA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SDA/SD` / `GameRes.Formats.SquadraD.SdaOpener` | `sda` | `53410000`, `534100cc` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SdaOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "SA\0"))` |
| `SdaOpener.TryOpen` | `int data_offset = file.View.ReadInt32 (4);` |
| `SdaOpener.TryOpen` | `var name = file.View.ReadString (index, 0x10).Trim();;` |
| `SdaOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index+0xC) + data_offset;` |
| `SdaOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index+0x10);` |
| `SdaOpener.LzssDecompress` | `int unpacked_size = input.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SquadraD.SdaOpener

继承/接口：`ArchiveFormat`。

#### SdaOpener

```csharp
public SdaOpener () {
    Signatures = new[] { 0x4153u, 0xCC004153u, 0u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "SA\0"))
        return null;
    int data_offset = file.View.ReadInt32 (4);
    if (data_offset <= 8 || data_offset >= file.MaxOffset)
        return null;
    int count = (data_offset - 8) / 0x14;
    if (!IsSaneCount (count))
        return null;
    string arc_name = Path.GetFileNameWithoutExtension (file.Name);
    bool is_cg = arc_name == "g";
    uint index = 8;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index, 0x10).Trim();;
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index+0xC) + data_offset;
        entry.Size   = file.View.ReadUInt32 (index+0x10);
        if (is_cg)
            entry.Type = "image";
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index += 0x14;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var data = LzssDecompress (input);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### LzssDecompress

```csharp
internal static byte[] LzssDecompress (IBinaryStream input) {
    int unpacked_size = input.ReadInt32();
    var output = new byte[unpacked_size];
    using (var bits = new LsbBitStream (input.AsStream, true))
    {
        var frame = new byte[0x1000];
        int frame_pos = 0xFC0;
        int dst = 0;
        while (dst < unpacked_size)
        {
            if (bits.GetNextBit() == 0)
            {
                byte b = (byte)bits.GetBits (8);
                output[dst++] = frame[frame_pos++ & 0xFFF] = b;
            }
            else
            {
                int count_len = 4;
                if (bits.GetNextBit() != 0)
                    count_len = 6;
                int offset = bits.GetBits (12);
                int count = bits.GetBits (count_len);
                count = Math.Min (count + 3, unpacked_size - dst);
                while (count --> 0)
                {
                    byte b = frame[offset++ & 0xFFF];
                    output[dst++] = frame[frame_pos++ & 0xFFF] = b;
                }
            }
        }
        return output;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../../ArcFormats/BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/SquadraD/ArcSDA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
