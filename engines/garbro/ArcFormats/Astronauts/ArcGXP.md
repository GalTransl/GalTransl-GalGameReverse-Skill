# Astronauts / ArcGXP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GXP` / `GameRes.Formats.Astronauts.PakOpener` | `gxp` | `47585000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpenGxpFile` | `int count = file.View.ReadInt32 (0x18);` |
| `PakOpener.TryOpenGxpFile` | `long base_offset = file.View.ReadInt64 (0x28);` |
| `PakOpener.TryOpenGxpFile` | `var entry_length = file.View.ReadUInt32 (index_offset) ^ entry_key;` |
| `PakOpener.TryOpenGxpFile` | `int name_length = LittleEndian.ToInt32 (entry_buffer, 0xC) * 2;` |
| `PakOpener.TryOpenGxpFile` | `entry.Offset = base_offset + LittleEndian.ToInt64 (entry_buffer, 0x18);` |
| `PakOpener.TryOpenGxpFile` | `entry.Size   = LittleEndian.ToUInt32 (entry_buffer, 4);` |
| `PakOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Astronauts.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private bool UseNameAsKey = false ;

static readonly byte[] KnownKey = {
    0x40, 0x21, 0x28, 0x38, 0xA6, 0x6E, 0x43, 0xA5, 0x40, 0x21, 0x28, 0x38, 0xA6, 0x43, 0xA5, 0x64,
    0x3E, 0x65, 0x24, 0x20, 0x46, 0x6E, 0x74,
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    UseNameAsKey = false;
    ArcFile arc = TryOpenGxpFile(file);
    if(null == arc)
    {
        UseNameAsKey = true;
        arc = TryOpenGxpFile(file);
    }
    return arc;
}
```

#### TryOpenGxpFile

```csharp
private ArcFile TryOpenGxpFile (ArcView file) {
    int count = file.View.ReadInt32 (0x18);
    if (!IsSaneCount (count))
        return null;
    string arcname = Path.GetFileName(file.Name);
    byte[] arcname_bytes = Encoding.ASCII.GetBytes(arcname);
    long base_offset = file.View.ReadInt64 (0x28);
    uint entry_key = KnownKey[0] | (1u ^ KnownKey[1]) << 8 | (2u ^ KnownKey[2]) << 16 | (3u ^ KnownKey[3]) << 24;
    if (UseNameAsKey)
    {
        uint arcname_key = (uint)(arcname_bytes[0] | (arcname_bytes[1 % arcname_bytes.Length]) << 8 | (arcname_bytes[2 % arcname_bytes.Length]) << 16 | (arcname_bytes[3 % arcname_bytes.Length]) << 24);
        entry_key ^= arcname_key;
    }
    uint index_offset = 0x30;
    var entry_buffer = new byte[0x100];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry_length = file.View.ReadUInt32 (index_offset) ^ entry_key;
        if (entry_length < 0x20 || entry_length > 0x1000)
            return null;
        if (entry_length > entry_buffer.Length)
            entry_buffer = new byte[entry_length];
        if (entry_length != file.View.Read (index_offset, entry_buffer, 0, entry_length))
            return null;
        if (UseNameAsKey)
            Decrypt(entry_buffer, entry_length, arcname_bytes);
        else
            Decrypt(entry_buffer, entry_length);
        int name_length = LittleEndian.ToInt32 (entry_buffer, 0xC) * 2;
        if (name_length >= entry_length)
            return null;
        var name = Encoding.Unicode.GetString (entry_buffer, 0x20, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = base_offset + LittleEndian.ToInt64 (entry_buffer, 0x18);
        entry.Size   = LittleEndian.ToUInt32 (entry_buffer, 4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_length;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (UseNameAsKey)
    {
        string arcname = Path.GetFileName(arc.File.Name);
        byte[] arcname_bytes = Encoding.ASCII.GetBytes(arcname);
        Decrypt(data, entry.Size, arcname_bytes);
    }
    else
        Decrypt(data, entry.Size);
    return new BinMemoryStream (data, entry.Name);
}
```

#### Decrypt

```csharp
static void Decrypt (byte[] data, uint length, byte[] key=null) {
    for (uint i = 0; i < length; ++i)
    {
        byte xorkey = (byte)(i ^ KnownKey[i % KnownKey.Length]);
        if(null != key)
            xorkey ^= key[i % key.Length];
        data[i] ^= xorkey;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Astronauts/ArcGXP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
