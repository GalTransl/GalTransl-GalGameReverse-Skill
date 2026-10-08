# Stack / ArcGPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GPK/STACK` / `GameRes.Formats.Stack.GpkOpener` | `gpk` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GpkOpener.TryOpen` | `if (!file.View.AsciiEqual (idx_offset, "STKFile0PIDX") \|\|` |
| `GpkOpener.TryOpen` | `!file.View.AsciiEqual (idx_offset+16, "STKFile0PACKFILE"))` |
| `GpkOpener.TryOpen` | `uint idx_size = file.View.ReadUInt32 (idx_offset+12);` |
| `GpkOpener.TryOpen` | `int name_length = index.ReadUInt16() * 2;` |
| `GpkOpener.TryOpen` | `index.ReadInt32();` |
| `GpkOpener.TryOpen` | `index.ReadInt16();` |
| `GpkOpener.TryOpen` | `entry.Offset = index.ReadUInt32();` |
| `GpkOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `GpkOpener.TryOpen` | `entry.UnpackedSize = index.ReadUInt32();` |
| `GpkOpener.TryOpen` | `int header_length = index.ReadUInt8();` |
| `GpkOpener.TryOpen` | `entry.Header = index.ReadBytes (header_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Stack.GpkEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte[]   Header ;
```

### GameRes.Formats.Stack.GpkOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long idx_offset = file.MaxOffset - 32;
    if (idx_offset <= 0)
        return null;
    if (!file.View.AsciiEqual (idx_offset, "STKFile0PIDX") ||
        !file.View.AsciiEqual (idx_offset+16, "STKFile0PACKFILE"))
        return null;
    uint idx_size = file.View.ReadUInt32 (idx_offset+12);
    if (idx_size > idx_offset)
        return null;
    idx_offset -= idx_size;
    var key = QueryKey (file.Name);
    if (null == key)
        return null;
    Stream input = file.CreateStream (idx_offset, idx_size);
    input = new ByteStringEncryptedStream (input, key);
    input.Position = 4;
    using (input = new ZLibStream (input, CompressionMode.Decompress))
    using (var index = new BinaryStream (input, file.Name))
    {
        var name_buffer = new byte[0x100];
        var dir = new List<Entry>();
        while (index.PeekByte() != -1)
        {
            int name_length = index.ReadUInt16() * 2;
            if (0 == name_length)
                break;
            if (name_length > name_buffer.Length)
                name_buffer = new byte[name_length];
            index.Read (name_buffer, 0, name_length);
            var name = Encoding.Unicode.GetString (name_buffer, 0, name_length);
            var entry = Create<GpkEntry> (name);

            index.ReadInt32();
            index.ReadInt16();
            entry.Offset = index.ReadUInt32();
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            index.ReadInt32();
            entry.UnpackedSize = index.ReadUInt32();
            entry.IsPacked = entry.UnpackedSize != 0;
            int header_length = index.ReadUInt8();
            if (header_length > 0)
                entry.Header = index.ReadBytes (header_length);
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var gent = (GpkEntry)entry;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (gent.Header != null)
        input = new PrefixStream (gent.Header, input);
    if (gent.IsPacked)
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

#### QueryKey

```csharp
byte[] QueryKey (string arc_name) {
    if (VFS.IsVirtual)
        return null;
    var dir = VFS.GetDirectoryName (arc_name);
    var parent_dir = Directory.GetParent (dir).FullName;
    var exe_files = VFS.GetFiles (VFS.CombinePath (parent_dir, "*.exe")).Concat (VFS.GetFiles (VFS.CombinePath (dir, "*.exe")));
    foreach (var exe_entry in exe_files)
    {
        try
        {
            using (var exe = new ExeFile.ResourceAccessor (exe_entry.Name))
            {
                var code = exe.GetResource ("CIPHERCODE", "CODE");
                if (null == code)
                    continue;
                if (20 == code.Length)
                    code = new CowArray<byte> (code, 4, 16).ToArray();
                return code;
            }
        }
        catch {  }
    }
    return null;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Stack/ArcGPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
