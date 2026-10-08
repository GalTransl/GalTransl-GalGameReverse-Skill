# RPGMaker / ArcRGSS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `RGSSAD` / `GameRes.Formats.RPGMaker.RgssOpener` | `rgss3a`, `rgss2a`, `rgssad` | `52475353` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `RgssOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "AD\0"))` |
| `RgssOpener.TryOpen` | `int version = file.View.ReadByte (7);` |
| `RgssOpener.ReadIndexV1` | `uint name_length = file.ReadUInt32() ^ key_gen.GetNext();` |
| `RgssOpener.ReadIndexV1` | `var name_bytes = file.ReadBytes ((int)name_length);` |
| `RgssOpener.ReadIndexV1` | `entry.Size   = file.ReadUInt32() ^ key_gen.GetNext();` |
| `RgssOpener.ReadIndexV3` | `uint key = file.ReadUInt32() * 9 + 3;` |
| `RgssOpener.ReadIndexV3` | `uint offset = file.ReadUInt32() ^ key;` |
| `RgssOpener.ReadIndexV3` | `uint size        = file.ReadUInt32() ^ key;` |
| `RgssOpener.ReadIndexV3` | `uint entry_key   = file.ReadUInt32() ^ key;` |
| `RgssOpener.ReadIndexV3` | `uint name_length = file.ReadUInt32() ^ key;` |
| `RgssOpener.ReadIndexV3` | `var name_bytes = file.ReadBytes ((int)name_length);` |
| `RgssOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (rent.Offset, rent.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RPGMaker.RgssOpener

继承/接口：`ArchiveFormat`。

#### RgssOpener

```csharp
public RgssOpener () {
    Extensions = new string[] { "rgss3a", "rgss2a", "rgssad" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "AD\0"))
        return null;
    int version = file.View.ReadByte (7);
    using (var index = file.CreateStream())
    {
        List<Entry> dir = null;
        if (3 == version)
            dir = ReadIndexV3 (index);
        else if (1 == version)
            dir = ReadIndexV1 (index);
        if (null == dir || 0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### ReadIndexV1

```csharp
List<Entry> ReadIndexV1 (IBinaryStream file) {
    var max_offset = file.Length;
    file.Position = 8;
    var key_gen = new KeyGenerator (0xDEADCAFE);
    var dir = new List<Entry>();
    while (file.PeekByte() != -1)
    {
        uint name_length = file.ReadUInt32() ^ key_gen.GetNext();
        var name_bytes = file.ReadBytes ((int)name_length);
        var name = DecryptName (name_bytes, key_gen);
        var entry = FormatCatalog.Instance.Create<RgssEntry> (name);
        entry.Size   = file.ReadUInt32() ^ key_gen.GetNext();
        entry.Offset = file.Position;
        entry.Key    = key_gen.Current;
        if (!entry.CheckPlacement (max_offset))
            return null;
        dir.Add (entry);
        file.Seek (entry.Size, SeekOrigin.Current);
    }
    return dir;
}
```

#### ReadIndexV3

```csharp
List<Entry> ReadIndexV3 (IBinaryStream file) {
    var max_offset = file.Length;
    file.Position = 8;
    uint key = file.ReadUInt32() * 9 + 3;
    var dir = new List<Entry>();
    while (file.PeekByte() != -1)
    {
        uint offset = file.ReadUInt32() ^ key;
        if (0 == offset)
            break;
        uint size        = file.ReadUInt32() ^ key;
        uint entry_key   = file.ReadUInt32() ^ key;
        uint name_length = file.ReadUInt32() ^ key;
        var name_bytes = file.ReadBytes ((int)name_length);
        var name = DecryptName (name_bytes, key);
        var entry = FormatCatalog.Instance.Create<RgssEntry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        entry.Key    = entry_key;
        if (!entry.CheckPlacement (max_offset))
            return null;
        dir.Add (entry);
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var rent = (RgssEntry)entry;
    var data = arc.File.View.ReadBytes (rent.Offset, rent.Size);
    var key_gen = new KeyGenerator (rent.Key);
    uint key = key_gen.GetNext();
    for (int i = 0; i < data.Length; )
    {
        data[i] ^= (byte)(key >> (i << 3));
        ++i;
        if (0 == (i & 3))
        {
            key = key_gen.GetNext();
        }
    }
    return new BinMemoryStream (data);
}
```

#### DecryptName

```csharp
string DecryptName (byte[] name, KeyGenerator key_gen) {
    for (int i = 0; i < name.Length; ++i)
    {
        name[i] ^= (byte)key_gen.GetNext();
    }
    return Encoding.UTF8.GetString (name);
}
```

#### DecryptName

```csharp
string DecryptName (byte[] name, uint key) {
    for (int i = 0; i < name.Length; ++i)
    {
        name[i] ^= (byte)(key >> (i << 3));
    }
    return Encoding.UTF8.GetString (name);
}
```

### GameRes.Formats.RPGMaker.RgssEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Key ;
```

### GameRes.Formats.RPGMaker.KeyGenerator

#### 状态与常量

```csharp
uint    m_seed ;

public uint Current { get { return m_seed; } }
```

#### KeyGenerator

```csharp
public KeyGenerator (uint seed) {
    m_seed = seed;
}
```

#### GetNext

```csharp
public uint GetNext () {
    uint key = m_seed;
    m_seed = m_seed * 7 + 3;
    return key;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Experimental/RPGMaker/ArcRGSS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
