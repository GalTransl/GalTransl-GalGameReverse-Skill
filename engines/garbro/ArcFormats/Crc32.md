# ArcFormats / Crc32：归档读取与解码

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

### GameRes.Utility.Crc32Normal

继承/接口：`ICheckSum`。

#### 状态与常量

```csharp
private static readonly uint[] crc_table = InitializeTable() ;

public static uint[] Table { get { return crc_table; } }

private uint m_crc = 0xffffffff ;

public  uint Value { get { return ~m_crc; } }
```

#### InitializeTable

```csharp
private static uint[] InitializeTable () {
    const uint polynomial = 0x04C11DB7;
    var table = new uint[256];
    for (uint n = 0; n < 256; n++)
    {
        uint c = n << 24;
        for (int k = 0; k < 8; k++)
        {
            if (0 != (c & 0x80000000u))
                c = polynomial ^ (c << 1);
            else
                c <<= 1;
        }
        table[n] = c;
    }
    return table;
}
```

#### UpdateCrc

```csharp
public static uint UpdateCrc (uint init_crc, byte[] data, int pos, int length) {
    uint c = init_crc;
    for (int n = 0; n < length; n++)
        c = crc_table[(c >> 24) ^ data[pos+n]] ^ (c << 8);
    return c;
}
```

#### Compute

```csharp
public static uint Compute (byte[] buf, int pos, int len) {
    return ~UpdateCrc (0xffffffff, buf, pos, len);
}
```

#### Update

```csharp
public void Update (byte[] buf, int pos, int len) {
    m_crc = UpdateCrc (m_crc, buf, pos, len);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Crc32.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
