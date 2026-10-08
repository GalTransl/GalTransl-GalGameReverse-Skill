# Yatagarasu / ArcPKG2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PKG/2` / `GameRes.Formats.Yatagarasu.Pkg2Opener` | `pkg` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Pkg2Opener.TryOpen` | `uint first_key = file.View.ReadUInt32 (0) ^ (uint)file.MaxOffset;` |
| `Pkg2Opener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (4) ^ key[0]);` |
| `Pkg2Opener.ReadIndex` | `var name = index.ReadCString (0x74);` |
| `Pkg2Opener.ReadIndex` | `entry.Size = index.ReadUInt32();` |
| `Pkg2Opener.ReadIndex` | `entry.Offset = index.ReadUInt32();` |
| `Pkg2Opener.ReadIndex` | `entry.EncryptedSize = index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Yatagarasu.Pkg2Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
PkgScheme m_scheme = new PkgScheme { KnownKeys = new Dictionary<string, uint[]>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".pkg"))
        return null;
    uint first_key = file.View.ReadUInt32 (0) ^ (uint)file.MaxOffset;
    foreach (var key in KnownKeys.Values.Where (k => k[0] == first_key))
    {
        int count = (int)(file.View.ReadUInt32 (4) ^ key[0]);
        if (!IsSaneCount (count))
            continue;
        try
        {
            var arc = ReadIndex (file, key, count);
            if (arc != null)
                return arc;
        }
        catch {  }
    }
    return null;
}
```

#### ReadIndex

```csharp
ArcFile ReadIndex (ArcView file, uint[] key, int count) {
    using (var input = file.CreateStream (8, (uint)count * 0x80u))
    using (var dec = new ByteStringEncryptedStream (input, GetKeyBytes (key)))
    using (var index = new BinaryStream (dec, file.Name))
    {
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadCString (0x74);
            if (0 == name.Length)
                return null;
            var entry = FormatCatalog.Instance.Create<Pkg2Entry> (name);
            entry.Size = index.ReadUInt32();
            entry.Offset = index.ReadUInt32();
            entry.EncryptedSize = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new Pkg2Archive (file, this, dir, key);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pkg_arc = (Pkg2Archive)arc;
    var pkg_ent = (Pkg2Entry)entry;
    var data = new byte[(pkg_ent.Size + 3) & ~3];
    arc.File.View.Read (pkg_ent.Offset, data, 0, pkg_ent.Size);

    uint encrypted_size = pkg_ent.EncryptedSize;
    if (0 == encrypted_size || encrypted_size > pkg_ent.Size)
        encrypted_size = pkg_ent.Size;
    unsafe
    {
        fixed (byte* data8 = data)
        {
            uint* data32 = (uint*)data8;
            uint count = (encrypted_size + 3) / 4;
            uint mask = (entry.Size / 4) & 7;
            for (uint i = 0; i < count; ++i)
                data32[i] ^= pkg_arc.Key[i & mask];
        }
    }
    return new BinMemoryStream (data, 0, (int)entry.Size);
}
```

#### GetKeyBytes

```csharp
static byte[] GetKeyBytes (uint[] key) {
    var bytes = new byte[sizeof(uint) * key.Length];
    Buffer.BlockCopy (key, 0, bytes, 0, bytes.Length);
    return bytes;
}
```

### GameRes.Formats.Yatagarasu.Pkg2Archive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly uint[] Key ;
```

#### Pkg2Archive

```csharp
public Pkg2Archive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Yatagarasu.Pkg2Entry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint EncryptedSize ;
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Yatagarasu/ArcPKG2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
