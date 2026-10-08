# Emic / ArcPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/EMIC` / `GameRes.Formats.Emic.PacOpener` | `pac` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `int count = file.View.ReadInt32 (0x28);` |
| `PacOpener.TryOpen` | `uint is_encrypted = file.View.ReadUInt32 (4);` |
| `PacOpener.TryOpen` | `key = file.View.ReadBytes (8, 0x20);` |
| `PacOpener.TryOpen` | `count = file.View.ReadInt32 (4);` |
| `PacOpener.TryOpen` | `is_encrypted = file.View.ReadUInt32 (8);` |
| `PacOpener.TryOpen` | `key = file.View.ReadBytes (0xC, 0x20);` |
| `PacOpener.TryOpen` | `int name_len = reader.ReadInt32();` |
| `PacOpener.TryOpen` | `entry.Size   = reader.ReadUInt32();` |
| `PacOpener.TryOpen` | `entry.Offset = reader.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Emic.EmicArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### EmicArchive

```csharp
public EmicArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Emic.PacOpener

继承/接口：`ArchiveFormat`。

#### PacOpener

```csharp
public PacOpener () {
    Extensions = new string[] { "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    byte[] key;
    int count = file.View.ReadInt32 (0x28);
    uint is_encrypted = file.View.ReadUInt32 (4);
    if (IsSaneCount (count) && is_encrypted <= 1)
    {
        key = file.View.ReadBytes (8, 0x20);
        for (int i = 0; i < key.Length; ++i)
            key[i] ^= 0xAA;
    }
    else
    {
        count = file.View.ReadInt32 (4);
        is_encrypted = file.View.ReadUInt32 (8);
        if (!IsSaneCount (count) || is_encrypted > 1)
            return null;
        key = file.View.ReadBytes (0xC, 0x20);
        for (int i = 0; i < key.Length; ++i)
            key[i] ^= 0xAB;
    }
    Stream input = file.CreateStream();
    if (1 == is_encrypted)
        input = new ByteStringEncryptedStream (input, 0, key);
    using (var reader = new BinaryReader (input))
    {
        input.Position = 0x2C;
        var index_buf = new byte[0x108];
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            int name_len = reader.ReadInt32();
            if (name_len <= 0 || name_len > index_buf.Length)
                return null;
            if (name_len != reader.Read (index_buf, 0, name_len))
                return null;
            string name = Binary.GetCString (index_buf, 0, name_len);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Size   = reader.ReadUInt32();
            entry.Offset = reader.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        if (1 == is_encrypted)
            return new EmicArchive (file, this, dir, key);
        else
            return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var emic = arc as EmicArchive;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null != emic)
        input = new ByteStringEncryptedStream (input, entry.Offset, emic.Key);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Emic/ArcPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
