# Qlie / QlieMersenneTwister：归档读取与解码

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

### GameRes.Formats.Qlie.QlieMersenneTwister

#### 状态与常量

```csharp
const uint  DefaultSeed     = 5489 ;

const int   StateLength     = 64 ;

const int   StateM          = 39 ;

const uint  MatrixA         = 0x9908B0DF ;

const uint  SignMask        = 0x80000000 ;

const uint  LowerMask       = 0x7FFFFFFF ;

const uint  TemperingMaskB  = 0x9C4F88E3 ;

const uint  TemperingMaskC  = 0xE7F70000 ;

uint[]  mt = new uint[StateLength] ;

int     mti = StateLength ;

uint[] mag01 = { 0, MatrixA }
```

#### QlieMersenneTwister

```csharp
public QlieMersenneTwister (uint seed) {
    SRand (seed);
}
```

#### SRand

```csharp
public void SRand (uint seed) {
    mt[0] = seed;
    for (mti = 1; mti < mt.Length; ++mti)
    {
        mt[mti] = (0x6611BC19u * (mt[mti-1] ^ (mt[mti-1] >> 30)) + (uint)mti);
    }
}
```

#### XorState

```csharp
public void XorState (byte[] hash) {
    int length = Math.Min (hash.Length / 4, StateLength);
    if (0 == length)
        return;
    unsafe
    {
        fixed (byte* hash_fixed = hash)
        {
            uint* hash32 = (uint*)hash_fixed;
            for (int i = 0; i < length; ++i)
                mt[i] ^= hash32[i];
        }
    }
}
```

#### Rand

```csharp
public uint Rand () {
    uint y;

    if (mti >= StateLength)
    {
        int kk;
        for (kk = 0; kk < StateLength - StateM; kk++)
        {
            y = (mt[kk] & SignMask) | (mt[kk+1] & LowerMask) >> 1;
            mt[kk] = mt[kk + StateM] ^ y ^ mag01[mt[kk+1] & 1];
        }
        for (; kk < StateLength-1; kk++)
        {
            y = (mt[kk] & SignMask) | (mt[kk+1] & LowerMask) >> 1;
            mt[kk] = mt[kk + StateM - StateLength] ^ y ^ mag01[mt[kk+1] & 1];
        }
        y = (mt[StateLength-1] & SignMask) | (mt[0] & LowerMask) >> 1;
        mt[StateLength-1] = mt[StateM-1] ^ y ^ mag01[mt[kk-1] & 1];

        mti = 0;
    }

    y = mt[mti++];
    y ^= y >> 11;
    y ^= (y << 7)  & TemperingMaskB;
    y ^= (y << 15) & TemperingMaskC;
    y ^= y >> 18;

    return y;
}
```

#### Rand64

```csharp
public ulong Rand64 () {

    ulong v = Rand();
    return v | (ulong)Rand() << 32;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Qlie/QlieMersenneTwister.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
