# Uran / ArcNCL：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NCL` / `GameRes.Formats.Uran.NclOpener` | `ncl` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NclOpener.TryOpen` | `uint size = file.View.ReadUInt32 (offset);` |
| `NclOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (offset+4);` |
| `NclOpener.TryOpen` | `uint name_length = file.View.ReadUInt16 (offset+8);` |
| `NclOpener.TryOpen` | `var name = file.View.ReadString (offset+10, name_length);` |
| `NclOpener.TryOpen` | `uint header_size = file.View.ReadUInt16 (offset+4);` |
| `NclOpener.TryOpen` | `entry.Method = (byte)(file.View.ReadByte (offset) - 10);` |
| `NclSubStream.ReadByte` | `public override int ReadByte () {` |
| `NclSubStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Uran.NclEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte     Method ;
```

### GameRes.Formats.Uran.NclOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".ncl") || file.MaxOffset > uint.MaxValue)
        return null;
    long offset = 0;
    var dir = new List<Entry>();
    while (offset < file.MaxOffset)
    {
        uint size = file.View.ReadUInt32 (offset);
        if (0 == size)
            break;
        uint unpacked_size = file.View.ReadUInt32 (offset+4);
        uint name_length = file.View.ReadUInt16 (offset+8);
        if (0 == name_length || name_length > 0x100)
            return null;
        var name = file.View.ReadString (offset+10, name_length);
        offset += 10 + name_length;
        var entry = FormatCatalog.Instance.Create<NclEntry> (name);
        entry.Size = size;
        entry.UnpackedSize = unpacked_size;
        uint header_size = file.View.ReadUInt16 (offset+4);
        offset += 6 + header_size;
        entry.Offset = offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Method = (byte)(file.View.ReadByte (offset) - 10);
        entry.IsPacked = entry.Method != 1;
        entry.Offset++;
        entry.Size--;
        dir.Add (entry);
        offset += size;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    input = new NclSubStream (input, 10);
    var nclent = entry as NclEntry;
    if (nclent != null && nclent.IsPacked)
    {
        if (2 == nclent.Method)
            input = new ZLibStream (input, CompressionMode.Decompress);
        else if (3 == nclent.Method)
            input = new BZip2InputStream (input);
    }
    return input;
}
```

### GameRes.Formats.Uran.NclSubStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
private byte        m_key ;
```

#### NclSubStream

```csharp
public NclSubStream (Stream stream, byte key, bool leave_open = false)
    : base (stream, leave_open) {
    m_key = key;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int read = BaseStream.Read (buffer, offset, count);
    for (int i = 0; i < read; ++i)
    {
        buffer[offset+i] -= m_key;
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = BaseStream.ReadByte();
    if (-1 != b)
    {
        b = (byte)(b - m_key);
    }
    return b;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Uran/ArcNCL.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
