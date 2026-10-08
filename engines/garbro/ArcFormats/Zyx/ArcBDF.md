# Zyx / ArcBDF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BDF` / `GameRes.Formats.Zyx.BdfOpener` | `bdf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BdfArchive.DecodeFrame` | `int cmd = input.ReadByte();` |
| `BdfArchive.DecodeFrame` | `count = input.ReadByte();` |
| `BdfArchive.DecodeFrame` | `count  = 3 * input.ReadByte();` |
| `BdfArchive.DecodeFrame` | `offset = 3 * input.ReadByte();` |
| `BdfArchive.DecodeFrame` | `offset = 3 * input.ReadUInt16();` |
| `BdfArchive.DecodeFrame` | `count = input.ReadUInt16();` |
| `BdfOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `BdfOpener.TryOpen` | `int first_offset = file.View.ReadInt32 (4);` |
| `BdfOpener.TryOpen` | `Offset = base_offset + file.View.ReadUInt32 (index_offset),` |
| `BdfOpener.TryOpen` | `Size = file.View.ReadUInt32 (index_offset+4),` |
| `BdfOpener.TryOpen` | `Incremental = 0 != file.View.ReadInt32 (index_offset+8),` |
| `BdfOpener.TryOpen` | `Width = file.View.ReadInt32 (index_offset+0x14),` |
| `BdfOpener.TryOpen` | `Height = file.View.ReadInt32 (index_offset+0x18),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Zyx.BdfFrame

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  Number ;

public int  Width ;

public int  Height ;

public bool Incremental ;
```

### GameRes.Formats.Zyx.BdfArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public byte[] FirstFrame ;

public ImageMetaData Info { get; private set; }
```

#### BdfArchive

```csharp
public BdfArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir)
    : base (arc, impl, dir) {
    var base_frame = dir.First() as BdfFrame;
    Info = new ImageMetaData {
        Width = (uint)base_frame.Width,
        Height = (uint)base_frame.Height,
        BPP = 24
    };
}
```

#### ReadFrame

```csharp
public byte[] ReadFrame (BdfFrame frame) {
    byte[] pixels;
    if (!frame.Incremental)
    {
        if (null != FirstFrame && 0 == frame.Number)
            return FirstFrame;
        pixels = new byte[frame.Width * frame.Height * 3];
        using (var input = File.CreateStream (frame.Offset, frame.Size))
            DecodeFrame (input, pixels);
        if (null == FirstFrame && 0 == frame.Number)
            FirstFrame = pixels;
    }
    else
    {
        if (null == FirstFrame)
        {
            var base_frame = Dir.First() as BdfFrame;
            FirstFrame = new byte[base_frame.Width * base_frame.Height * 3];
            using (var input = File.CreateStream (base_frame.Offset, base_frame.Size))
                DecodeFrame (input, FirstFrame);
        }
        pixels = FirstFrame.Clone() as byte[];
        int i = 1;
        foreach (BdfFrame entry in Dir.Skip(1))
        {
            if (i++ > frame.Number)
                break;
            using (var input = File.CreateStream (entry.Offset, entry.Size))
                DecodeFrame (input, pixels, entry.Incremental);
        }
    }
    return pixels;
}
```

#### DecodeFrame

```csharp
private void DecodeFrame (IBinaryStream input, byte[] output, bool incremental = false) {
    int v2 = incremental ? 6 : 4;
    int dst = 0;
    while (dst < output.Length)
    {
        int count, offset;
        int cmd = input.ReadByte();
        if (-1 == cmd)
            break;
        switch (cmd)
        {
        case 0:
            {
                int src = dst-3;
                count = input.ReadByte();
                for (int i = 0; i < count; ++i)
                {
                    output[dst++] = output[src];
                    output[dst++] = output[src+1];
                    output[dst++] = output[src+2];
                }
                break;
            }
        case 1:
            {
                count  = 3 * input.ReadByte();
                offset = 3 * input.ReadByte();
                int src = dst - offset;
                Binary.CopyOverlapped (output, src, dst, count);
                dst += count;
                break;
            }
        case 2:
            {
                count  = 3 * input.ReadByte();
                offset = 3 * input.ReadUInt16();
                int src = dst - offset;
                Binary.CopyOverlapped (output, src, dst, count);
                dst += count;
                break;
            }
        case 3:
            {
                offset = 3 * input.ReadByte();
                int src = dst - offset;
                output[dst++] = output[src++];
                output[dst++] = output[src++];
                output[dst++] = output[src++];
                break;
            }
        case 4:
            {
                offset = 3 * input.ReadUInt16();
                int src = dst - offset;
                output[dst++] = output[src++];
                output[dst++] = output[src++];
                output[dst++] = output[src++];
                break;
            }
        default:
            if (v2 < 5 || cmd > 6)
            {
                count = (cmd - v2) * 3;
                input.Read (output, dst, count);
                dst += count;
            }
            else
            {
                if (5 == cmd)
                {
                    count = input.ReadByte();
                }
                else
                {
                    count = input.ReadUInt16();
                }
                dst += 3 * count;
            }
            break;
        }
    }
}
```

### GameRes.Formats.Zyx.BdfOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (count <= 0 || count > 100)
        return null;
    int first_offset = file.View.ReadInt32 (4);
    if (0 != first_offset)
        return null;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);

    int base_offset = 4 + count * 0x1C;
    int index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new BdfFrame {
            Number = i,
            Name = string.Format ("{0}#{1:D2}", base_name, i),
            Type = "image",
            Offset = base_offset + file.View.ReadUInt32 (index_offset),
            Size = file.View.ReadUInt32 (index_offset+4),
            Incremental = 0 != file.View.ReadInt32 (index_offset+8),
            Width = file.View.ReadInt32 (index_offset+0x14),
            Height = file.View.ReadInt32 (index_offset+0x18),
        };
        if (entry.Size > 0)
        {
            if (entry.Size < 4 || entry.Width <= 0 || entry.Height <= 0
                || !entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += 0x1C;
    }
    return new BdfArchive (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Zyx/ArcBDF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
