# SplushWave / ImageSWG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SwgFormat.Decompress` | `byte hi = input.ReadUInt8();` |
| `SwgFormat.Decompress` | `byte lo = input.ReadUInt8();` |
| `SwgFormat.Decompress` | `if (0 == input.ReadByte())` |
| `SwgFormat.Decompress` | `hi = input.ReadUInt8();` |
| `SwgFormat.Decompress` | `lo = input.ReadUInt8();` |
| `SwgFormat.Decompress` | `output[pos] = input.ReadUInt8();` |
| `SwgFormat.Decompress` | `var row_sizes = input.ReadBytes (2 * height * channels);` |
| `SwgFormat.DecompressRow` | `byte ctl = input.ReadUInt8();` |
| `SwgFormat.DecompressRow` | `byte v = input.ReadUInt8();` |
| `SwgFormat.DecompressRow` | `output[dst] = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SplushWave.SwgFormat

继承/接口：`ImageFormat`。

#### 状态与常量

```csharp
static readonly byte[] PlaneMap = { 2, 1, 0, 3 }
```

#### Decompress

```csharp
bool Decompress (IBinaryStream input, byte[] output, int channels, int width, int height) {
    long start_pos = input.Position;
    byte hi = input.ReadUInt8();
    byte lo = input.ReadUInt8();
    if (hi != 0 || lo != 1)
    {
        input.Position = start_pos;
        int n = 0;
        for (int i = 0; i < channels; ++i)
        {
            if (0 == input.ReadByte())
                ++n;
        }
        if (n != channels)
            return false;
        input.Position = start_pos + 4;
        hi = input.ReadUInt8();
        lo = input.ReadUInt8();
    }
    int compress_method = lo | hi << 8;
    if (0 == compress_method)
    {
        for (int i = 0; i < channels; ++i)
        {
            int pos = i;
            int count = height * width;
            while (count --> 0)
            {
                output[pos] = input.ReadUInt8();
                pos += channels;
            }
        }
        return true;
    }
    if (compress_method != 1)
        return false;
    int stride = width * channels;
    var row_sizes = input.ReadBytes (2 * height * channels);
    int ctl_pos = 0;
    for (int c = 0; c < channels; ++c)
    for (int y = height - 1; y >= 0; --y)
    {
        int dst = stride * y + PlaneMap[c];
        int row_size = row_sizes[ctl_pos+1] | row_sizes[ctl_pos] << 8;
        ctl_pos += 2;
        DecompressRow (input, row_size, output, dst, channels);
    }
    return true;
}
```

#### DecompressRow

```csharp
internal static void DecompressRow (IBinaryStream input, int row_size, byte[] output, int dst, int step) {
    int x = 0;
    while (x < row_size)
    {
        byte ctl = input.ReadUInt8();
        if (ctl == 0)
        {
            byte v = input.ReadUInt8();
            x += 2;
            output[dst] = v;
            dst += step;
        }
        else if (ctl < 0x81u)
        {
            int count = ctl + 1;
            x += count + 1;
            while (count --> 0)
            {
                output[dst] = input.ReadUInt8();
                dst += step;
            }
        }
        else
        {
            byte v = input.ReadUInt8();
            x += 2;
            int count = 0x101 - ctl;
            while (count --> 0)
            {
                output[dst] = v;
                dst += step;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/SplushWave/ImageSWG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
