# ActiveSoft / ArcADPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ADPACK32` / `GameRes.Formats.AdPack.Pak32Opener` | `pak` | `41445041` | `False` |
| `A98` / `GameRes.Formats.AdPack.PakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int count = file.View.ReadInt16 (0);` |
| `PakOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset+12);` |
| `PakOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset+0x10+12);` |
| `PakOpener.TryOpenVoiceArchive` | `int count = file.View.ReadInt16 (2);` |
| `PakOpener.TryOpenVoiceArchive` | `uint offset = file.View.ReadUInt32 (index_offset+4);` |
| `PakOpener.TryOpenVoiceArchive` | `entry.Size = file.View.ReadUInt32 (index_offset+0xC);` |
| `PakOpener.ReadName` | `string name = file.View.ReadString (offset, 8).TrimEnd (null);` |
| `PakOpener.ReadName` | `string ext  = file.View.ReadString (offset+8, 4).TrimEnd (null);` |
| `Pak32Opener.TryOpen` | `if (!file.View.AsciiEqual (4, "CK32"))` |
| `Pak32Opener.TryOpen` | `int count = file.View.ReadInt32 (12) - 1;` |
| `Pak32Opener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x18);` |
| `Pak32Opener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset+0x1c);` |
| `Pak32Opener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset+0x20+0x1c);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AdPack.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt16 (0);
    if (count <= 1)
        return null;
    if (0x4000 == count)
        return TryOpenVoiceArchive (file);
    long index_offset = 2;
    uint index_size = (uint)(0x10 * count);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    --count;
    var dir = new List<Entry> (count);
    for (uint i = 0; i < count; ++i)
    {
        string name = ReadName (file, index_offset);
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        uint offset = file.View.ReadUInt32 (index_offset+12);
        uint next_offset = file.View.ReadUInt32 (index_offset+0x10+12);
        entry.Size = next_offset - offset;
        entry.Offset = offset;
        if (offset < index_size || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x10;
    }
    return new ArcFile (file, this, dir);
}
```

#### TryOpenVoiceArchive

```csharp
ArcFile TryOpenVoiceArchive (ArcView file) {
    int count = file.View.ReadInt16 (2);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset+4);
        index_offset += 8;
        if (offset == file.MaxOffset && i+1 == count)
            break;
        if (offset > file.MaxOffset)
            return null;
        var entry = new Entry { Offset = offset };
        dir.Add (entry);
    }
    foreach (var entry in dir)
    {
        var name = ReadName (file, index_offset);
        if (string.IsNullOrEmpty (name))
            return null;
        entry.Name = name;
        entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
        entry.Size = file.View.ReadUInt32 (index_offset+0xC);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 0x10;
    }
    return new ArcFile (file, this, dir);
}
```

#### ReadName

```csharp
string ReadName (ArcView file, long offset) {
    string name = file.View.ReadString (offset, 8).TrimEnd (null);
    if (0 == name.Length)
        return null;
    string ext  = file.View.ReadString (offset+8, 4).TrimEnd (null);
    if (0 != ext.Length)
        name += '.'+ext;
    return name;
}
```

### GameRes.Formats.AdPack.Pak32Opener

继承/接口：`ArchiveFormat`。

#### Pak32Opener

```csharp
public Pak32Opener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "CK32"))
        return null;
    int count = file.View.ReadInt32 (12) - 1;
    if (count <= 0 || count > 0xfffff)
        return null;
    uint index_size = (uint)(0x20 * count);
    if (index_size > file.View.Reserve (0x10, index_size))
        return null;
    var dir = new List<Entry> (count);
    long index_offset = 0x10;
    for (uint i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x18);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        uint offset = file.View.ReadUInt32 (index_offset+0x1c);
        uint next_offset = file.View.ReadUInt32 (index_offset+0x20+0x1c);
        entry.Size = next_offset - offset;
        entry.Offset = offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ActiveSoft/ArcADPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
