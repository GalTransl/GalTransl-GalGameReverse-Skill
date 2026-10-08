# Tanaka / ArcWSM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WSM0` / `GameRes.Formats.Will.Wsm0Opener` | `wsm` | `57534d30` | `False` |
| `WSM1` / `GameRes.Formats.Will.Wsm1Opener` | `wsm` | `57534d31` | `False` |
| `WSM2` / `GameRes.Formats.Will.Wsm2Opener` | `wsm` | `57534d32`, `57534d33` | `False` |
| `WSM4` / `GameRes.Formats.Will.Wsm4Opener` | `wsm` | `57534d34` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Wsm2Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `Wsm2Opener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `Wsm2Opener.TryOpen` | `int version = file.View.ReadByte (3) - '0';` |
| `Wsm2Opener.TryOpen` | `int table_offset = file.View.ReadInt32 (0x10);` |
| `Wsm2Opener.TryOpen` | `int table_count = file.View.ReadInt32 (0x14);` |
| `Wsm2Opener.TryOpen` | `var index = file.View.ReadBytes (0x40, index_size);` |
| `Wsm2Opener.TryOpen` | `entry.Offset = index.ToUInt32 (table_offset) - 0x14;` |
| `Wsm2Opener.TryOpen` | `entry.Size   = index.ToUInt32 (table_offset+8) + 0x14;` |
| `Wsm2Opener.TryOpen` | `entry.Size += index.ToUInt32 (table_offset+4);` |
| `Wsm2Opener.TryOpen` | `int entry_pos = index.ToInt32 (index_offset);` |
| `Wsm0Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `Wsm0Opener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `Wsm0Opener.TryOpen` | `var index = file.View.ReadBytes (0, index_size);` |
| `Wsm0Opener.TryOpen` | `int entry_pos = index.ToInt32 (index_offset);` |
| `Wsm0Opener.TryOpen` | `Offset = index.ToUInt32 (entry_pos+8),` |
| `Wsm0Opener.TryOpen` | `Size   = index.ToUInt32 (entry_pos+12),` |
| `Wsm1Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `Wsm1Opener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `Wsm1Opener.TryOpen` | `var index = file.View.ReadBytes (0, index_size);` |
| `Wsm1Opener.TryOpen` | `int entry_pos = index.ToInt32 (index_offset);` |
| `Wsm1Opener.TryOpen` | `Offset = index.ToUInt32 (entry_pos+8),` |
| `Wsm1Opener.TryOpen` | `Size   = index.ToUInt32 (entry_pos+12),` |
| `Wsm1Opener.TryOpen` | `entry.Format.SamplesPerSecond = index.ToUInt32 (entry_pos+4);` |
| `Wsm4Opener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (4);` |
| `Wsm4Opener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `Wsm4Opener.TryOpen` | `int table_offset = file.View.ReadInt32 (0x10);` |
| `Wsm4Opener.TryOpen` | `int table_count = file.View.ReadInt32 (0x14);` |
| `Wsm4Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (table_offset);` |
| `Wsm4Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (table_offset+4);` |
| `Wsm4Opener.TryOpen` | `dir[i].Name = file.View.ReadString (index_offset, 0x40);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.Wsm2Opener

继承/接口：`ArchiveFormat`。

#### Wsm2Opener

```csharp
public Wsm2Opener () {
    Extensions = new string[] { "wsm" };
    Signatures = new uint[] { 0x324D5357, 0x334D5357 };
    ContainedFormats = new[] { "WAV" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count) || index_size >= file.MaxOffset - 0x40)
        return null;
    int version = file.View.ReadByte (3) - '0';
    int table_offset = file.View.ReadInt32 (0x10);
    int table_count = file.View.ReadInt32 (0x14);
    if (table_offset >= index_size || !IsSaneCount (table_count))
        return null;
    var index = file.View.ReadBytes (0x40, index_size);
    var dir = new List<Entry> (count);
    for (int i = 0; i < table_count; ++i)
    {
        var entry = new Entry { Type = "audio" };
        entry.Offset = index.ToUInt32 (table_offset) - 0x14;
        entry.Size   = index.ToUInt32 (table_offset+8) + 0x14;
        if (3 == version)
            entry.Size += index.ToUInt32 (table_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        table_offset += 0x20;
        dir.Add (entry);
    }
    int index_offset = 0;
    var names = new HashSet<string>();
    for (int i = 0; i < count; ++i)
    {
        int entry_pos = index.ToInt32 (index_offset);
        index_offset += 4;
        int name_length = index[entry_pos+1];
        var name = Binary.GetCString (index, entry_pos+2, name_length-2);
        if (0 == name.Length)
            return null;
        entry_pos += name_length;
        int entry_idx = index[entry_pos+3];
        if (entry_idx >= dir.Count)
            return null;
        if (0 == entry_idx)
            entry_idx = i;
        var entry = dir[entry_idx];
        entry.Name = name + ".wav";
        names.Add (entry.Name);
    }
    if (names.Count != dir.Count)
    {

        for (int i = 0; i < dir.Count; ++i)
        {
            var entry = dir[i];
            entry.Name = string.Format("{0:D2}_{1}", i, entry.Name);
        }
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Will.Wsm0Opener

继承/接口：`ArchiveFormat`。

#### Wsm0Opener

```csharp
public Wsm0Opener () {
    Extensions = new string[] { "wsm" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count) || index_size >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0, index_size);
    var dir = new List<Entry> (count);
    int index_offset = 0x10;
    for (int i = 0; i < count; ++i)
    {
        int entry_pos = index.ToInt32 (index_offset);
        index_offset += 4;
        int name_length = index[entry_pos];
        var name = Binary.GetCString (index, entry_pos+1, name_length-1);
        if (0 == name.Length)
            return null;
        entry_pos += name_length;
        var entry = new WsmEntry {
            Name = string.Format ("{0}.wav", name),
            Type = "audio",
            Offset = index.ToUInt32 (entry_pos+8),
            Size   = index.ToUInt32 (entry_pos+12),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Format.FormatTag = 1;
        entry.Format.Channels = 2;
        entry.Format.BitsPerSample = 16;
        entry.Format.SamplesPerSecond = 44100;
        entry.Format.BlockAlign = (ushort)(entry.Format.Channels * entry.Format.BitsPerSample/8);
        entry.Format.AverageBytesPerSecond = entry.Format.SamplesPerSecond * entry.Format.BlockAlign;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var went = (WsmEntry)entry;
    using (var riff = new MemoryStream (0x2C))
    {
        WaveAudio.WriteRiffHeader (riff, went.Format, entry.Size);
        var input = arc.File.CreateStream (entry.Offset, entry.Size);
        return new PrefixStream (riff.ToArray(), input);
    }
}
```

### GameRes.Formats.Will.Wsm1Opener

继承/接口：`Wsm0Opener`。

#### Wsm1Opener

```csharp
public Wsm1Opener () {
    Extensions = new string[] { "wsm" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count) || index_size >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0, index_size);
    var dir = new List<Entry> (count);
    int index_offset = 0x10;
    for (int i = 0; i < count; ++i)
    {
        int entry_pos = index.ToInt32 (index_offset);
        index_offset += 4;
        int name_length = index[entry_pos];
        var name = Binary.GetCString (index, entry_pos+1, name_length-1);
        if (0 == name.Length)
            return null;
        entry_pos += name_length;
        var entry = new WsmEntry {
            Name = string.Format ("{0}.wav", name),
            Type = "audio",
            Offset = index.ToUInt32 (entry_pos+8),
            Size   = index.ToUInt32 (entry_pos+12),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Format.FormatTag = 1;
        entry.Format.Channels = index[entry_pos+2];
        entry.Format.BitsPerSample = index[entry_pos+3];
        entry.Format.SamplesPerSecond = index.ToUInt32 (entry_pos+4);
        entry.Format.BlockAlign = (ushort)(entry.Format.Channels * entry.Format.BitsPerSample/8);
        entry.Format.AverageBytesPerSecond = entry.Format.SamplesPerSecond * entry.Format.BlockAlign;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Will.WsmEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public WaveFormat Format ;
```

### GameRes.Formats.Will.Wsm4Opener

继承/接口：`ArchiveFormat`。

#### Wsm4Opener

```csharp
public Wsm4Opener () {
    Extensions = new string[] { "wsm" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint data_offset = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count) || data_offset >= file.MaxOffset)
        return null;
    int table_offset = file.View.ReadInt32 (0x10);
    int table_count = file.View.ReadInt32 (0x14);
    if (table_offset >= data_offset || !IsSaneCount (table_count))
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < table_count; ++i)
    {
        var entry = new Entry { Name = i.ToString ("D4"), Type = "audio" };
        entry.Offset = file.View.ReadUInt32 (table_offset);
        entry.Size   = file.View.ReadUInt32 (table_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        table_offset += 0x24;
        dir.Add (entry);
    }
    int index_offset = 0x44;
    for (int i = 0; i < count; ++i)
    {
        dir[i].Name = file.View.ReadString (index_offset, 0x40);
        index_offset += 0x1A8;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Tanaka/ArcWSM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
