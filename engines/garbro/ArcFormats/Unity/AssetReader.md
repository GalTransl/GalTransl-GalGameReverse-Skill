# Unity / AssetReader：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AssetReader.SetupReaders` | `ReadUInt16 = () => m_input.ReadUInt16();` |
| `AssetReader.SetupReaders` | `ReadUInt32 = () => m_input.ReadUInt32();` |
| `AssetReader.SetupReaders` | `ReadInt16 = () => m_input.ReadInt16();` |
| `AssetReader.SetupReaders` | `ReadInt32 = () => m_input.ReadInt32();` |
| `AssetReader.SetupReaders` | `ReadInt64 = () => m_input.ReadInt64();` |
| `AssetReader.SetupReaders` | `ReadUInt16 = () => Binary.BigEndian (m_input.ReadUInt16());` |
| `AssetReader.SetupReaders` | `ReadUInt32 = () => Binary.BigEndian (m_input.ReadUInt32());` |
| `AssetReader.SetupReaders` | `ReadInt16 = () => Binary.BigEndian (m_input.ReadInt16());` |
| `AssetReader.SetupReaders` | `ReadInt32 = () => Binary.BigEndian (m_input.ReadInt32());` |
| `AssetReader.SetupReaders` | `ReadInt64 = () => Binary.BigEndian (m_input.ReadInt64());` |
| `AssetReader.SetupReaders` | `ReadId = () => ReadInt32();` |
| `AssetReader.SetupReaders` | `ReadOffset = () => ReadUInt32();` |
| `AssetReader.SetupReadId` | `ReadId = () => ReadInt32();` |
| `AssetReader.ReadCString` | `public string ReadCString () {` |
| `AssetReader.ReadCString` | `return m_input.ReadCString (Encoding.UTF8);` |
| `AssetReader.ReadString` | `public string ReadString () {` |
| `AssetReader.ReadString` | `int length = ReadInt32();` |
| `AssetReader.ReadString` | `var bytes = ReadBytes (length);` |
| `AssetReader.ReadBytes` | `public byte[] ReadBytes (int length) {` |
| `AssetReader.ReadBytes` | `return m_input.ReadBytes (length);` |
| `AssetReader.ReadByte` | `public byte ReadByte () {` |
| `AssetReader.ReadByte` | `return m_input.ReadUInt8();` |
| `AssetReader.ReadBool` | `return ReadByte() != 0;` |
| `AssetReader.ReadFloat` | `buf.u = ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.AssetReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

int             m_format ;

const int MaxStringLength = 0x100000 ;

public Stream Source { get { return m_input.AsStream; } }

public int    Format { get { return m_format; } }

public long Position {
    get { return m_input.Position; }
    set { m_input.Position = value; }
}

public Action       Align ;

public Func<ushort> ReadUInt16 ;

public Func<short>  ReadInt16 ;

public Func<uint>   ReadUInt32 ;

public Func<int>    ReadInt32 ;

public Func<long>   ReadInt64 ;

public Func<long>   ReadId ;

public Func<long>   ReadOffset ;

bool _disposed = false ;
```

#### AssetReader

```csharp
public AssetReader (IBinaryStream input) {
    m_input = input;
    SetupReaders (0, false);
}
```

#### SetupReaders

```csharp
public void SetupReaders (Asset asset) {
    SetupReaders (asset.Format, asset.IsLittleEndian);
}
```

#### SetupReaders

```csharp
public void SetupReaders (int format, bool is_little_endian) {
    m_format = format;
    if (is_little_endian)
    {
        ReadUInt16 = () => m_input.ReadUInt16();
        ReadUInt32 = () => m_input.ReadUInt32();
        ReadInt16 = () => m_input.ReadInt16();
        ReadInt32 = () => m_input.ReadInt32();
        ReadInt64 = () => m_input.ReadInt64();
    }
    else
    {
        ReadUInt16 = () => Binary.BigEndian (m_input.ReadUInt16());
        ReadUInt32 = () => Binary.BigEndian (m_input.ReadUInt32());
        ReadInt16 = () => Binary.BigEndian (m_input.ReadInt16());
        ReadInt32 = () => Binary.BigEndian (m_input.ReadInt32());
        ReadInt64 = () => Binary.BigEndian (m_input.ReadInt64());
    }
    if (m_format >= 14 || m_format == 9)
    {
        Align = () => {
            long pos = m_input.Position;
            if (0 != (pos & 3))
                m_input.Position = (pos + 3) & ~3L;
        };
    }
    else
    {
        Align = () => {};
    }
    if (m_format >= 14)
        ReadId = ReadInt64;
    else
        ReadId = () => ReadInt32();
    if (m_format >= 22)
        ReadOffset = ReadInt64;
    else
        ReadOffset = () => ReadUInt32();
}
```

#### SetupReadId

```csharp
public void SetupReadId (bool long_ids) {
    if (long_ids)
        ReadId = ReadInt64;
    else
        ReadId = () => ReadInt32();
}
```

#### Skip

```csharp
public void Skip (int count) {
    m_input.Seek (count, SeekOrigin.Current);
}
```

#### Read

```csharp
public int Read (byte[] buffer, int offset, int count) {
    return m_input.Read (buffer, offset, count);
}
```

#### ReadCString

```csharp
public string ReadCString () {
    return m_input.ReadCString (Encoding.UTF8);
}
```

#### ReadString

```csharp
public string ReadString () {
    int length = ReadInt32();
    if (0 == length)
        return string.Empty;
    if (length < 0 || length > MaxStringLength)
        throw new InvalidFormatException();
    var bytes = ReadBytes (length);
    return Encoding.UTF8.GetString (bytes);
}
```

#### ReadBytes

```csharp
public byte[] ReadBytes (int length) {
    return m_input.ReadBytes (length);
}
```

#### ReadByte

```csharp
public byte ReadByte () {
    return m_input.ReadUInt8();
}
```

#### ReadBool

```csharp
public bool ReadBool () {
    return ReadByte() != 0;
}
```

#### ReadFloat

```csharp
public float ReadFloat () {
    var buf = new Union();
    buf.u = ReadUInt32();
    return buf.f;
}
```

### GameRes.Formats.Unity.AssetReader.Union

#### FieldOffset

```csharp
[FieldOffset (0)]
public uint u ;
```

#### FieldOffset

```csharp
[FieldOffset(0)]
public float f ;
```

## 配套算法与外部条件

- [ArcFormats/Unity/Asset.cs](Asset.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/AssetReader.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
