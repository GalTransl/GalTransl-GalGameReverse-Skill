# HSP / ArcDPM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DPM` / `GameRes.Formats.HSP.DpmOpener` | `dpm`, `bin`, `dat` | `44504d58` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DpmOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (0);` |
| `DpmOpener.TryOpen` | `if (exe.Overlay.Size <= 4 \|\| !file.View.AsciiEqual (exe.Overlay.Offset, "DPMX"))` |
| `DpmOpener.TryOpen` | `int count = file.View.ReadInt32 (base_offset+8);` |
| `DpmOpener.TryOpen` | `long index_offset = base_offset + 0x10 + file.View.ReadUInt32 (base_offset+0xC);` |
| `DpmOpener.TryOpen` | `base_offset += file.View.ReadUInt32 (base_offset+4);` |
| `DpmOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `DpmOpener.TryOpen` | `entry.Key = file.View.ReadUInt32 (index_offset);` |
| `DpmOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4) + base_offset;` |
| `DpmOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+8);` |
| `DpmOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `DpmOpener.FindExeKey` | `return exe.View.ReadUInt32 (key_pos+0x17);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.HSP.DpmOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly uint DefaultKey = 0xAC52AE58 ;

DpmxScheme DefaultScheme = new DpmxScheme { KnownKeys = new Dictionary<string, uint>() }
```

#### DpmOpener

```csharp
public DpmOpener () {
    Extensions = new string[] { "dpm", "bin", "dat" };
    Signatures = new uint[] { 0x584D5044, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint signature = file.View.ReadUInt32 (0);
    bool is_inside_exe = false;
    long base_offset = 0;
    uint arc_key = 0;
    if (0x5A4D == (signature & 0xFFFF))
    {
        var exe = new ExeFile (file);
        if (exe.Overlay.Size <= 4 || !file.View.AsciiEqual (exe.Overlay.Offset, "DPMX"))
            return null;
        base_offset = exe.Overlay.Offset;
        arc_key = FindExeKey (exe, base_offset);
        is_inside_exe = true;
    }
    else if (0x584D5044 != signature)
        return null;
    int count = file.View.ReadInt32 (base_offset+8);
    if (!IsSaneCount (count))
        return null;
    long index_offset = base_offset + 0x10 + file.View.ReadUInt32 (base_offset+0xC);
    uint data_size = (uint)(file.MaxOffset - (index_offset + 32 * count));
    base_offset += file.View.ReadUInt32 (base_offset+4);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        index_offset += 0x14;
        var entry = Create<DpmEntry> (name);
        entry.Key = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4) + base_offset;
        entry.Size   = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0xC;
    }
    if (is_inside_exe)
        return new DpmArchive (file, this, dir, arc_key, data_size);
    else
        return new DpmArchive (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var dent = entry as DpmEntry;
    var darc = arc as DpmArchive;
    if (null == dent || null == darc || 0 == dent.Key)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    darc.DecryptEntry2 (data, dent.Key);
    return new BinMemoryStream (data, entry.Name);
}
```

#### FindExeKey

```csharp
static uint FindExeKey (ExeFile exe, long dpm_offset) {
    uint base_offset = (uint)(dpm_offset - 0x10000);
    var offset_str = base_offset.ToString() + '\0';
    var offset_bytes = Encoding.ASCII.GetBytes (offset_str);
    long key_pos = -1;
    if (exe.ContainsSection (".rdata"))
        key_pos = exe.FindString (exe.Sections[".rdata"], offset_bytes);
    if (-1 == key_pos && exe.ContainsSection (".data"))
        key_pos = exe.FindString (exe.Sections[".data"], offset_bytes);
    if (-1 == key_pos)
        return DefaultKey;
    return exe.View.ReadUInt32 (key_pos+0x17);
}
```

### GameRes.Formats.HSP.DpmEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Key ;
```

### GameRes.Formats.HSP.DpmArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
readonly byte Seed1 ;

readonly byte Seed2 ;
```

#### DpmArchive

```csharp
public DpmArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir)
    : base (arc, impl, dir) {
    Seed1 = 0xAA;
    Seed2 = 0x55;
}
```

#### DpmArchive

```csharp
public DpmArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint arc_key, uint dpm_size)
    : base (arc, impl, dir) {
    Seed1 = (byte)((((arc_key >> 16) & 0xFF) * (arc_key & 0xFF) / 3) ^ dpm_size);
    Seed2 = (byte)((((arc_key >> 8)  & 0xFF) * ((arc_key >> 24) & 0xFF) / 5) ^ dpm_size ^ 0xAA);
}
```

#### DecryptEntry

```csharp
internal void DecryptEntry (byte[] data, uint entry_key) {
    byte s1 = 0xA5;
    byte s2 = 0x5A;
    s1 = (byte)(Seed1 + ((entry_key >> 16) ^  (entry_key       + s1)));
    s2 = (byte)(Seed2 + ((entry_key >> 24) ^ ((entry_key >> 8) + s2)));
    byte val = 0;
    for (int i = 0; i < data.Length; ++i)
    {
        val += (byte)(s1 ^ (data[i] - s2));
        data[i] = val;
    }
}
```

#### DecryptEntry2

```csharp
internal void DecryptEntry2 (byte[] data, uint entry_key) {
    byte s1 = 0x5A;
    byte s2 = 0xA5;
    s1 = (byte)(Seed1 + ((entry_key >> 16) ^  (entry_key       + s1)));
    s2 = (byte)(Seed2 + ((entry_key >> 24) ^ ((entry_key >> 8) + s2)));
    byte val = 0;
    for (int i = 0; i < data.Length; ++i)
    {
        val += (byte)((s1 ^ data[i]) - s2);
        data[i] = val;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/HSP/ArcDPM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
