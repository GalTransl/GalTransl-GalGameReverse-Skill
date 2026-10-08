# AZSys / FastMersenneTwister：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

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

### GameRes.Utility.FastMersenneTwister

#### 状态与常量

```csharp
const int MEXP  = 19937 ;

const int N     = MEXP / 128 + 1 ;

const int N32   = N * 4 ;

const int POS1	= 122 ;

const int SL1	= 18 ;

const int SL2	= 1 ;

const int SR1	= 11 ;

const int SR2	= 1 ;

const uint MSK1	= 0xdfffffefU ;

const uint MSK2	= 0xddfecb7fU ;

const uint MSK3	= 0xbffaffffU ;

const uint MSK4	= 0xbffffff6U ;

const uint PARITY1	= 0x00000001U ;

const uint PARITY2	= 0x00000000U ;

const uint PARITY3	= 0x00000000U ;

const uint PARITY4	= 0x13c9e684U ;

uint[,]     m_state = new uint[N,4] ;

int         m_idx ;

static readonly uint[] s_parity = { PARITY1, PARITY2, PARITY3, PARITY4 }
```

#### FastMersenneTwister

```csharp
public FastMersenneTwister (uint seed) {
    SRand (seed);
}
```

#### SRand

```csharp
public void SRand (uint seed) {
    uint prev = m_state[0,0] = seed;
    for (int i = 1; i < N32; i++)
    {
        int p = i >> 2;
        int k = i & 3;
        prev = (uint)(1812433253UL * (prev ^ (prev >> 30)) + (uint)i);
        m_state[p,k] = prev;
    }
    m_idx = N32;
    period_certification();
}
```

#### GetRand32

```csharp
public uint GetRand32 () {
    if (m_idx >= N32)
    {
        sfmt_gen_rand_all();
        m_idx = 0;
    }
    uint r = m_state[m_idx >> 2, m_idx & 3];
    m_idx++;
    return r;
}
```

#### sfmt_gen_rand_all

```csharp
void sfmt_gen_rand_all () {
    int i;
    int r1 = N - 2;
    int r2 = N - 1;
    for (i = 0; i < N - POS1; i++)
    {
        do_recursion (i, i, i + POS1, r1, r2);
        r1 = r2;
        r2 = i;
    }
    for (; i < N; i++)
    {
        do_recursion (i, i, i + POS1 - N, r1, r2);
        r1 = r2;
        r2 = i;
    }
}
```

#### do_recursion

```csharp
void do_recursion (int r, int a, int b, int c, int d) {
    var x = new uint[4];
    var y = new uint[4];
    lshift128 (x, a, SL2);
    rshift128 (y, c, SR2);
    m_state[r,0] = m_state[a,0] ^ x[0] ^ ((m_state[b,0] >> SR1) & MSK1)
                                ^ y[0] ^ (m_state[d,0] << SL1);
    m_state[r,1] = m_state[a,1] ^ x[1] ^ ((m_state[b,1] >> SR1) & MSK2)
                                ^ y[1] ^ (m_state[d,1] << SL1);
    m_state[r,2] = m_state[a,2] ^ x[2] ^ ((m_state[b,2] >> SR1) & MSK3)
                                ^ y[2] ^ (m_state[d,2] << SL1);
    m_state[r,3] = m_state[a,3] ^ x[3] ^ ((m_state[b,3] >> SR1) & MSK4)
                                ^ y[3] ^ (m_state[d,3] << SL1);
}
```

#### period_certification

```csharp
void period_certification () {
    uint inner = 0;
    int i;

    for (i = 0; i < 4; i++)
        inner ^= m_state[0,i] & s_parity[i];
    for (i = 16; i > 0; i >>= 1)
        inner ^= inner >> i;
    inner &= 1;

    if (inner == 1)
        return;

    for (i = 0; i < 4; i++)
    {
        uint work = 1;
        for (int j = 0; j < 32; j++)
        {
            if ((work & s_parity[i]) != 0)
            {
                m_state[0,i] ^= work;
                return;
            }
            work = work << 1;
        }
    }
}
```

#### lshift128

```csharp
void lshift128 (uint[] result, int idx, int shift) {
    ulong th = ((ulong)m_state[idx,3] << 32) | ((ulong)m_state[idx,2]);
    ulong tl = ((ulong)m_state[idx,1] << 32) | ((ulong)m_state[idx,0]);

    ulong oh = th << (shift * 8);
    ulong ol = tl << (shift * 8);
    oh |= tl >> (64 - shift * 8);
    result[1] = (uint)(ol >> 32);
    result[0] = (uint)ol;
    result[3] = (uint)(oh >> 32);
    result[2] = (uint)oh;
}
```

#### rshift128

```csharp
void rshift128 (uint[] result, int idx, int shift) {
    ulong th = ((ulong)m_state[idx,3] << 32) | ((ulong)m_state[idx,2]);
    ulong tl = ((ulong)m_state[idx,1] << 32) | ((ulong)m_state[idx,0]);

    ulong oh = th >> (shift * 8);
    ulong ol = tl >> (shift * 8);
    ol |= th << (64 - shift * 8);
    result[1] = (uint)(ol >> 32);
    result[0] = (uint)ol;
    result[3] = (uint)(oh >> 32);
    result[2] = (uint)oh;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AZSys/FastMersenneTwister.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
