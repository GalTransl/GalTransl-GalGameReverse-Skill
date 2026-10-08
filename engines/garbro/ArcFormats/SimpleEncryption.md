# ArcFormats / SimpleEncryption：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ByteStringEncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `ByteStringEncryptedStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ByteTransform

继承/接口：`ICryptoTransform`。

#### 状态与常量

```csharp
const int BlockSize = 1 ;

public bool          CanReuseTransform { get { return true; } }

public bool CanTransformMultipleBlocks { get { return true; } }

public int              InputBlockSize { get { return BlockSize; } }

public int             OutputBlockSize { get { return BlockSize; } }
```

#### TransformBlock

```csharp
public abstract int TransformBlock (byte[] inputBuffer, int inputOffset, int inputCount,
byte[] outputBuffer, int outputOffset) ;
```

#### TransformFinalBlock

```csharp
public byte[] TransformFinalBlock (byte[] inputBuffer, int inputOffset, int inputCount) {
    byte[] outputBuffer = new byte[inputCount];
    TransformBlock (inputBuffer, inputOffset, inputCount, outputBuffer, 0);
    return outputBuffer;
}
```

### GameRes.Formats.NotTransform

继承/接口：`ByteTransform`。

#### TransformBlock

```csharp
public override int TransformBlock (byte[] inputBuffer, int inputOffset, int inputCount,
                                    byte[] outputBuffer, int outputOffset) {
    for (int i = 0; i < inputCount; ++i)
    {
        outputBuffer[outputOffset++] = (byte)~inputBuffer[inputOffset+i];
    }
    return inputCount;
}
```

### GameRes.Formats.ByteStringEncryptedStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
byte[]  m_key ;

int     m_base_pos ;
```

#### ByteStringEncryptedStream

```csharp
public ByteStringEncryptedStream (Stream main, long start_pos, byte[] key, bool leave_open = false)
    : base (main, leave_open) {
    m_key = key;
    m_base_pos = (int)(start_pos % m_key.Length);
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int start_pos = (int)((m_base_pos + BaseStream.Position) % m_key.Length);
    int read = BaseStream.Read (buffer, offset, count);
    for (int i = 0; i < read; ++i)
    {
        buffer[offset+i] ^= m_key[(start_pos + i) % m_key.Length];
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    long pos = BaseStream.Position;
    int b = BaseStream.ReadByte();
    if (-1 != b)
    {
        b ^= m_key[(m_base_pos + pos) % m_key.Length];
    }
    return b;
}
```

### GameRes.Formats.InputCryptoStream

继承/接口：`CryptoStream`。

#### 状态与常量

```csharp
ICryptoTransform    m_transform ;
```

#### InputCryptoStream

```csharp
public InputCryptoStream (Stream input, ICryptoTransform transform)
    : base (input, transform, CryptoStreamMode.Read) {
    m_transform = transform;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/SimpleEncryption.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
