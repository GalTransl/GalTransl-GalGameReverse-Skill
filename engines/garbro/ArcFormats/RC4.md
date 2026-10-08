# ArcFormats / RC4：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Cryptography.Rc4Transform

继承/接口：`ICryptoTransform`。

#### 状态与常量

```csharp
private const int StateLength = 256 ;

private const int BlockSize = 1 ;

private byte[]	m_state ;

private int		m_x ;

private int		m_y ;

public bool          CanReuseTransform { get { return false; } }

public bool CanTransformMultipleBlocks { get { return true; } }

public int              InputBlockSize { get { return BlockSize; } }

public int             OutputBlockSize { get { return BlockSize; } }

public byte[]                    State { get { return m_state; } }
```

#### Rc4Transform

```csharp
public Rc4Transform (byte[] key) {
    m_x = 0;
    m_y = 0;

    m_state = new byte[StateLength];
    for (int i = 0; i < StateLength; ++i)
    {
        m_state[i] = (byte)i;
    }

    int s = 0;
    for (int i = 0; i < StateLength; ++i)
    {
        s = (key[i % key.Length] + m_state[i] + s) & 0xFF;
        byte t = m_state[i];
        m_state[i] = m_state[s];
        m_state[s] = t;
    }
}
```

#### NextByte

```csharp
public byte NextByte () {
    m_x = (m_x + 1) & 0xFF;
    byte a = m_state[m_x];
    m_y = (m_y + a) & 0xFF;
    byte b = m_state[m_y];
    m_state[m_x] = b;
    m_state[m_y] = a;
    return m_state[(a + b) & 0xFF];
}
```

#### GenerateBlock

```csharp
public byte[] GenerateBlock (int length) {
    var block = new byte[length];
    for (int i = 0; i < block.Length; ++i)
        block[i] = NextByte();
    return block;
}
```

#### TransformBlock

```csharp
public int TransformBlock (byte[] inBuf, int inOffset, int inCount, byte[] outBuf, int outOffset) {
    for (int i = 0; i < inCount; i++)
    {
        outBuf[i+outOffset] = (byte)(inBuf[i + inOffset] ^ NextByte());
    }
    return inCount;
}
```

#### TransformFinalBlock

```csharp
public byte[] TransformFinalBlock (byte[] inBuf, int inOffset, int inCount) {
    byte[] output = new byte[inCount];
    TransformBlock (inBuf, inOffset, inCount, output, 0);
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RC4.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
