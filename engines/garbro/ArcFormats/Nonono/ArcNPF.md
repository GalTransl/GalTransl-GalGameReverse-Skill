# Nonono / ArcNPF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NPF` / `GameRes.Formats.Nonono.NpfOpener` | `npf` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NpfOpener.TryOpen` | `if (file.View.ReadInt32 (4) != 4 \|\| file.View.ReadInt32 (8) != 1)` |
| `NpfOpener.ReadIndex` | `var header = file.View.ReadBytes (12, 20);` |
| `NpfOpener.ReadIndex` | `if (!header.AsciiEqual ("FAT "))` |
| `NpfOpener.ReadIndex` | `int count = header.ToInt32 (8);` |
| `NpfOpener.ReadIndex` | `var index = file.View.ReadBytes (0x20, 20 * (uint)count);` |
| `NpfOpener.ReadIndex` | `int name_length = index.ToInt32 (pos+12);` |
| `NpfOpener.ReadIndex` | `int seed = index.ToInt32 (pos+8);` |
| `NpfOpener.ReadIndex` | `entry.Offset = index.ToUInt32 (pos+4);` |
| `NpfOpener.ReadIndex` | `entry.Size   = index.ToUInt32 (pos+16);` |
| `NpfOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nonono.NpfEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  Seed ;
```

### GameRes.Formats.Nonono.NpfArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IRandomGenerator KeyGenerator ;
```

#### NpfArchive

```csharp
public NpfArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IRandomGenerator rnd)
    : base (arc, impl, dir) {
    KeyGenerator = rnd;
}
```

### GameRes.Formats.Nonono.NpfOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const int DefaultSeed = 0x46415420 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadInt32 (4) != 4 || file.View.ReadInt32 (8) != 1)
        return null;

    foreach (var rnd in GetGenerators())
    {
        var dir = ReadIndex (file, rnd);
        if (dir != null)
        {
            return new NpfArchive (file, this, dir, rnd);
        }
    }
    return null;
}
```

#### GetGenerators

```csharp
internal IEnumerable<IRandomGenerator> GetGenerators () {
    yield return new RandomGenerator1 (DefaultSeed);
    yield return new RandomGenerator2 (DefaultSeed);
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (ArcView file, IRandomGenerator rnd) {
    var header = file.View.ReadBytes (12, 20);

    Decrypt (header, 0, header.Length, rnd);
    if (!header.AsciiEqual ("FAT "))
        return null;
    int count = header.ToInt32 (8);
    if (!IsSaneCount (count))
        return null;
    rnd.SRand (count);
    var index = file.View.ReadBytes (0x20, 20 * (uint)count);
    Decrypt (index, 0, index.Length, rnd);
    int pos = 0;
    int name_pos = 0x20 + 20 * count;
    var dir = new List<Entry> (count);
    var name_buffer = new byte[0x100];
    for (int i = 0; i < count; ++i)
    {
        int name_length = index.ToInt32 (pos+12);
        if (name_length <= 0 || name_length > name_buffer.Length)
            return null;
        file.View.Read (name_pos, name_buffer, 0, (uint)name_length);
        int seed = index.ToInt32 (pos+8);
        rnd.SRand (seed);
        Decrypt (name_buffer, 0, name_length, rnd);
        var name = Encodings.cp932.GetString (name_buffer, 0, name_length);
        var entry = Create<NpfEntry> (name);
        entry.Offset = index.ToUInt32 (pos+4);
        entry.Size   = index.ToUInt32 (pos+16);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Seed = seed;
        dir.Add (entry);
        pos += 20;
        name_pos += name_length;
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var narc = (NpfArchive)arc;
    var nent = (NpfEntry)entry;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    var rnd = narc.KeyGenerator;
    rnd.SRand (nent.Seed);
    Decrypt (data, 0, data.Length, rnd);
    return new BinMemoryStream (data, entry.Name);
}
```

#### Decrypt

```csharp
internal void Decrypt (byte[] data, int pos, int count, IRandomGenerator rnd) {
    for (int i = 0; i < count; ++i)
        data[pos + i] ^= (byte)rnd.Rand();
}
```

### GameRes.Formats.Nonono.RandomGenerator1

继承/接口：`IRandomGenerator`。

#### 状态与常量

```csharp
int      m_seed ;

const int DefaultSeed = 0x67895 ;
```

#### RandomGenerator1

```csharp
public RandomGenerator1 (int seed = DefaultSeed) {
    SRand (seed);
}
```

#### SRand

```csharp
public void SRand (int seed) {
    m_seed = seed;
    for (int i = 0; i < 32; ++i)
    {
        Rand();
    }
}
```

#### Rand

```csharp
public int Rand () {
    m_seed ^= 0x65AC9365;
    m_seed ^= (((m_seed >> 1) ^ m_seed) >> 3)
            ^ (((m_seed << 1) ^ m_seed) << 3);
    return m_seed;
}
```

### GameRes.Formats.Nonono.RandomGenerator2

继承/接口：`IRandomGenerator`。

#### 状态与常量

```csharp
int     m_seed1 ;

int     m_seed2 ;

const int DefaultSeed = 0x67895 ;
```

#### RandomGenerator2

```csharp
public RandomGenerator2 (int seed = DefaultSeed) {
    SRand (seed);
}
```

#### SRand

```csharp
public void SRand (int seed) {
    m_seed1 = seed;
    m_seed2 = ((seed >> 12) ^ (seed << 18)) - 0x579E2B8D;
}
```

#### Rand

```csharp
public int Rand () {
    int n = m_seed2 + ((m_seed1 >> 10) ^ (m_seed1 << 14));
    m_seed2 = n - 0x15633649 + ((m_seed2 >> 12) ^ (m_seed2 << 18));
    return m_seed2;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Nonono/ArcNPF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
