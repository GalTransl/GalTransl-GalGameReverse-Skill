# ArcFormats / MD5：归档读取与解码

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

### GameRes.Cryptography.MD5Base

#### 状态与常量

```csharp
protected uint[]  m_state = new uint[4] ;

protected uint[]  m_buffer = new uint[16] ;

static readonly byte[,] ShiftsTable = {
    { 7, 12, 17, 22 }, { 5, 9, 14, 20 }, { 4, 11, 16, 23 }, { 6, 10, 15, 21 },
}

static readonly uint[] SineTable = {
    0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
    0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be, 0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
    0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa, 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
    0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed, 0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
    0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c, 0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
    0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
    0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
    0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1, 0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391,
}
```

#### Transform

```csharp
protected void Transform () {
    uint a = m_state[0];
    uint b = m_state[1];
    uint c = m_state[2];
    uint d = m_state[3];

    for (int i = 0; i < 64; ++i)
    {
        uint f;
        int g;
        if (i < 16)
        {
            f = d ^ (b & (c ^ d));
            g = i;
        }
        else if (i < 32)
        {
            f = c ^ (d & (b ^ c));
            g = (5 * i + 1) & 0xF;
        }
        else if (i < 48)
        {
            f = b ^ c ^ d;
            g = (3 * i + 5) & 0xF;
        }
        else
        {
            f = c ^ (b | ~d);
            g = (7 * i) & 0xF;
        }
        uint t = d;
        d = c;
        c = b;
        b += Binary.RotL (a + f + m_buffer[g] + SineTable[i], ShiftsTable[i>>4, i&3]);
        a = t;
    }

    m_state[0] += a;
    m_state[1] += b;
    m_state[2] += c;
    m_state[3] += d;
}
```

### GameRes.Cryptography.MD5

继承/接口：`MD5Base`。

#### 状态与常量

```csharp
long    m_bit_count ;

int     m_buf_pos ;

public uint[] State { get { return m_state; } }

static readonly byte[] Terminator = new byte[1] { 0x80 }

static readonly byte[] ZeroBytes = new byte[56] ;
```

#### MD5

```csharp
public MD5 () {
    Initialize();
}
```

#### Initialize

```csharp
public void Initialize () {
    m_state[0] = 0x67452301;
    m_state[1] = 0xEFCDAB89;
    m_state[2] = 0x98BADCFE;
    m_state[3] = 0x10325476;
    m_bit_count = 0;
    m_buf_pos = 0;
}
```

#### ComputeHash

```csharp
public byte[] ComputeHash (byte[] data) {
    return ComputeHash (data, 0, data.Length);
}
```

#### ComputeHash

```csharp
public byte[] ComputeHash (byte[] data, int pos, int count) {
    Initialize();
    Update (data, pos, count);
    Final();
    var hash = new byte[16];
    Buffer.BlockCopy (m_state, 0, hash, 0, 16);
    return hash;
}
```

#### Update

```csharp
public void Update (byte[] data, int pos, int count) {
    m_bit_count += (long)count << 3;

    if (m_buf_pos != 0)
    {
        int buf_count = 64 - m_buf_pos;
        if (count < buf_count)
        {
            Buffer.BlockCopy (data, pos, m_buffer, m_buf_pos, count);
            m_buf_pos += count;
            return;
        }
        Buffer.BlockCopy (data, pos, m_buffer, m_buf_pos, buf_count);
        Transform();
        pos += buf_count;
        count -= buf_count;
        m_buf_pos = 0;
    }

    while (count >= 64)
    {
        Buffer.BlockCopy (data, pos, m_buffer, 0, 64);
        Transform();
        pos += 64;
        count -= 64;
    }
    if (count > 0)
    {
        Buffer.BlockCopy (data, pos, m_buffer, 0, count);
        m_buf_pos += count;
    }
}
```

#### Final

```csharp
public void Final () {
    Buffer.BlockCopy (Terminator, 0, m_buffer, m_buf_pos++, 1);
    int buf_count = 64 - m_buf_pos;

    if (buf_count < 8)
    {
        Buffer.BlockCopy (ZeroBytes, 0, m_buffer, m_buf_pos, buf_count);
        Transform();
        m_buf_pos = 0;
        buf_count = 64;
    }
    Buffer.BlockCopy (ZeroBytes, 0, m_buffer, m_buf_pos, buf_count-8);
    m_buffer[14] = (uint)m_bit_count;
    m_buffer[15] = (uint)(m_bit_count >> 32);
    Transform();
    m_buf_pos = 0;

}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MD5.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
