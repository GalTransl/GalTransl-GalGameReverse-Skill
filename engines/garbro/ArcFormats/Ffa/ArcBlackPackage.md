# Ffa / ArcBlackPackage：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FFA/DAT` / `GameRes.Formats.Ffa.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |
| `FFA/JDAT` / `GameRes.Formats.Ffa.JDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `string name = lst.View.ReadString (index_offset, 14);` |
| `DatOpener.TryOpen` | `entry.Offset = lst.View.ReadUInt32 (index_offset+14);` |
| `DatOpener.TryOpen` | `entry.Size = lst.View.ReadUInt32 (index_offset+18);` |
| `DatOpener.OpenEntry` | `int packed = input.ReadInt32();` |
| `DatOpener.OpenEntry` | `int unpacked = input.ReadInt32();` |
| `JDatOpener.TryOpen` | `long index_offset = file.View.ReadUInt32 (0);` |
| `JDatOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x20);` |
| `JDatOpener.TryOpen` | `entry.Offset = 4 + file.View.ReadUInt32 (index_offset+0x20);` |
| `JDatOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x24);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ffa.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string lst_name = Path.ChangeExtension (file.Name, ".lst");
    if (lst_name == file.Name || !VFS.FileExists (lst_name))
        return null;
    var lst_entry = VFS.FindFile (lst_name);
    int count = (int)(lst_entry.Size/0x16);
    if (count > 0xffff || count*0x16 != lst_entry.Size)
        return null;
    using (var lst = VFS.OpenView (lst_entry))
    {
        var dir = new List<Entry> (count);
        uint index_offset = 0;
        for (int i = 0; i < count; ++i)
        {
            string name = lst.View.ReadString (index_offset, 14);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = lst.View.ReadUInt32 (index_offset+14);
            entry.Size = lst.View.ReadUInt32 (index_offset+18);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += 0x16;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (entry.Size <= 8)
        return input;
    if (!entry.Name.HasAnyOfExtensions ("so4", "so5"))
        return input;
    int packed = input.ReadInt32();
    int unpacked = input.ReadInt32();
    if (packed+8 != entry.Size || packed <= 0 || unpacked <= 0)
    {
        input.Position = 0;
        return input;
    }
    using (input)
    using (var reader = new LzssReader (input, packed, unpacked))
    {
        reader.Unpack();
        return new BinMemoryStream (reader.Data, entry.Name);
    }
}
```

### GameRes.Formats.Ffa.JDatOpener

继承/接口：`DatOpener`。

#### JDatOpener

```csharp
public JDatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long index_offset = file.View.ReadUInt32 (0);
    if (index_offset >= file.MaxOffset)
        return null;
    int index_size = (int)(file.MaxOffset - index_offset);
    int entry_size = 0x34;
    int rem;
    int count = Math.DivRem (index_size, entry_size, out rem);
    if (0 != rem || !IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x20);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = 4 + file.View.ReadUInt32 (index_offset+0x20);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Ffa/ArcBlackPackage.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
