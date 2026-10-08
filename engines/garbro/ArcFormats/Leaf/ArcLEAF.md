# Leaf / ArcLEAF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/LEAF` / `GameRes.Formats.Leaf.LeafPackOpener` | `pak` | `4c454146` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LeafPackOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "PACK"))` |
| `LeafPackOpener.TryOpen` | `int count = file.View.ReadInt16 (8);` |
| `LeafPackOpener.TryOpen` | `var index = file.View.ReadBytes (file.MaxOffset - index_size, index_size);` |
| `LeafPackOpener.TryOpen` | `entry.Offset = index.ToUInt32 (index_pos+0xC);` |
| `LeafPackOpener.TryOpen` | `entry.Size   = index.ToUInt32 (index_pos+0x10);` |
| `LeafPackOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Leaf.LeafArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### LeafArchive

```csharp
public LeafArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Leaf.LeafPackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public static readonly byte[] DefaultKey = {
    0x71, 0x48, 0x6A, 0x55, 0x9F, 0x13, 0x58, 0xF7, 0xD1, 0x7C, 0x3E
}

static LeafPackScheme DefaultScheme = new LeafPackScheme { KnownSchemes = new Dictionary<string, byte[]>() }
```

#### LeafPackOpener

```csharp
LeafPackOpener () {
    ContainedFormats = new[] { "LFG", "P16", "DAT/GENERIC" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "PACK"))
        return null;
    int count = file.View.ReadInt16 (8);
    if (!IsSaneCount (count))
        return null;
    uint index_size = (uint)count * 0x18;
    if (index_size >= file.MaxOffset)
        return null;
    var key = QueryKey (file.Name);
    if (null == key)
        return null;
    var index = file.View.ReadBytes (file.MaxOffset - index_size, index_size);
    DecryptData (index, key);
    int index_pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, index_pos, 8).TrimEnd();
        var ext  = Binary.GetCString (index, index_pos+8, 3).TrimEnd();
        if (!string.IsNullOrWhiteSpace (ext))
            name = Path.ChangeExtension (name, ext);
        var entry = Create<Entry> (name);
        entry.Offset = index.ToUInt32 (index_pos+0xC);
        entry.Size   = index.ToUInt32 (index_pos+0x10);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += 0x18;
    }
    return new LeafArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var larc = (LeafArchive)arc;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, larc.Key);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, byte[] key) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] -= key[i % key.Length];
    }
}
```

#### QueryKey

```csharp
byte[] QueryKey (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name, @"*.exe");
    var key = GetTitleKey (title);
    if (null == key)
    {
        var options = Query<LeafOptions> (arcStrings.ArcEncryptedNotice);
        key = options.Key;
    }
    return key;
}
```

#### GetTitleKey

```csharp
byte[] GetTitleKey (string title) {
    byte[] key = null;
    if (!string.IsNullOrEmpty (title))
        KnownKeys.TryGetValue (title, out key);
    return key;
}
```

### GameRes.Formats.Leaf.LeafOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[]   Key ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Leaf/ArcLEAF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
