# ArcFormats / BitStream：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MsbBitStream.GetBits` | `int b = m_input.ReadByte();` |
| `LsbBitStream.GetBits` | `int b = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BitStream

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
protected Stream    m_input ;

private   bool      m_should_dispose ;

protected int       m_bits = 0 ;

protected int       m_cached_bits = 0 ;

public Stream  Input { get { return m_input; } }

public int CacheSize { get { return m_cached_bits; } }

bool m_disposed = false ;
```

#### BitStream

```csharp
protected BitStream (Stream file, bool leave_open) {
    m_input = file;
    m_should_dispose = !leave_open;
}
```

#### Reset

```csharp
public void Reset () {
    m_cached_bits = 0;
}
```

### GameRes.Formats.MsbBitStream

继承/接口：`BitStream`, `IBitStream`。

#### GetBits

```csharp
public int GetBits (int count) {
    Debug.Assert (count <= 24, "MsbBitStream does not support sequences longer than 24 bits");
    while (m_cached_bits < count)
    {
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

#### GetNextBit

```csharp
public int GetNextBit () {
    return GetBits (1);
}
```

### GameRes.Formats.LsbBitStream

继承/接口：`BitStream`, `IBitStream`。

#### GetBits

```csharp
public int GetBits (int count) {
    Debug.Assert (count <= 32, "LsbBitStream does not support sequences longer than 32 bits");
    int value;
    if (m_cached_bits >= count)
    {
        int mask = (1 << count) - 1;
        value = m_bits & mask;
        m_bits = (int)((uint)m_bits >> count);
        m_cached_bits -= count;
    }
    else
    {
        value = m_bits & ((1 << m_cached_bits) - 1);
        count -= m_cached_bits;
        int shift = m_cached_bits;
        m_cached_bits = 0;
        while (count >= 8)
        {
            int b = m_input.ReadByte();
            if (-1 == b)
                return -1;
            value |= b << shift;
            shift += 8;
            count -= 8;
        }
        if (count > 0)
        {
            int b = m_input.ReadByte();
            if (-1 == b)
                return -1;
            value |= (b & ((1 << count) - 1)) << shift;
            m_bits = b >> count;
            m_cached_bits = 8 - count;
        }
    }
    return value;
}
```

#### GetNextBit

```csharp
public int GetNextBit () {
    return GetBits (1);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/BitStream.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
