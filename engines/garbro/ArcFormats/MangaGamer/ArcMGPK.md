# MangaGamer / ArcMGPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MGPK0` / `GameRes.Formats.Mg.Mgpk0Opener` | `pac` | `4d47504b` | `False` |
| `MGPK` / `GameRes.Formats.Mg.MgpkOpener` | `pac` | `4d47504b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MgpkOpener.TryOpen` | `int version = file.View.ReadInt32 (4);` |
| `MgpkOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `MgpkOpener.TryOpen` | `uint name_length = file.View.ReadByte (cur_offset);` |
| `MgpkOpener.TryOpen` | `string name = file.View.ReadString (cur_offset+1, name_length, Encoding.UTF8);` |
| `MgpkOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (cur_offset+0x20);` |
| `MgpkOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (cur_offset+0x24);` |
| `Mgpk0Opener.TryOpen` | `int version = file.View.ReadInt32 (4);` |
| `Mgpk0Opener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `Mgpk0Opener.TryOpen` | `string name = file.View.ReadString (cur_offset, 0x20, Encoding.UTF8);` |
| `Mgpk0Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (cur_offset+0x20);` |
| `Mgpk0Opener.TryOpen` | `entry.Size = file.View.ReadUInt32 (cur_offset+0x2C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Mg.MgArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### MgArchive

```csharp
public MgArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Mg.MgOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] Key ;
```

### GameRes.Formats.Mg.MgpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static MgScheme DefaultScheme = new MgScheme { KnownKeys = new Dictionary<string, byte[]>() }
```

#### MgpkOpener

```csharp
public MgpkOpener () {
    Extensions = new string[] { "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (4);
    int count = file.View.ReadInt32 (8);
    if (version < 1 || !IsSaneCount (count))
        return null;
    long cur_offset = 0x0C;
    var dir = new List<Entry> (count);
    bool has_encrypted = false;
    for (int i = 0; i < count; ++i)
    {
        uint name_length = file.View.ReadByte (cur_offset);
        string name = file.View.ReadString (cur_offset+1, name_length, Encoding.UTF8);
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (cur_offset+0x20);
        entry.Size = file.View.ReadUInt32 (cur_offset+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        has_encrypted = has_encrypted || name.HasAnyOfExtensions ("png", "txt");
        dir.Add (entry);
        cur_offset += 0x30;
    }
    if (has_encrypted && KnownKeys.Count > 0)
    {
        var key = QueryKey (file.Name);
        if (key != null)
            return new MgArchive (file, this, dir, key);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var mgarc = arc as MgArchive;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null == mgarc || null == mgarc.Key)
        return input;
    using (input)
    {
        byte[] data = new byte[entry.Size];
        input.Read (data, 0, data.Length);
        DecryptData (data, mgarc.Key);
        if (entry.Name.HasExtension ("txt"))
            return DecompressStream (data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### DecryptData

```csharp
protected virtual void DecryptData (byte[] input, byte[] key) {
    key = (byte[])key.Clone();
    for (int i = 0; i < input.Length; i++)
    {
        input[i] ^= key[i % key.Length];
        key[i % key.Length] += 27;
    }
}
```

#### DecompressStream

```csharp
internal Stream DecompressStream (byte[] input) {
    byte[] output = new byte[input.Length * 2];
    int output_size = lzf_decompress (input, ref output);
    return new BinMemoryStream (output, 0, output_size);
}
```

#### lzf_decompress

```csharp
private static int lzf_decompress (byte[] input, ref byte[] output) {
    int src = 0;
    int dst = 0;
    while (src < input.Length)
    {
        int count = input[src++];
        if (count < 32)
        {
            ++count;
            if (dst + count > output.Length)
            {
                Array.Resize (ref output, Math.Max (checked(output.Length * 2), dst + count));
            }
            Buffer.BlockCopy (input, src, output, dst, count);
            src += count;
            dst += count;
        }
        else
        {
            int offset = (count & 31) << 8;
            count >>= 5;
            if (7 == count)
            {
                count += input[src++];
            }
            count += 2;
            offset += input[src++] + 1;
            if (offset > dst)
                throw new InvalidFormatException();
            if (dst + count > output.Length)
            {
                Array.Resize (ref output, Math.Max (checked(output.Length * 2), dst + count));
            }
            Binary.CopyOverlapped (output, dst-offset, dst, count);
            dst += count;
        }
    }
    return dst;
}
```

#### QueryKey

```csharp
internal byte[] QueryKey (string arc_name) {
    var options = Query<MgOptions> (arcStrings.ArcEncryptedNotice);
    return options.Key;
}
```

#### GetKey

```csharp
public static byte[] GetKey (string title) {
    byte[] key;
    if (string.IsNullOrEmpty (title) || !KnownKeys.TryGetValue (title, out key))
        return null;
    return key;
}
```

### GameRes.Formats.Mg.Mgpk0Opener

继承/接口：`MgpkOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (4);
    int count = file.View.ReadInt32 (8);
    if (version != 0 || !IsSaneCount (count))
        return null;
    long cur_offset = 0x0C;
    var dir = new List<Entry> (count);
    bool has_encrypted = false;
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (cur_offset, 0x20, Encoding.UTF8);
        var entry = Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (cur_offset+0x20);
        entry.Size = file.View.ReadUInt32 (cur_offset+0x2C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        has_encrypted = has_encrypted || name.HasAnyOfExtensions ("png", "txt");
        dir.Add (entry);
        cur_offset += 0x30;
    }
    if (has_encrypted)
    {
        var key = QueryKey (file.Name);
        if (key != null)
            return new MgArchive (file, this, dir, key);
    }
    return new ArcFile (file, this, dir);
}
```

#### DecryptData

```csharp
protected override void DecryptData (byte[] input, byte[] key) {
    for (int i = 0; i < input.Length; i++)
    {
        input[i] ^= key[i % key.Length];
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MangaGamer/ArcMGPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
