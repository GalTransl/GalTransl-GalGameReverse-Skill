# Suika / ArcSuika：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/SUIKA` / `GameRes.Formats.Suika.ArcOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `ulong count = file.View.ReadUInt64 (0);` |
| `ArcOpener.TryOpen` | `if (file.View.ReadByte (0x107) != 0)` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x100);` |
| `ArcOpener.TryOpen` | `entry.Size = (uint)file.View.ReadInt64 (index_offset + 0x100);` |
| `ArcOpener.TryOpen` | `entry.Offset = file.View.ReadInt64 (index_offset + 0x108);` |
| `ArcOpener.OpenEncrypted` | `var name_buffer = file.View.ReadBytes (index_offset, 0x100);` |
| `ArcOpener.OpenEncrypted` | `entry.Size = (uint)file.View.ReadInt64 (index_offset + 0x100);` |
| `ArcOpener.OpenEncrypted` | `entry.Offset = file.View.ReadInt64 (index_offset + 0x108);` |
| `ArcOpener.OpenEntry` | `var data = sarc.File.View.ReadBytes (aent.Offset, aent.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Suika.SuikaArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public ulong ObfsKey ;
```

#### SuikaArchive

```csharp
public SuikaArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ulong key)
    : base (arc, impl, dir) {
    ObfsKey = key;
}
```

### GameRes.Formats.Suika.ArcEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int Order ;
```

### GameRes.Formats.Suika.ArcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ulong[] KnownKeys = new[] { 0xABADCAFEDEADBEEFu, 0xCAFEF00DABADBEEFu }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    ulong count = file.View.ReadUInt64 (0);
    if (!IsSaneCount ((int)count) || (count >> 32) != 0)
        return null;

    if (file.View.ReadByte (0x107) != 0)
    {
        foreach (ulong key in KnownKeys)
        {
            try
            {
                return OpenEncrypted (file, (int)count, key);
            }
            catch {  }
        }
        return null;
    }
    else
    {
        uint index_offset = 8;
        var dir = new List<Entry> ((int)count);
        for (int i = 0; i < (int)count; i++)
        {
            var name = file.View.ReadString (index_offset, 0x100);
            if (string.IsNullOrEmpty (name))
                return null;
            var entry = Create<ArcEntry> (name);
            entry.Size = (uint)file.View.ReadInt64 (index_offset + 0x100);
            entry.Offset = file.View.ReadInt64 (index_offset + 0x108);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += 0x110;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEncrypted

```csharp
ArcFile OpenEncrypted (ArcView file, int count, ulong key) {
    uint index_offset = 8;
    var dir = new List<Entry> (count);

    for (int i = 0; i < count; i++)
    {
        var name_buffer = file.View.ReadBytes (index_offset, 0x100);
        var rnd = new RandomGenerator (i, key);
        for (int j = 0; j < name_buffer.Length; j++)
            name_buffer[j] ^= rnd.Rand();
        var name = Binary.GetCString (name_buffer, 0, Encoding.UTF8);
        if (string.IsNullOrEmpty (name))
            throw new InvalidFormatException();
        var entry = Create<ArcEntry> (name);
        entry.Size = (uint)file.View.ReadInt64 (index_offset + 0x100);
        entry.Offset = file.View.ReadInt64 (index_offset + 0x108);
        entry.Order = i;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x110;
    }

    return new SuikaArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var sarc = arc as SuikaArchive;
    var aent = entry as ArcEntry;

    if (sarc != null)
    {
        var data = sarc.File.View.ReadBytes (aent.Offset, aent.Size);
        var rnd = new RandomGenerator (aent.Order, sarc.ObfsKey);
        for (int i = 0; i < aent.Size; i++)
            data[i] ^= rnd.Rand();
        return new BinMemoryStream (data, aent.Name);
    }
    return base.OpenEntry (arc, entry);
}
```

### GameRes.Formats.Suika.RandomGenerator

#### 状态与常量

```csharp
ulong m_seed, m_key ;
```

#### RandomGenerator

```csharp
public RandomGenerator (int index, ulong seed) {
    index &= 63;

    m_seed = m_key = seed;
    for (int i = 0; i < index; i++)
    {
        m_seed = Binary.RotL (m_seed ^ 0xAFCB8F2FF4FFF33Fu, 1);
    }
}
```

#### Rand

```csharp
public byte Rand () {
    ulong ret = m_seed;

    m_seed = (((m_key & 0xFF00) * m_seed + (m_key & 0xFF)) % m_key) ^ 0xFCBFAFF8F2F4F3F0u;

    return (byte)ret;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Suika/ArcSuika.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
