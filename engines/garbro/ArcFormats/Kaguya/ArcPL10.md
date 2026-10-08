# Kaguya / ArcPL10：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PL10/KAGUYA` / `GameRes.Formats.Kaguya.PL10Opener` | `plt` | `504c3130` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PL10Opener.TryOpen` | `int frame_count = file.View.ReadUInt16(current_offset);` |
| `PL10Opener.TryOpen` | `OffsetX = file.View.ReadInt32(current_offset),` |
| `PL10Opener.TryOpen` | `OffsetY = file.View.ReadInt32(current_offset + 4),` |
| `PL10Opener.TryOpen` | `Width = file.View.ReadUInt32(current_offset + 8),` |
| `PL10Opener.TryOpen` | `Height = file.View.ReadUInt32(current_offset + 12),` |
| `PL10Opener.TryOpen` | `int channels = file.View.ReadInt32(current_offset + 0x10);` |
| `PL10Opener.TryOpen` | `int step = file.View.ReadByte(current_offset++);` |
| `PL10Opener.TryOpen` | `uint packed_size = file.View.ReadUInt32(current_offset);` |
| `PL10Opener.DecompressRLE` | `byte v1 = input.ReadUInt8();` |
| `PL10Opener.DecompressRLE` | `byte v2 = input.ReadUInt8();` |
| `PL10Opener.DecompressRLE` | `int count = input.ReadUInt8();` |
| `PL10Opener.DecompressRLE` | `count = input.ReadUInt8() + ((count & 0x7F) << 8) + 128;` |
| `PL10Opener.DecompressRLE` | `v2 = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.PL10Entry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int FrameIndex ;

public int RleStep ;
```

### GameRes.Formats.Kaguya.PL10Opener

继承/接口：`ArchiveFormat`。

#### PL10Opener

```csharp
public PL10Opener() {
    Extensions = new string[] { "plt" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    uint current_offset = 4;
    int frame_count = file.View.ReadUInt16(current_offset);
    if (!IsSaneCount(frame_count))
        return null;
    current_offset += 0x12;
    string base_name = Path.GetFileNameWithoutExtension(file.Name);
    var dir = new List<Entry>(frame_count);
    var info = new ImageMetaData
    {
        OffsetX = file.View.ReadInt32(current_offset),
        OffsetY = file.View.ReadInt32(current_offset + 4),
        Width = file.View.ReadUInt32(current_offset + 8),
        Height = file.View.ReadUInt32(current_offset + 12),
    };
    int channels = file.View.ReadInt32(current_offset + 0x10);
    info.BPP = channels * 8;
    current_offset += 0x14;
    var entry = new PL10Entry
    {
        FrameIndex = 0,
        Name = string.Format("{0}#{1:D2}", base_name, 0),
        Type = "image",
        Offset = current_offset,
        Size = (uint)channels * info.Width * info.Height,
        IsPacked = false,
    };
    dir.Add(entry);
    current_offset += entry.Size;
    for (int i = 1; i < frame_count; ++i)
    {
        int step = file.View.ReadByte(current_offset++);
        if (0 == step)
            return null;
        uint packed_size = file.View.ReadUInt32(current_offset);
        uint unpacked_size = (uint)(channels * (info.OffsetX + (int)info.Width)
                                             * (info.OffsetY + (int)info.Height));
        current_offset += 4;
        entry = new PL10Entry
        {
            FrameIndex = i,
            Name = string.Format("{0}#{1:D2}", base_name, i),
            Type = "image",
            Offset = current_offset,
            Size = packed_size,
            UnpackedSize = unpacked_size,
            IsPacked = true,
            RleStep = step,
        };
        dir.Add(entry);
        current_offset += packed_size;
    }
    return new PL10Archive(file, this, dir, info);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var anent = entry as PL10Entry;
    var input = arc.File.CreateStream(entry.Offset, entry.Size);
    if (null == anent || !anent.IsPacked)
        return input;
    using (input)
    {
        var data = DecompressRLE(input, anent.UnpackedSize, anent.RleStep);
        return new BinMemoryStream(data);
    }
}
```

#### DecompressRLE

```csharp
internal static byte[] DecompressRLE(IBinaryStream input, uint unpacked_size, int rle_step) {
    var output = new byte[unpacked_size];
    for (int i = 0; i < rle_step; ++i)
    {
        byte v1 = input.ReadUInt8();
        output[i] = v1;
        int dst = i + rle_step;
        while (dst < output.Length)
        {
            byte v2 = input.ReadUInt8();
            output[dst] = v2;
            dst += rle_step;
            if (v2 == v1)
            {
                int count = input.ReadUInt8();
                if (0 != (count & 0x80))
                    count = input.ReadUInt8() + ((count & 0x7F) << 8) + 128;
                while (count-- > 0 && dst < output.Length)
                {
                    output[dst] = v2;
                    dst += rle_step;
                }
                if (dst < output.Length)
                {
                    v2 = input.ReadUInt8();
                    output[dst] = v2;
                    dst += rle_step;
                }
            }
            v1 = v2;
        }
    }
    return output;
}
```

### GameRes.Formats.Kaguya.PL10Archive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
byte[][] Frames ;

public readonly ImageMetaData ImageInfo ;
```

#### PL10Archive

```csharp
public PL10Archive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ImageMetaData base_info)
    : base(arc, impl, dir) {
    Frames = new byte[dir.Count][];
    ImageInfo = base_info;
}
```

#### GetFrame

```csharp
public byte[] GetFrame(int index) {
    if (index >= Frames.Length)
        throw new ArgumentException("index");
    if (null != Frames[index])
        return Frames[index];

    var entry = Dir.ElementAt(index);
    byte[] pixels;
    using (var stream = OpenEntry(entry))
    {
        pixels = new byte[stream.Length];
        stream.Read(pixels, 0, pixels.Length);
    }
    if (index > 0)
    {
        var prev_frame = GetFrame(index - 1);
        for (int i = 0; i < pixels.Length; ++i)
            pixels[i] += prev_frame[i];
    }
    Frames[index] = pixels;
    return pixels;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcPL10.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
