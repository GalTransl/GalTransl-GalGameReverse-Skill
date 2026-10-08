# Yatagarasu / ArcPKG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PKG` / `GameRes.Formats.Yatagarasu.PkgOpener` | `pkg` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkgOpener.TryOpen` | `uint key = file.View.ReadUInt32 (0x84);` |
| `PkgOpener.TryOpen` | `if (key != file.View.ReadUInt32 (0x10C))` |
| `PkgOpener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (4) ^ key);` |
| `PkgOpener.TryOpen` | `var name = index.ReadCString (0x80);` |
| `PkgOpener.TryOpen` | `entry.Size = index.ReadUInt32();` |
| `PkgOpener.TryOpen` | `entry.Offset = index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Yatagarasu.PkgOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".pkg"))
        return null;
    uint key = file.View.ReadUInt32 (0x84);
    if (key != file.View.ReadUInt32 (0x10C))
        return null;
    int count = (int)(file.View.ReadUInt32 (4) ^ key);
    if (!IsSaneCount (count))
        return null;
    var key_bytes = new byte[4];
    LittleEndian.Pack (key, key_bytes, 0);
    using (var input = file.CreateStream())
    using (var dec = new ByteStringEncryptedStream (input, key_bytes))
    using (var index = new BinaryStream (dec, file.Name))
    {
        index.Position = 8;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadCString (0x80);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Size = index.ReadUInt32();
            entry.Offset = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new PkgArchive (file, this, dir, key_bytes);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pkg_arc = (PkgArchive)arc;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new ByteStringEncryptedStream (input, pkg_arc.Key);
}
```

### GameRes.Formats.Yatagarasu.PkgArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### PkgArchive

```csharp
public PkgArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Yatagarasu/ArcPKG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
