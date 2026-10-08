# Cri / BigEndianReader：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BigEndianReader.ReadByte` | `public byte ReadByte () {` |
| `BigEndianReader.ReadByte` | `return m_input.ReadByte();` |
| `BigEndianReader.ReadInt16` | `public short ReadInt16 () {` |
| `BigEndianReader.ReadInt16` | `return Binary.BigEndian (m_input.ReadInt16());` |
| `BigEndianReader.ReadUInt16` | `public ushort ReadUInt16 () {` |
| `BigEndianReader.ReadUInt16` | `return Binary.BigEndian (m_input.ReadUInt16());` |
| `BigEndianReader.ReadInt32` | `public int ReadInt32 () {` |
| `BigEndianReader.ReadInt32` | `return Binary.BigEndian (m_input.ReadInt32());` |
| `BigEndianReader.ReadUInt32` | `public uint ReadUInt32 () {` |
| `BigEndianReader.ReadUInt32` | `return Binary.BigEndian (m_input.ReadUInt32());` |
| `BigEndianReader.ReadInt64` | `public long ReadInt64 () {` |
| `BigEndianReader.ReadInt64` | `return Binary.BigEndian (m_input.ReadInt64());` |
| `BigEndianReader.ReadUInt64` | `public ulong ReadUInt64 () {` |
| `BigEndianReader.ReadUInt64` | `return Binary.BigEndian (m_input.ReadUInt64());` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Cri.BigEndianReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
BinaryReader    m_input ;

byte[]          m_buffer = new byte[8] ;

public long Position {
    get { return m_input.BaseStream.Position; }
    set { m_input.BaseStream.Position = value; }
}

public Stream BaseStream { get { return m_input.BaseStream; } }

bool _disposed = false ;
```

#### BigEndianReader

```csharp
public BigEndianReader (Stream input, Encoding enc, bool leave_open = false) {
    m_input = new BinaryReader (input, enc, leave_open);
}
```

#### Read

```csharp
public int Read (byte[] buffer, int index, int count) {
    return m_input.Read (buffer, index, count);
}
```

#### Skip

```csharp
public void Skip (int amount) {
    m_input.BaseStream.Seek (amount, SeekOrigin.Current);
}
```

#### ReadByte

```csharp
public byte ReadByte () {
    return m_input.ReadByte();
}
```

#### ReadSByte

```csharp
public sbyte ReadSByte () {
    return m_input.ReadSByte();
}
```

#### ReadInt16

```csharp
public short ReadInt16 () {
    return Binary.BigEndian (m_input.ReadInt16());
}
```

#### ReadUInt16

```csharp
public ushort ReadUInt16 () {
    return Binary.BigEndian (m_input.ReadUInt16());
}
```

#### ReadInt32

```csharp
public int ReadInt32 () {
    return Binary.BigEndian (m_input.ReadInt32());
}
```

#### ReadUInt32

```csharp
public uint ReadUInt32 () {
    return Binary.BigEndian (m_input.ReadUInt32());
}
```

#### ReadInt64

```csharp
public long ReadInt64 () {
    return Binary.BigEndian (m_input.ReadInt64());
}
```

#### ReadUInt64

```csharp
public ulong ReadUInt64 () {
    return Binary.BigEndian (m_input.ReadUInt64());
}
```

#### ReadSingle

```csharp
public float ReadSingle () {
    if (4 != m_input.Read (m_buffer, 0, 4))
        throw new EndOfStreamException();
    if (BitConverter.IsLittleEndian)
        Array.Reverse (m_buffer, 0, 4);
    return BitConverter.ToSingle (m_buffer, 0);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Cri/BigEndianReader.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
