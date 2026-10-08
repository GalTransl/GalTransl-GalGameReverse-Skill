# ArcFormats / LzssStream：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LzssReader.Unpack` | `int ctl = m_input.ReadByte();` |
| `LzssReader.Unpack` | `byte b = m_input.ReadByte();` |
| `LzssReader.Unpack` | `int lo = m_input.ReadByte();` |
| `LzssReader.Unpack` | `int hi = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum LzssMode
    {
        Decompress,
        Compress,
    }
```

### GameRes.Compression.LzssStream

继承/接口：`PackedStream<LzssCoroutine>`。

#### 状态与常量

```csharp
public LzssSettings   Config { get { return Reader.Settings; } }
```

#### LzssStream

```csharp
public LzssStream (Stream input, LzssMode mode = LzssMode.Decompress, bool leave_open = false)
    : base (input, leave_open) {
    if (mode != LzssMode.Decompress)
        throw new NotImplementedException ("LzssStream compression not implemented");
}
```

### GameRes.Compression.LzssReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
BinaryReader    m_input ;

byte[]          m_output ;

int             m_size ;

public BinaryReader Input { get { return m_input; } }

public byte[]        Data { get { return m_output; } }

public int      FrameSize { get; set; }

public byte     FrameFill { get; set; }

public int   FrameInitPos { get; set; }

bool disposed = false ;
```

#### LzssReader

```csharp
public LzssReader (Stream input, int input_length, int output_length) {
    m_input = new BinaryReader (input, System.Text.Encoding.ASCII, true);
    m_output = new byte[output_length];
    m_size = input_length;

    FrameSize = 0x1000;
    FrameFill = 0;
    FrameInitPos = 0xfee;
}
```

#### Unpack

```csharp
public void Unpack () {
    int dst = 0;
    var frame = new byte[FrameSize];
    if (FrameFill != 0)
        for (int i = 0; i < frame.Length; ++i)
            frame[i] = FrameFill;
    int frame_pos = FrameInitPos;
    int frame_mask = FrameSize-1;
    int remaining = (int)m_size;
    while (remaining > 0)
    {
        int ctl = m_input.ReadByte();
        --remaining;
        for (int bit = 1; remaining > 0 && bit != 0x100; bit <<= 1)
        {
            if (dst >= m_output.Length)
                return;
            if (0 != (ctl & bit))
            {
                byte b = m_input.ReadByte();
                --remaining;
                frame[frame_pos++] = b;
                frame_pos &= frame_mask;
                m_output[dst++] = b;
            }
            else
            {
                if (remaining < 2)
                    return;
                int lo = m_input.ReadByte();
                int hi = m_input.ReadByte();
                remaining -= 2;
                int offset = (hi & 0xf0) << 4 | lo;
                for (int count = 3 + (hi & 0xF); count != 0; --count)
                {
                    if (dst >= m_output.Length)
                        break;
                    byte v = frame[offset++];
                    offset &= frame_mask;
                    frame[frame_pos++] = v;
                    frame_pos &= frame_mask;
                    m_output[dst++] = v;
                }
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/LzssStream.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
