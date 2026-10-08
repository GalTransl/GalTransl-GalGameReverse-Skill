# Macromedia / ImageBITD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BitdDecoder.UnpackScanLine` | `int b = m_input.ReadByte();` |
| `BitdDecoder.UnpackScanLine` | `b = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Macromedia.BitdMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public byte DepthType ;
```

### GameRes.Formats.Macromedia.BitdDecoder

继承/接口：`IImageDecoder`。

#### 状态与常量

```csharp
Stream  m_input ;

byte[]  m_output ;

int     m_width ;

int     m_height ;

int     m_stride ;

ImageMetaData   m_info ;

ImageData       m_image ;

BitmapPalette   m_palette ;

public Stream            Source => m_input;

public ImageFormat SourceFormat { get; private set; }

public ImageMetaData       Info => m_info;

public ImageData          Image => m_image ?? (m_image = GetImageData());

public PixelFormat       Format { get; private set; }

public byte[]      AlphaChannel { get; set; }

bool m_disposed = false ;
```

#### BitdDecoder

```csharp
public BitdDecoder (Stream input, BitdMetaData info, BitmapPalette palette) {
    m_input = input;
    m_info = info;
    m_width = info.iWidth;
    m_height = info.iHeight;
    m_stride = (m_width * m_info.BPP + 7) / 8;
    m_stride = (m_stride + 1) & ~1;
    m_output = new byte[m_stride * m_height];
    Format = info.BPP ==  2 ? PixelFormats.Indexed2
           : info.BPP ==  4 ? PixelFormats.Indexed4
           : info.BPP ==  8 ? PixelFormats.Indexed8
           : info.BPP == 16 ? PixelFormats.Bgr555
           :  info.DepthType == 0x87
           || info.DepthType == 0x8A ? PixelFormats.Bgra32
                                     : PixelFormats.Bgra32;
    m_palette = palette;
}
```

#### BitdDecoder

```csharp
private BitdDecoder (Stream input, ImageMetaData info, byte[] alpha_channel) {
    m_input = input;
    m_info = info;
    m_width = info.iWidth;
    m_height = info.iHeight;
    m_stride = (m_width * m_info.BPP + 7) / 8;
    Format = PixelFormats.Bgra32;
    AlphaChannel = alpha_channel;
    SourceFormat = ImageFormat.Jpeg;
}
```

#### ApplyAlphaChannel

```csharp
void ApplyAlphaChannel (byte[] alpha) {
    int alpha_stride = (m_width + 1) & ~1;
    int src = 0;
    int pdst = 3;
    for (int y = 0; y < m_height; ++y)
    {
        int dst = pdst;
        for (int x = 0; x < m_width; ++x)
        {
            m_output[dst] = alpha[src+x];
            dst += 4;
        }
        src += alpha_stride;
        pdst += m_stride;
    }
}
```

#### Unpack8bpp

```csharp
public byte[] Unpack8bpp () {
    for (int line = 0; line < m_output.Length; line += m_stride)
    {
        UnpackScanLine (m_output, line);
    }
    return m_output;
}
```

#### UnpackChannels

```csharp
public void UnpackChannels (int channels) {
    var scan_line = new byte[m_stride];
    for (int line = 0; line < m_output.Length; line += m_stride)
    {
        UnpackScanLine (scan_line, 0);
        int dst = line;
        for (int i = 0; i < m_width; ++i)
        {
            for (int src = m_width * (channels - 1); src >= 0; src -= m_width)
                m_output[dst++] = scan_line[i + src];
        }
    }
}
```

#### UnpackScanLine

```csharp
void UnpackScanLine (byte[] scan_line, int pos) {
    int x = 0;
    while (x < m_stride)
    {
        int b = m_input.ReadByte();
        if (-1 == b)
            break;
        int count = b;
        if (b > 0x7f)
            count = (byte)-(sbyte)b;
        ++count;
        if (x + count > m_stride)
            throw new InvalidFormatException();
        if (b > 0x7f)
        {
            b = m_input.ReadByte();
            if (-1 == b)
                throw new InvalidFormatException ("Unexpected end of file");
            for (int i = 0; i < count; ++i)
                scan_line[pos + x++] = (byte)b;
        }
        else
        {
            m_input.Read (scan_line, pos+x, count);
            x += count;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Macromedia/ImageBITD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
