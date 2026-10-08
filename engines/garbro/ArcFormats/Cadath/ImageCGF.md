# Cadath / ImageCGF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CgfDecoder.Unpack` | `int channel_length = m_input.ReadInt32();` |
| `CgfDecoder.UnpackRle` | `int unpacked_length = LittleEndian.ToInt32 (input, 0);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Cadath.CgfMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int  Method ;
```

### GameRes.Formats.Cadath.CgfDecoder

#### 状态与常量

```csharp
IBinaryStream   m_input ;

CgfMetaData     m_info ;

byte[]          m_output ;

public PixelFormat Format { get; private set; }
```

#### CgfDecoder

```csharp
public CgfDecoder (IBinaryStream input, CgfMetaData info) {
    m_input = input;
    m_info = info;
    m_output = new byte[(int)m_info.Width * (int)m_info.Height * m_info.BPP / 8];
    if (32 == m_info.BPP)
        Format = PixelFormats.Bgra32;
    else
        Format = PixelFormats.Bgr24;
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    m_input.Position = 10;
    Action<byte[], int, byte[]> unpack_channel;
    if (1 == m_info.Method)
        unpack_channel = UnpackZLibV1;
    else if (2 == m_info.Method)
        unpack_channel = UnpackRle;
    else if (3 == m_info.Method)
        unpack_channel = UnpackZLibV3;
    else
        throw new NotSupportedException();
    int pixel_size = m_info.BPP / 8;
    var channel = new byte[m_info.Width * m_info.Height];
    byte[] buffer = null;
    for (int i = 0; i < pixel_size; ++i)
    {
        int channel_length = m_input.ReadInt32();
        if (channel_length < 0)
            throw new InvalidFormatException();
        if (null == buffer || channel_length > buffer.Length)
            buffer = new byte[channel_length];
        if (channel_length != m_input.Read (buffer, 0, channel_length))
            throw new EndOfStreamException();
        unpack_channel (buffer, channel_length, channel);
        int dst = i;
        for (int j = 0; j < channel.Length; ++j)
        {
            m_output[dst] = channel[j];
            dst += pixel_size;
        }
    }
    return m_output;
}
```

#### UnpackZLibV1

```csharp
void UnpackZLibV1 (byte[] input, int length, byte[] output) {
    Decrypt (input, length);
    UnpackZLib (input, length, output);
}
```

#### UnpackZLibV3

```csharp
void UnpackZLibV3 (byte[] input, int length, byte[] output) {
    UnpackZLib (input, length, output);
    byte px = 0;
    for (int i = 0; i < output.Length; ++i)
    {
        px ^= output[i];
        output[i] = px;
    }
}
```

#### UnpackZLib

```csharp
void UnpackZLib (byte[] input, int length, byte[] output) {
    using (var zinput = new MemoryStream (input, 4, length - 4))
    using (var z = new ZLibStream (zinput, CompressionMode.Decompress))
        z.Read (output, 0, output.Length);
}
```

#### UnpackRle

```csharp
void UnpackRle (byte[] input, int length, byte[] output) {
    int unpacked_length = LittleEndian.ToInt32 (input, 0);
    if (unpacked_length < 0 || unpacked_length > output.Length)
        throw new InvalidFormatException();
    int src = 4;
    int dst = 0;
    byte last_byte = 0;
    while (dst < unpacked_length)
    {
        byte b = input[src++];
        output[dst++] = b;
        if (b == last_byte)
        {
            int count = input[src++];
            for (int i = 0; i < count; ++i)
            {
                output[dst++] = b;
            }
        }
        last_byte = b;
    }
}
```

#### Decrypt

```csharp
unsafe internal static void Decrypt (byte[] data, int length) {
    if (length < 4)
        return;
    if (length > data.Length)
        throw new ArgumentOutOfRangeException ("length");
    fixed (byte* data8 = data)
    {
        uint* data32 = (uint*)data8;
        const uint seed = 0x3977141B;
        uint key = seed;
        for (int i = 0; i < length; i += 4)
        {
            key = Binary.RotL (key, 3);
            *data32++ ^= key;
            key += seed;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Cadath/ImageCGF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
