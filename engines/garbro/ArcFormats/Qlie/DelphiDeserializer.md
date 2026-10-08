# Qlie / DelphiDeserializer：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DelphiDeserializer.Deserialize` | `if (m_input.ReadUInt32() != 0x30465054)` |
| `DelphiDeserializer.DeserializeNode` | `int type_len = m_input.ReadByte();` |
| `DelphiDeserializer.DeserializeNode` | `node.Type = ReadString (type_len);` |
| `DelphiDeserializer.DeserializeNode` | `node.Name = ReadString();` |
| `DelphiDeserializer.DeserializeNode` | `while ((key_length = m_input.ReadUInt8()) > 0)` |
| `DelphiDeserializer.DeserializeNode` | `var key = ReadString (key_length);` |
| `DelphiDeserializer.ReadValue` | `int type = m_input.ReadUInt8();` |
| `DelphiDeserializer.ReadValue` | `case 2:  return (int)m_input.ReadUInt8();` |
| `DelphiDeserializer.ReadValue` | `case 3:  return (int)m_input.ReadUInt16();` |
| `DelphiDeserializer.ReadValue` | `case 7:  return ReadString();` |
| `DelphiDeserializer.ReadString` | `string ReadString () {` |
| `DelphiDeserializer.ReadString` | `return ReadString (m_input.ReadUInt8());` |
| `DelphiDeserializer.ReadString` | `string ReadString (int length) {` |
| `DelphiDeserializer.ReadString` | `return m_input.ReadCString (length, Encoding);` |
| `DelphiDeserializer.ReadUnicodeString` | `int length = m_input.ReadInt32();` |
| `DelphiDeserializer.ReadUnicodeString` | `var bytes = m_input.ReadBytes (length * 2);` |
| `DelphiDeserializer.ReadByteString` | `int length = m_input.ReadInt32();` |
| `DelphiDeserializer.ReadByteString` | `return m_input.ReadBytes (length);` |
| `DelphiDeserializer.ReadStringArray` | `while ((length = m_input.ReadUInt8()) > 0)` |
| `DelphiDeserializer.ReadStringArray` | `list.Add (ReadString (length));` |
| `DelphiDeserializer.ReadLongDouble` | `return m_input.ReadBytes (10);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Borland.DelphiDeserializer

#### 状态与常量

```csharp
IBinaryStream   m_input ;

public Encoding Encoding { get; set; }
```

#### DelphiDeserializer

```csharp
public DelphiDeserializer (IBinaryStream input) {
    m_input = input;
    Encoding = Encodings.cp932;
}
```

#### Deserialize

```csharp
public DelphiObject Deserialize () {
    if (m_input.ReadUInt32() != 0x30465054)
        return null;
    return DeserializeNode();
}
```

#### DeserializeNode

```csharp
DelphiObject DeserializeNode () {
    int type_len = m_input.ReadByte();
    if (type_len <= 0)
        return null;
    var node = new DelphiObject();
    node.Type = ReadString (type_len);
    node.Name = ReadString();
    int key_length;
    while ((key_length = m_input.ReadUInt8()) > 0)
    {
        var key = ReadString (key_length);
        node.Props[key] = ReadValue();
    }
    DelphiObject child;
    while ((child = DeserializeNode()) != null)
    {
        node.Contents.Add (child);
    }
    return node;
}
```

#### ReadValue

```csharp
object ReadValue () {
    int type = m_input.ReadUInt8();
    switch (type)
    {
    case 2:  return (int)m_input.ReadUInt8();
    case 3:  return (int)m_input.ReadUInt16();
    case 5:  return ReadLongDouble();
    case 6:
    case 7:  return ReadString();
    case 8:
    case 9:  return true;
    case 10: return ReadByteString();
    case 11: return ReadStringArray();
    case 18: return ReadUnicodeString();
    default: throw new System.NotImplementedException();
    }
}
```

#### ReadString

```csharp
string ReadString () {
    return ReadString (m_input.ReadUInt8());
}
```

#### ReadString

```csharp
string ReadString (int length) {
    return m_input.ReadCString (length, Encoding);
}
```

#### ReadUnicodeString

```csharp
string ReadUnicodeString () {
    int length = m_input.ReadInt32();
    if (length < 0)
        throw new InvalidFormatException();
    if (0 == length)
        return "";
    var bytes = m_input.ReadBytes (length * 2);
    return Encoding.Unicode.GetString (bytes);
}
```

#### ReadByteString

```csharp
byte[] ReadByteString () {
    int length = m_input.ReadInt32();
    if (length < 0)
        throw new InvalidFormatException();
    if (0 == length)
        return new byte[0];
    return m_input.ReadBytes (length);
}
```

#### ReadStringArray

```csharp
IList<string> ReadStringArray () {
    var list = new List<string>();
    int length;
    while ((length = m_input.ReadUInt8()) > 0)
    {
        list.Add (ReadString (length));
    }
    return list;
}
```

#### ReadLongDouble

```csharp
object ReadLongDouble () {
    return m_input.ReadBytes (10);
}
```

### GameRes.Formats.Borland.DelphiObject

#### 状态与常量

```csharp
public string       Type ;

public string       Name ;

public IDictionary  Props = new Hashtable() ;

public IList<DelphiObject> Contents = new List<DelphiObject>() ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Qlie/DelphiDeserializer.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
