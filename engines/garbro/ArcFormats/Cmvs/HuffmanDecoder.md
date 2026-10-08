# Cmvs / HuffmanDecoder：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `HuffmanDecoder.GetBits` | `m_bits = LittleEndian.ToInt32 (m_input, m_src);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Purple.HuffmanDecoder

#### 状态与常量

```csharp
byte[]          m_input ;

byte[]          m_output ;

int             m_src ;

int             m_bits ;

int             m_bit_count ;

ushort[] lhs = new ushort[512] ;

ushort[] rhs = new ushort[512] ;

ushort token = 256 ;
```

#### HuffmanDecoder

```csharp
public HuffmanDecoder (byte[] src, int index, int length, byte[] dst) {
    m_input = src;
    m_output = dst;

    m_src = index;
    m_bit_count = 0;
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    int dst = 0;
    token = 256;
    ushort root = CreateTree();
    while (dst < m_output.Length)
    {
        ushort symbol = root;
        while (symbol >= 0x100)
        {
            if (0 != GetBits (1))
                symbol = rhs[symbol];
            else
                symbol = lhs[symbol];
        }
        m_output[dst++] = (byte)symbol;
    }
    return m_output;
}
```

#### CreateTree

```csharp
ushort CreateTree() {
    if (0 != GetBits (1))
    {
        ushort v = token++;
        if (v >= 511)
            throw new InvalidDataException ("Invalid compressed data");
        lhs[v] =  CreateTree();
        rhs[v] =  CreateTree();
        return v;
    }
    else
    {
        return (ushort)GetBits (8);
    }
}
```

#### GetBits

```csharp
int GetBits (int count) {
    int bits = 0;
    while (count --> 0)
    {
        if (0 == m_bit_count)
        {
            m_bits = LittleEndian.ToInt32 (m_input, m_src);
            m_src += 4;
            m_bit_count = 32;
        }
        bits = bits << 1 | (m_bits & 1);
        m_bits >>= 1;
        --m_bit_count;
    }
    return bits;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Cmvs/HuffmanDecoder.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
