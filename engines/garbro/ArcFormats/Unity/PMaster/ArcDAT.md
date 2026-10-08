# PMaster / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PMASTER` / `GameRes.Formats.Unity.PMaster.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `count += file.View.ReadInt32 (i);` |
| `DatOpener.TryOpen` | `var index = file.View.ReadBytes (0x400, index_length);` |
| `DatOpener.TryOpen` | `DecryptData (index, file.View.ReadUInt32 (0xD4));` |
| `DatOpener.TryOpen` | `uint first_offset = index.ToUInt32 (4);` |
| `DatOpener.TryOpen` | `var names = file.View.ReadBytes (0x400 + index_length, names_length);` |
| `DatOpener.TryOpen` | `DecryptData (names, file.View.ReadUInt32 (0x5C));` |
| `DatOpener.TryOpen` | `int name_pos = index.ToInt32 (index_pos);` |
| `DatOpener.TryOpen` | `entry.Offset = index.ToUInt32 (index_pos+4);` |
| `DatOpener.TryOpen` | `entry.Size   = index.ToUInt32 (index_pos+8);` |
| `DatOpener.TryOpen` | `entry.Key    = index.ToUInt32 (index_pos+12);` |
| `DatOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.PMaster.PMasterEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Key ;
```

### GameRes.Formats.Unity.PMaster.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = 0;
    for (int i = 0; i < 0x400; i += 4)
        count += file.View.ReadInt32 (i);
    if (!IsSaneCount (count))
        return null;
    uint index_length = (uint)count * 0x10;
    if (index_length >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0x400, index_length);
    DecryptData (index, file.View.ReadUInt32 (0xD4));

    uint first_offset = index.ToUInt32 (4);
    if (first_offset >= file.MaxOffset || first_offset <= (0x400 + index_length))
        return null;
    uint names_length = first_offset - (0x400 + index_length);
    var names = file.View.ReadBytes (0x400 + index_length, names_length);
    DecryptData (names, file.View.ReadUInt32 (0x5C));

    int index_pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_pos = index.ToInt32 (index_pos);
        var name = Binary.GetCString (names, name_pos);
        var entry = Create<PMasterEntry> (name);
        entry.Offset = index.ToUInt32 (index_pos+4);
        entry.Size   = index.ToUInt32 (index_pos+8);
        entry.Key    = index.ToUInt32 (index_pos+12);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += 16;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PMasterEntry)entry;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, pent.Key);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, uint seed) {
    var key = GenerateKey (seed);
    for (int i = 0; i < data.Length; i++)
    {
        byte b = data[i];
        b ^= key[i & 0xFF];
        b += 0x4D;
        b += key[i % 0x2B];
        b -= key[i & 0xFF];
        b ^= 0x23;
        data[i] = b;
    }
}
```

#### GenerateKey

```csharp
byte[] GenerateKey (uint seed) {
    var key = new byte[256];
    uint n = seed * 2281 + 59455;
    uint n2 = (n << 17) ^ n;
    for (int i = 0; i < 256; i++)
    {
        n >>= 5;
        n ^= n2;
        n *= 471;
        n -= seed;
        n += n2;
        n2 = n + 87;
        n ^= n2 & 91;
        key[i] = (byte)n;
        n >>= 1;
    }
    return key;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Unity/PMaster/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
