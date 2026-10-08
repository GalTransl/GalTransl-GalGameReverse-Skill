# Aquarium / ImageCP2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Cp2Reader.DecompressLz` | `int remaining = input.ReadInt32();` |
| `Cp2Reader.DecompressLz` | `input.ReadInt32();` |
| `Cp2Reader.DecompressLz` | `int b = input.ReadByte();` |
| `Cp2Reader.DecompressLz` | `int count = input.ReadByte();` |
| `Cp2Reader.DecompressLz` | `int offset = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aquarium.Cp2MetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int  Flags ;

public bool IsCompressed { get { return (Flags & 0x0F) != 0; } }

public bool     HasAlpha { get { return (Flags & 0x20) != 0; } }
```

### GameRes.Formats.Aquarium.Cp2Reader

#### 状态与常量

```csharp
IBinaryStream   m_input ;

Cp2MetaData     m_info ;

byte[]          m_output ;

public BitmapPalette Palette { get; private set; }

public PixelFormat    Format { get; private set; }

public int            Stride { get; private set; }
```

#### Cp2Reader

```csharp
public Cp2Reader (IBinaryStream input, Cp2MetaData info) {
    m_input = input;
    m_info = info;
    switch (info.BPP)
    {
    case 8:  Format = PixelFormats.Indexed8; break;
    case 24: Format = PixelFormats.Bgr24; break;
    case 32: Format = PixelFormats.Bgr32; break;
    default: throw new InvalidFormatException();
    }
    Stride = (((int)info.Width + 31) & ~31) * (info.BPP / 8);
    m_output = new byte[Stride * (int)info.Height];
}
```

#### DecompressLz

```csharp
internal static void DecompressLz (IBinaryStream input, byte[] output) {
    int remaining = input.ReadInt32();
    input.ReadInt32();
    int dst = 0;
    while (dst < output.Length && remaining > 0)
    {
        int b = input.ReadByte();
        if (-1 == b)
            break;
        if (b != 0)
        {
            output[dst++] = (byte)b;
            --remaining;
        }
        else
        {
            int count = input.ReadByte();
            if (count != 0)
            {
                int offset = input.ReadUInt16();
                Binary.CopyOverlapped (output, dst - offset, dst, count);
                dst += count;
                remaining -= 4;
            }
            else
            {
                output[dst++] = 0;
                remaining -= 2;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Aquarium/ImageCP2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
