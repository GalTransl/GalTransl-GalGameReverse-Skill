# RealLive / ImageG00：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `G00Reader.UnpackV1` | `int colors = LittleEndian.ToUInt16 (m_output, 0);` |
| `G00Reader.UnpackV2` | `int tile_count = m_input.ReadInt32();` |
| `G00Reader.UnpackV2` | `tile.X = m_input.ReadInt32();` |
| `G00Reader.UnpackV2` | `tile.Y = m_input.ReadInt32();` |
| `G00Reader.UnpackV2` | `if (input.ReadInt32() != tile_count)` |
| `G00Reader.UnpackV2` | `tiles[i].Offset = input.ReadUInt32();` |
| `G00Reader.UnpackV2` | `tiles[i].Length = input.ReadInt32();` |
| `G00Reader.UnpackV2` | `int tile_type = input.ReadUInt16();` |
| `G00Reader.UnpackV2` | `int count = input.ReadUInt16();` |
| `G00Reader.UnpackV2` | `int tile_x = input.ReadUInt16();` |
| `G00Reader.UnpackV2` | `int tile_y = input.ReadUInt16();` |
| `G00Reader.UnpackV2` | `input.ReadInt16();` |
| `G00Reader.UnpackV2` | `int tile_width = input.ReadUInt16();` |
| `G00Reader.UnpackV2` | `int tile_height = input.ReadUInt16();` |
| `G00Reader.LzDecompress` | `int packed_size = input.ReadInt32() - 8;` |
| `G00Reader.LzDecompress` | `int output_size = input.ReadInt32();` |
| `G00Reader.LzDecompress` | `bits = input.ReadUInt8() \| 0x100;` |
| `G00Reader.LzDecompress` | `int offset = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RealLive.G00MetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int  Type ;
```

### GameRes.Formats.RealLive.Tile

#### 状态与常量

```csharp
public int  X ;

public int  Y ;

public uint Offset ;

public int  Length ;
```

### GameRes.Formats.RealLive.G00Reader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

byte[]          m_output ;

int             m_width ;

int             m_height ;

int             m_type ;

public byte[]           Data { get { return m_output; } }

public PixelFormat    Format { get; private set; }

public BitmapPalette Palette { get; private set; }
```

#### G00Reader

```csharp
public G00Reader (IBinaryStream input, G00MetaData info) {
    m_width = (int)info.Width;
    m_height = (int)info.Height;
    m_type = info.Type;
    m_input = input;
}
```

#### Unpack

```csharp
public void Unpack () {
    m_input.Position = 5;
    if (0 == m_type)
        UnpackV0();
    else if (1 == m_type)
        UnpackV1();
    else
        UnpackV2();
}
```

#### UnpackV0

```csharp
void UnpackV0 () {
    m_output = LzDecompress (m_input, 1, 3);
    Format = PixelFormats.Bgr24;
}
```

#### UnpackV1

```csharp
void UnpackV1 () {
    m_output = LzDecompress (m_input, 2, 1);
    int colors = LittleEndian.ToUInt16 (m_output, 0);
    int src = 2;
    var palette = new Color[colors];
    for (int i = 0; i < colors; ++i)
    {
        palette[i] = Color.FromArgb (m_output[src+3], m_output[src+2], m_output[src+1], m_output[src]);
        src += 4;
    }
    Palette = new BitmapPalette (palette);
    Format = PixelFormats.Indexed8;
    Buffer.BlockCopy (m_output, src, m_output, 0, m_output.Length-src);
}
```

#### UnpackV2

```csharp
void UnpackV2 () {
    Format = PixelFormats.Bgra32;
    int tile_count = m_input.ReadInt32();
    var tiles = new List<Tile> (tile_count);
    for (int i = 0; i < tile_count; ++i)
    {
        var tile = new Tile();
        tile.X = m_input.ReadInt32();
        tile.Y = m_input.ReadInt32();
        tiles.Add (tile);
        m_input.Seek (0x10, SeekOrigin.Current);
    }
    using (var input = new BinMemoryStream (LzDecompress (m_input, 2, 1)))
    {
        if (input.ReadInt32() != tile_count)
            throw new InvalidFormatException();
        int dst_stride = m_width * 4;
        m_output = new byte[m_height * dst_stride];
        for (int i = 0; i < tile_count; ++i)
        {
            tiles[i].Offset = input.ReadUInt32();
            tiles[i].Length = input.ReadInt32();
        }
        var tile = tiles.First (t => t.Length != 0);

        input.Position = tile.Offset;
        int tile_type = input.ReadUInt16();
        int count = input.ReadUInt16();
        if (tile_type != 1)
            throw new InvalidFormatException();
        input.Seek (0x70, SeekOrigin.Current);
        for (int i = 0; i < count; ++i)
        {
            int tile_x = input.ReadUInt16();
            int tile_y = input.ReadUInt16();
            input.ReadInt16();
            int tile_width = input.ReadUInt16();
            int tile_height = input.ReadUInt16();
            input.Seek (0x52, SeekOrigin.Current);

            tile_x += tile.X;
            tile_y += tile.Y;
            if (tile_x + tile_width > m_width || tile_y + tile_height > m_height)
                throw new InvalidFormatException();
            int dst = tile_y * dst_stride + tile_x * 4;
            int tile_stride = tile_width * 4;
            for (int row = 0; row < tile_height; ++row)
            {
                input.Read (m_output, dst, tile_stride);
                dst += dst_stride;
            }
        }
    }
}
```

#### LzDecompress

```csharp
public static byte[] LzDecompress (IBinaryStream input, int min_count, int bytes_pp) {
    int packed_size = input.ReadInt32() - 8;
    int output_size = input.ReadInt32();
    var output = new byte[output_size];
    int dst = 0;
    int bits = 2;
    while (dst < output.Length && packed_size > 0)
    {
        bits >>= 1;
        if (1 == bits)
        {
            bits = input.ReadUInt8() | 0x100;
            --packed_size;
        }
        if (0 != (bits & 1))
        {
            input.Read (output, dst, bytes_pp);
            dst += bytes_pp;
            packed_size -= bytes_pp;
        }
        else
        {
            if (packed_size < 2)
                break;
            int offset = input.ReadUInt16();
            packed_size -= 2;
            int count = (offset & 0xF) + min_count;
            offset >>= 4;
            offset *= bytes_pp;
            count *= bytes_pp;
            Binary.CopyOverlapped (output, dst-offset, dst, count);
            dst += count;
        }
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RealLive/ImageG00.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
