# Leaf / ArcAM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AM/Leaf` / `GameRes.Formats.Leaf.AmOpener` | `am` | `616d3030` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AmOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `AmOpener.TryOpen` | `byte key = file.View.ReadByte (8);` |
| `AmOpener.TryOpen` | `var index = file.View.ReadBytes (9, index_size);` |
| `AmOpener.TryOpen` | `entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_offset);` |
| `AmOpener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `AmStream.ReadByte` | `public override int ReadByte () {` |
| `AmStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Leaf.AmOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static byte[] DecryptTable = null ;
```

#### AmOpener

```csharp
public AmOpener () {
    Extensions = new string[] { "am" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (4);
    byte key = file.View.ReadByte (8);
    var index = file.View.ReadBytes (9, index_size);
    if (index.Length != index_size)
        return null;
    for (int i = 0; i < index.Length; ++i)
        index[i] ^= key;

    uint base_offset = 9 + index_size;
    int index_offset = 0;
    var dir = new List<Entry>();
    while (index_offset < index.Length)
    {
        int name_end = Array.IndexOf<byte> (index, 0, index_offset);
        if (-1 == name_end || name_end == index_offset)
            return null;
        var name = Encodings.cp932.GetString (index, index_offset, name_end-index_offset);
        index_offset = name_end+1;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_offset);
        entry.Size = LittleEndian.ToUInt32 (index, index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null == DecryptTable)
        return input;
    return new AmStream (input, DecryptTable);
}
```

### GameRes.Formats.Leaf.AmStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
byte[]  m_table ;
```

#### AmStream

```csharp
public AmStream (Stream input, byte[] table) : base (input) {
    m_table = table;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int pos = (int)Position;
    int read = BaseStream.Read (buffer, offset, count);
    for (int i = 0; i < read; ++i)
    {
        buffer[offset+i] ^= m_table[(pos+i) & 0xFFFF];
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = BaseStream.ReadByte();
    if (-1 != b)
        b ^= m_table[(Position-1) & 0xFFFF];
    return b;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Leaf/ArcAM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
