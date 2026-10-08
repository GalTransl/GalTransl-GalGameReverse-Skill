# AnimeGameSystem / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/AGS` / `GameRes.Formats.Ags.DatOpener` | `dat` | `7061636b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt16 (4);` |
| `DatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `DatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x10);` |
| `DatOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x14);` |
| `DatOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ags.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public static readonly EncryptionScheme DefaultScheme = new EncryptionScheme {
    FileMap = new Dictionary<string, EncryptionKey>()
}

AgsScheme m_scheme = new AgsScheme {
    KnownSchemes = new Dictionary<string, EncryptionScheme>(),
    EncryptedArchives = new HashSet<string>()
}

HashSet<string>                 EncryptedArchives { get { return m_scheme.EncryptedArchives; } }
```

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt16 (4);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 6;
    uint index_size = (uint)count*0x18;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x10);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    var arc_name = Path.GetFileName (file.Name);
    if (EncryptedArchives.Contains (arc_name))
    {
        var options = Query<AgsOptions> (arcStrings.AGSMightBeEncrypted);
        EncryptionKey key;
        if (options.Scheme.FileMap.TryGetValue (arc_name, out key))
            return new DatArchive (file, this, dir, key);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var earc = arc as DatArchive;
    if (null == earc)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    byte key = earc.Key.Initial;
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] ^= key;
        key += earc.Key.Increment;
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### GetScheme

```csharp
public EncryptionScheme GetScheme (string title) {
    EncryptionScheme scheme;
    if (string.IsNullOrEmpty (title) || !KnownSchemes.TryGetValue (title, out scheme))
        scheme = DefaultScheme;
    return scheme;
}
```

### GameRes.Formats.Ags.DatArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public EncryptionKey Key ;
```

#### DatArchive

```csharp
public DatArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, EncryptionKey key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Ags.EncryptionKey

#### 状态与常量

```csharp
public byte Initial ;

public byte Increment ;
```

### GameRes.Formats.Ags.EncryptionScheme

#### 状态与常量

```csharp
public Dictionary<string, EncryptionKey> FileMap ;
```

### GameRes.Formats.Ags.AgsScheme

继承/接口：`ResourceScheme`。

#### 状态与常量

```csharp
public HashSet<string>                      EncryptedArchives ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AnimeGameSystem/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
