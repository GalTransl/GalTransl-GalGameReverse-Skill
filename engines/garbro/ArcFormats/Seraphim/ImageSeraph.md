# Seraphim / ImageSeraph：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SeraphReader.UnpackRgb` | `int ctl = m_input.ReadByte();` |
| `SeraphReader.UnpackRgb` | `FillBytes (dst, (byte)m_input.ReadByte(), count);` |
| `SeraphReader.UnpackRgb` | `count = m_input.ReadByte() \| ((ctl & 0xF) << 8);` |
| `SeraphReader.UnpackRgb` | `count = m_input.ReadByte() + ((ctl & 7) << 8) + 1;` |
| `SeraphReader.UnpackRgb` | `int offset = m_input.ReadByte() + ((ctl & 0xF) << 8) + 1;` |
| `SeraphReader.UnpackRgb` | `count = m_input.ReadByte() + 1;` |
| `SeraphReader.UnpackBytes` | `int next = m_input.ReadByte();` |
| `SeraphReader.UnpackBytes` | `byte v = (byte)m_input.ReadByte();` |
| `SeraphReader.UnpackBytes` | `count = m_input.ReadByte() \| ((next & 0xF) << 8);` |
| `SeraphReader.UnpackBytes` | `count = m_input.ReadByte() + ((next & 7) << 8) + 1;` |
| `SeraphReader.UnpackBytes` | `int offset = m_input.ReadByte() \| ((next & 0xF) << 8);` |
| `SeraphReader.UnpackBytes` | `count = m_input.ReadByte() + 1;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Seraphim.SeraphMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int PackedSize ;

public int Colors ;
```

### GameRes.Formats.Seraphim.SeraphReader

#### 状态与常量

```csharp
Stream      m_input ;

byte[]      m_output ;

int         m_width ;

int         m_height ;

int         m_stride ;

int         m_colors ;

int         m_packed_size ;

int         m_pixel_size ;

public byte[]           Data { get { return m_output; } }

public PixelFormat    Format { get; private set; }

public BitmapPalette Palette { get; private set; }

public ImageMetaData    Info { get; private set; }
```

#### SeraphReader

```csharp
public SeraphReader (Stream input, SeraphMetaData info, int pixel_size = 3) {
    Info = info;
    m_input = input;
    m_input.Position = 0x10;
    m_width = (int)info.Width;
    m_height = (int)info.Height;
    m_stride = m_width * pixel_size;
    m_output = new byte[m_stride * m_height];
    m_packed_size = info.PackedSize;
    m_colors = info.Colors;
    m_pixel_size = pixel_size;
    if (1 == pixel_size && m_colors > 0)
        Palette = ReadPalette (m_colors);
}
```

#### ReadPalette

```csharp
public BitmapPalette ReadPalette (int colors) {
    return ImageFormat.ReadPalette (m_input, Math.Min (colors, 0x100), PaletteFormat.Rgb);
}
```

#### UnpackCb

```csharp
public void UnpackCb () {
    var pixels = UnpackBytes();
    int dst = 0;
    for (int src = (m_height-1) * m_width; src >= 0; src -= m_width)
    {
        Buffer.BlockCopy (pixels, src, m_output, dst, m_width);
        dst += m_width;
    }
    Format = PixelFormats.Indexed8;
}
```

#### UnpackCt

```csharp
public void UnpackCt () {
    UnpackRgb();
    m_input.Position = 0x10 + m_packed_size + 4;
    var alpha = UnpackBytes();
    var pixels = new byte[m_width*m_height*4];
    int dst = 0;
    for (int y = m_height-1; y >= 0; --y)
    {
        int rgb = y * m_stride;
        int a   = y * m_width;
        for (int x = 0; x < m_width; ++x)
        {
            pixels[dst++] = m_output[rgb++];
            pixels[dst++] = m_output[rgb++];
            pixels[dst++] = m_output[rgb++];
            int v = Math.Min (alpha[a++] * 0xff / 0x64, 0xff);
            pixels[dst++] = (byte)~v;
        }
    }
    m_output = pixels;
    Format = PixelFormats.Bgra32;
}
```

#### UnpackCf

```csharp
public void UnpackCf () {
    UnpackRgb();
    FlipPixels();
    Format = PixelFormats.Bgr24;
}
```

#### UnpackCx

```csharp
public void UnpackCx () {
    UnpackRgb();
    FlipPixels();
    Format = PixelFormats.Bgra32;
}
```

#### UnpackRgb

```csharp
private void UnpackRgb ()
    int dst = 0;
    while (dst < m_output.Length)
    {
        int count;
        int ctl = m_input.ReadByte();
        if (-1 == ctl)
            break;
        if ((ctl & 0xF0) == 0xF0)
            throw new InvalidFormatException();

        if (0 == (ctl & 0x80))
        {
            if (0 != (ctl & 0x40))
            {
                count = (ctl & 0x3F) + 2;
                FillBytes (dst, (byte)m_input.ReadByte(), count);
            }
            else
            {
                count = (ctl & 0x3F) + 1;
                if (count != m_input.Read (m_output, dst, count))
                    break;
            }
        }
        else if (0 == (ctl & 0x40))
        {
            count = m_input.ReadByte() | ((ctl & 0xF) << 8);
            switch ((ctl >> 4) & 3)
            {
            case 0:
                count += 2;
                FillBytes (dst, (byte)m_input.ReadByte(), count);
                break;
            case 1:
                ++count;
                Binary.CopyOverlapped (m_output, dst-m_stride, dst, count);
                break;
            case 2:
                ++count;
                Binary.CopyOverlapped (m_output, dst-2*m_stride, dst, count);
                break;
            case 3:
                ++count;
                Binary.CopyOverlapped (m_output, dst-4*m_stride, dst, count);
                break;
            }
        }
        else if (0 == (ctl & 0x30))
        {
            count = m_input.ReadByte() + ((ctl & 7) << 8) + 1;
            int x = m_pixel_size;
            if (0 != (ctl & 8))
                x *= 2;
            m_input.Read (m_output, dst, x);
            Binary.CopyOverlapped (m_output, dst, dst+x, count*x);
            ++count;
            count *= x;
        }
        else if (0 == (ctl & 0x20))
        {
            int offset = m_input.ReadByte() + ((ctl & 0xF) << 8) + 1;
            count = m_input.ReadByte() + 1;
            int src = dst - m_pixel_size * offset;
            count = Math.Min (count * m_pixel_size, m_output.Length - dst);
            Binary.CopyOverlapped (m_output, src, dst, count);
        }
        else
        {
            int offset = m_input.ReadByte() + ((ctl & 0xF) << 8) + 1;
            count = m_input.ReadByte() + 1;
            int src = dst - offset;
            Binary.CopyOverlapped (m_output, src, dst, count);
        }
        if (0 == count)
            throw new InvalidFormatException();
        dst += count;
    }
}
```

#### UnpackBytes

```csharp
private byte[] UnpackBytes ()
    int total = m_width * m_height;
    var output = new byte[total + m_width];
    int dst = 0;
    while ( dst < total )
    {
        int count;
        int next = m_input.ReadByte();
        if (-1 == next)
            break;
        if ((next & 0xF0) == 0xF0)
            throw new InvalidFormatException();

        if (0 == (next & 0x80))
        {
            if (0 != (next & 0x40))
            {
                count = (next & 0x3F) + 2;
                byte v = (byte)m_input.ReadByte();
                for (int i = 0; i < count; ++i)
                    output[dst+i] = v;
            }
            else
            {
                count = (next & 0x3F) + 1;
                if (count != m_input.Read (output, dst, count))
                    break;
            }
        }
        else if (0 == (next & 0x40))
        {
            count = m_input.ReadByte() | ((next & 0xF) << 8);
            switch ((next >> 4) & 3)
            {
            case 0:
                {
                    count += 2;
                    byte v = (byte)m_input.ReadByte();
                    for (int i = 0; i < count; ++i)
                        output[dst+i] = v;
                    break;
                }
            case 1:
                ++count;
                Binary.CopyOverlapped (output, dst-m_width, dst, count);
                break;
            case 2:
                ++count;
                Binary.CopyOverlapped (output, dst-2*m_width, dst, count);
                break;
            case 3:
                ++count;
                Binary.CopyOverlapped (output, dst-4*m_width, dst, count);
                break;
            }
        }
        else if (0 == (next & 0x20))
        {
            count = m_input.ReadByte() + ((next & 7) << 8) + 1;
            switch ((next >> 3) & 3)
            {
            case 0:
                m_input.Read (output, dst, 2);
                Binary.CopyOverlapped (output, dst, dst+2, count*2);
                ++count;
                count *= 2;
                break;
            case 1:
                m_input.Read (output, dst, 4);
                Binary.CopyOverlapped (output, dst, dst+4, count*4);
                ++count;
                count *= 4;
                break;
            case 2:
                m_input.Read (output, dst, 8);
                Binary.CopyOverlapped (output, dst, dst+8, count*8);
                ++count;
                count *= 8;
                break;
            case 3:
                m_input.Read (output, dst, 16);
                Binary.CopyOverlapped (output, dst, dst+16, count*16);
                ++count;
                count *= 16;
                break;
            }
        }
        else
        {
            int offset = m_input.ReadByte() | ((next & 0xF) << 8);
            count = m_input.ReadByte() + 1;
            int src = dst - 1 - offset;
            Binary.CopyOverlapped (output, src, dst, count);
        }
        dst += count;
    }
    return output;
}
```

#### FlipPixels

```csharp
private void FlipPixels () {

    var pixels = new byte[m_output.Length];
    int dst = 0;
    for (int src = m_stride * (m_height-1); src >= 0; src -= m_stride)
    {
        Buffer.BlockCopy (m_output, src, pixels, dst, m_stride);
        dst += m_stride;
    }
    m_output = pixels;
}
```

#### FillBytes

```csharp
void FillBytes (int dst, byte value, int count) {
    for (int i = 0; i < count; ++i)
        m_output[dst+i] = value;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Seraphim/ImageSeraph.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
