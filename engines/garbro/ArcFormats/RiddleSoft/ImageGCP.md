# RiddleSoft / ImageGCP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CmpReader.GetBits` | `int b = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Riddle.CmpReader

#### 状态与常量

```csharp
Stream          m_input ;

byte[]          m_output ;

int             m_src_count = 0 ;

int             m_src_total ;

public byte[] Data { get { return m_output; } }

int m_bits = 0 ;

int m_cached_bits = 0 ;
```

#### CmpReader

```csharp
public CmpReader (Stream file, int src_size, int dst_size) {
    m_input = file;
    m_output = new byte[dst_size];
    m_src_total = src_size;
}
```

#### Unpack

```csharp
public void Unpack () {
    int dst = 0;
    var shift = new byte[0x800];
    int edi = 0x7ef;
    for (int i = 0; i < edi; ++i)
        shift[i] = 0x20;
    while (dst < m_output.Length)
    {
        int bit = GetBits (1);
        if (-1 == bit)
            break;
        if (1 == bit)
        {
            int data = GetBits (8);
            if (-1 == data)
                break;
            m_output[dst++] = (byte)data;
            shift[edi++] = (byte)data;
            edi &= 0x7ff;
        }
        else
        {
            int offset = GetBits (11);
            if (-1 == offset)
                break;
            int count = GetBits (4);
            if (-1 == count)
                break;
            count += 2;
            for (int i = 0; i < count; ++i)
            {
                byte data = shift[(offset + i) & 0x7ff];
                m_output[dst++] = data;
                shift[edi++] = data;
                edi &= 0x7ff;
                if (m_output.Length == dst)
                    return;
            }
        }
    }
}
```

#### GetBits

```csharp
int GetBits (int count) {
    while (m_cached_bits < count)
    {
        if (m_src_count++ >= m_src_total)
            return -1;
        int b = m_input.ReadByte();
        if (-1 == b)
            return -1;
        m_bits = (m_bits << 8) | b;
        m_cached_bits += 8;
    }
    int mask = (1 << count) - 1;
    m_cached_bits -= count;
    return (m_bits >> m_cached_bits) & mask;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RiddleSoft/ImageGCP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
