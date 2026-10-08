# Primel / RC6：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `RC6.Encrypt` | `uint a = LittleEndian.ToUInt32 (inBuffer, offset);` |
| `RC6.Encrypt` | `uint b = LittleEndian.ToUInt32 (inBuffer, offset+4);` |
| `RC6.Encrypt` | `uint c = LittleEndian.ToUInt32 (inBuffer, offset+8);` |
| `RC6.Encrypt` | `uint d = LittleEndian.ToUInt32 (inBuffer, offset+12);` |
| `RC6.Decrypt` | `uint a = LittleEndian.ToUInt32 (inBuffer, offset);` |
| `RC6.Decrypt` | `uint b = LittleEndian.ToUInt32 (inBuffer, offset+4);` |
| `RC6.Decrypt` | `uint c = LittleEndian.ToUInt32 (inBuffer, offset+8);` |
| `RC6.Decrypt` | `uint d = LittleEndian.ToUInt32 (inBuffer, offset+12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Cryptography.RC6

继承/接口：`ICryptoTransform`。

#### 状态与常量

```csharp
internal const int BlockSize = 16 ;

internal const int DefaultRounds = 20 ;

public bool CanTransformMultipleBlocks { get { return true; } }

public bool          CanReuseTransform { get { return false; } }

public int              InputBlockSize { get { return BlockSize; } }

public int             OutputBlockSize { get { return BlockSize; } }

uint[]      m_state ;

byte[]      m_iv ;

const uint  P = 0xB7E15163 ;

const uint  Q = 0x9E3779B9 ;
```

#### RC6

```csharp
public RC6 (byte[] key, byte[] iv) {
    m_state = new uint[2 * (DefaultRounds + 2)];
    int key_length = Math.Max ((key.Length + 3) / 4, 1);
    var key_copy = new uint[key_length];
    Buffer.BlockCopy (key, 0, key_copy, 0, key.Length);

    m_state[0] = P;
    for (int i = 1; i < m_state.Length; ++i)
        m_state[i] = m_state[i-1] + Q;

    uint a = 0, b = 0;
    int n = 3 * Math.Max (m_state.Length, key_length);
    for (int h = 0; h < n; ++h)
    {
        a = m_state[h % m_state.Length] = Binary.RotL (m_state[h % m_state.Length] + a + b, 3);
        b = key_copy[h % key_length] = Binary.RotL ((key_copy[h % key_length] + a + b), (int)(a + b));
    }

    m_iv = new byte[BlockSize];
    if (iv != null)
        Buffer.BlockCopy (iv, 0, m_iv, 0, Math.Min (iv.Length, BlockSize));
}
```

#### TransformBlock

```csharp
public int TransformBlock (byte[] inBuffer, int offset, int count, byte[] outBuffer, int outOffset) {
    int out_count = count / BlockSize;
    for (int i = 0; i < out_count; ++i)
    {

        Encrypt (m_iv, 0, outBuffer, outOffset);
        for (int j = 0; j < BlockSize; ++j)
        {
            byte b = inBuffer[offset++];
            outBuffer[outOffset++] ^= b;
            m_iv[j] = b;
        }
    }
    return out_count * BlockSize;
}
```

#### TransformFinalBlock

```csharp
public byte[] TransformFinalBlock (byte[] inBuffer, int offset, int count) {
    if (count < BlockSize)
        return new ArraySegment<byte> (inBuffer, offset, count).ToArray();
    var output = new byte[count];
    int tail = count / BlockSize * BlockSize;
    count -= TransformBlock (inBuffer, offset, count, output, 0);
    if (count > 0)
        Buffer.BlockCopy (inBuffer, offset+tail, output, tail, count);
    return output;
}
```

#### Encrypt

```csharp
private void Encrypt (byte[] inBuffer, int offset, byte[] outBuffer, int outOffset) {
    uint a = LittleEndian.ToUInt32 (inBuffer, offset);
    uint b = LittleEndian.ToUInt32 (inBuffer, offset+4);
    uint c = LittleEndian.ToUInt32 (inBuffer, offset+8);
    uint d = LittleEndian.ToUInt32 (inBuffer, offset+12);

    b += m_state[0];
    d += m_state[1];
    int sptr = 2;

    for (int i = 0; i < DefaultRounds; ++i)
    {
        uint t, u;
        t = Binary.RotL (b * (2 * b + 1), 5);
        u = Binary.RotL (d * (2 * d + 1), 5);
        a = Binary.RotL (a ^ t, (int)u) + m_state[sptr++];
        c = Binary.RotL (c ^ u, (int)t) + m_state[sptr++];
        t = a;
        a = b;
        b = c;
        c = d;
        d = t;
    }
    a += m_state[sptr];
    c += m_state[sptr+1];

    LittleEndian.Pack (a, outBuffer, outOffset);
    LittleEndian.Pack (b, outBuffer, outOffset+4);
    LittleEndian.Pack (c, outBuffer, outOffset+8);
    LittleEndian.Pack (d, outBuffer, outOffset+12);
}
```

#### Decrypt

```csharp
private void Decrypt (byte[] inBuffer, int offset, byte[] outBuffer, int outOffset) {
    uint a = LittleEndian.ToUInt32 (inBuffer, offset);
    uint b = LittleEndian.ToUInt32 (inBuffer, offset+4);
    uint c = LittleEndian.ToUInt32 (inBuffer, offset+8);
    uint d = LittleEndian.ToUInt32 (inBuffer, offset+12);

    int sptr = m_state.Length - 2;
    c -= m_state[sptr+1];
    a -= m_state[sptr];

    for (int i = 0; i < DefaultRounds; ++i)
    {
        uint t, u;
        sptr -= 2;
        t = a;
        a = d;
        d = c;
        c = b;
        b = t;
        u = Binary.RotL (d*(2*d+1), 5);
        t = Binary.RotL (b*(2*b+1), 5);
        c = Binary.RotR (c-m_state[sptr+1], (int)t) ^ u;
        a = Binary.RotR (a-m_state[sptr  ], (int)u) ^ t;
    }
    d -= m_state[1];
    b -= m_state[0];

    LittleEndian.Pack (a, outBuffer, outOffset);
    LittleEndian.Pack (b, outBuffer, outOffset+4);
    LittleEndian.Pack (c, outBuffer, outOffset+8);
    LittleEndian.Pack (d, outBuffer, outOffset+12);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Primel/RC6.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
