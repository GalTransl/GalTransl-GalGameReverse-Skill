# Ikura / ArcGAN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GAN` / `GameRes.Formats.Ikura.GanOpener` | `gan` | `47414e4d` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GanOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "0100"))` |
| `GanOpener.TryOpen` | `int count = file.View.ReadInt32 (12);` |
| `GanOpener.TryOpen` | `Id     = file.View.ReadInt32 (index_offset),` |
| `GanOpener.TryOpen` | `Ref    = file.View.ReadInt32 (index_offset+4),` |
| `GanOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+8),` |
| `GanOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+12),` |
| `GanFrameArchive.UnpackRefFrame` | `int header_size = input.ReadInt32();` |
| `GanFrameArchive.UnpackRefFrame` | `var header = input.ReadBytes (header_size-4);` |
| `GanFrameArchive.ReadInteger` | `int val = input.ReadByte();` |
| `GanFrameArchive.ReadInteger` | `val = (val & 0x7F) << 8 \| input.ReadUInt8();` |
| `GanFrameArchive.ReadInteger` | `val = input.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ikura.GanEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  Index ;

public int  Id ;

public int  Ref ;
```

### GameRes.Formats.Ikura.GanOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "0100"))
        return null;
    int count = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_offset = 0x2010;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new GanEntry {
            Name   = string.Format ("{0}#{1:D2}", base_name, i),
            Type   = "image",
            Index  = i,
            Id     = file.View.ReadInt32 (index_offset),
            Ref    = file.View.ReadInt32 (index_offset+4),
            Offset = file.View.ReadUInt32 (index_offset+8),
            Size   = file.View.ReadUInt32 (index_offset+12),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x10;
    }
    return new GanFrameArchive (file, this, dir);
}
```

### GameRes.Formats.Ikura.GanFrameArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly ImageMetaData   Info ;

byte[][]    Frames ;

const uint DefaultWidth  = 800 ;

const uint DefaultHeight = 600 ;
```

#### GanFrameArchive

```csharp
public GanFrameArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir)
    : base (arc, impl, dir) {
    Info = new ImageMetaData { Width = DefaultWidth, Height = DefaultHeight, BPP = 24 };
    Frames = new byte[dir.Count][];
}
```

#### GetFrame

```csharp
public byte[] GetFrame (GanEntry entry) {
    int index = entry.Index;
    if (Frames[index] != null)
        return Frames[index];

    byte[] ref_frame = null;
    if (entry.Ref != 0)
    {
        var ref_entry = Dir.Cast<GanEntry>().FirstOrDefault (e => e.Id == entry.Ref);
        if (ref_entry != null && ref_entry != entry)
            ref_frame = GetFrame (ref_entry);
    }
    using (var stream = File.CreateStream (entry.Offset, entry.Size))
    {
        byte[] pixels;
        if (ref_frame != null)
        {
            pixels = ref_frame.Clone() as byte[];
            UnpackRefFrame (stream, pixels);
        }
        else
        {
            pixels = new byte[(int)Info.Width * (int)Info.Height * 3];
            UnpackKeyFrame (stream, pixels);
        }
        Frames[index] = pixels;
        return pixels;
    }
}
```

#### UnpackKeyFrame

```csharp
void UnpackKeyFrame (IBinaryStream input, byte[] output) {
    int last = -1;
    int dst = 0;
    while (dst < output.Length)
    {
        if (input.Read (output, dst, 3) < 3)
            break;
        int color = output[dst] | output[dst+1] << 8 | output[dst+2] << 16;
        dst += 3;
        if (color == last)
        {
            int count = ReadInteger (input);
            if (-1 == count)
                break;
            if (count > 2)
            {
                count = Math.Min ((count - 2) * 3, output.Length - dst);
                Binary.CopyOverlapped (output, dst - 3, dst, count);
                dst += count;
            }
        }
        last = color;
    }
}
```

#### UnpackRefFrame

```csharp
void UnpackRefFrame (IBinaryStream input, byte[] output) {
    int header_size = input.ReadInt32();
    if (header_size < 4)
        throw new InvalidFormatException();
    var header = input.ReadBytes (header_size-4);
    using (var chunks = new BinMemoryStream (header))
    {
        int count = 0;
        int last = -1;
        int dst = 0;
        while (dst < output.Length)
        {
            int length = ReadInteger (chunks);
            if (-1 == length)
                break;
            while (length --> 0)
            {
                if (0 == count)
                {
                    input.Read (output, dst, 3);
                    int color = output[dst] | output[dst+1] << 8 | output[dst+2] << 16;
                    dst += 3;
                    if (color == last)
                    {
                        count = ReadInteger (input);
                        if (-1 == count)
                            return;
                        if (count > 2)
                            count -= 2;
                        else
                            count = 0;
                    }
                    last = color;
                }
                else
                {
                    count--;
                    output[dst++] = (byte)last;
                    output[dst++] = (byte)(last >> 8);
                    output[dst++] = (byte)(last >> 16);
                }
            }
            length = ReadInteger (chunks);
            if (-1 == length)
                break;
            length = Math.Min (length * 3, output.Length - dst);
            dst += length;
        }
    }
}
```

#### ReadInteger

```csharp
static int ReadInteger (IBinaryStream input) {
    int val = input.ReadByte();
    if (-1 == val)
        return val;
    if (val > 0x7F)
    {
        val = (val & 0x7F) << 8 | input.ReadUInt8();
        if (0x7FFF == val)
            val = input.ReadInt32();
    }
    return val;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ikura/ArcGAN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
