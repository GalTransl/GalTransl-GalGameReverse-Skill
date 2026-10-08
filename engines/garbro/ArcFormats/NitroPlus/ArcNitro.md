# NitroPlus / ArcNitro：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/NITRO+` / `GameRes.Formats.NitroPlus.PakOpener` | `pak` | `02000000`, `03000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int version = file.View.ReadInt32 (0);` |
| `PakOpener.OpenPakV2` | `int count = file.View.ReadInt32 (4);` |
| `PakOpener.OpenPakV2` | `int unpacked_size = file.View.ReadInt32 (8);` |
| `PakOpener.OpenPakV2` | `uint packed_size = file.View.ReadUInt32 (0xC);` |
| `PakOpener.OpenPakV2` | `int name_length = header.ReadInt32();` |
| `PakOpener.OpenPakV2` | `entry.Offset        = base_offset + header.ReadUInt32();` |
| `PakOpener.OpenPakV2` | `entry.UnpackedSize  = header.ReadUInt32();` |
| `PakOpener.OpenPakV2` | `entry.Size          = header.ReadUInt32();` |
| `PakOpener.OpenPakV2` | `entry.IsPacked      = header.ReadInt32() != 0;` |
| `PakOpener.OpenPakV2` | `uint psize          = header.ReadUInt32();` |
| `PakOpener.OpenPakV3` | `uint size_xor = file.View.ReadUInt32 (0x104);` |
| `PakOpener.OpenPakV3` | `byte[] name_buf = file.View.ReadBytes (4, 0x100);` |
| `PakOpener.OpenPakV3` | `uint unpacked = file.View.ReadUInt32 (0x108) ^ header_key;` |
| `PakOpener.OpenPakV3` | `int count = (int)(file.View.ReadUInt32 (0x10c) ^ header_key);` |
| `PakOpener.OpenPakV3` | `uint header_size = file.View.ReadUInt32 (0x110) ^ size_xor;` |
| `PakOpener.OpenPakV3` | `name_len = header.ReadInt32();` |
| `PakOpener.OpenPakV3` | `entry.Offset        = (header.ReadUInt32() ^ key) + base_offset;` |
| `PakOpener.OpenPakV3` | `entry.UnpackedSize  = (header.ReadUInt32() ^ key);` |
| `PakOpener.OpenPakV3` | `uint ignored        = (header.ReadUInt32() ^ key);` |
| `PakOpener.OpenPakV3` | `entry.IsPacked      = (header.ReadUInt32() ^ key) != 0;` |
| `PakOpener.OpenPakV3` | `uint packed_size    = (header.ReadUInt32() ^ key);` |
| `PakOpener.OpenV3Entry` | `var buf = arc.File.View.ReadBytes (entry.Offset, enc_size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NitroPlus.PakEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint Key ;
```

### GameRes.Formats.NitroPlus.NitroPak

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public int Version ;
```

#### NitroPak

```csharp
public NitroPak (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version)
    : base (arc, impl, dir) {
    Version = version;
}
```

### GameRes.Formats.NitroPlus.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
    Signatures = new uint[] { 2, 3 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (0);
    List<Entry> dir = null;
    if (2 == version)
        dir = OpenPakV2 (file);
    else if (3 == version)
        dir = OpenPakV3 (file);
    if (null == dir)
        return null;
    return new NitroPak (file, this, dir, version);
}
```

#### OpenPakV2

```csharp
private List<Entry> OpenPakV2 (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    int unpacked_size = file.View.ReadInt32 (8);
    uint packed_size = file.View.ReadUInt32 (0xC);
    using (var input = file.CreateStream (0x114, packed_size))
    using (var header_stream = new ZLibStream (input, CompressionMode.Decompress))
    using (var header = new BinaryReader (header_stream, Encoding.ASCII, true))
    {
        long base_offset = 0x114 + packed_size;
        var name_buf = new byte[0x40];
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            int name_length = header.ReadInt32();
            if (name_length <= 0)
                return null;
            if (name_length > name_buf.Length)
                name_buf = new byte[name_length];
            if (name_length != header.Read (name_buf, 0, name_length))
                return null;
            var name = Encodings.cp932.GetString (name_buf, 0, name_length);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);

            entry.Offset        = base_offset + header.ReadUInt32();
            entry.UnpackedSize  = header.ReadUInt32();
            entry.Size          = header.ReadUInt32();
            entry.IsPacked      = header.ReadInt32() != 0;
            uint psize          = header.ReadUInt32();
            if (entry.IsPacked)
                entry.Size = psize;

            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return dir;
    }
}
```

#### OpenPakV3

```csharp
private List<Entry> OpenPakV3 (ArcView file) {
    if (0x110 > file.View.Reserve (4, 0x110))
        return null;

    uint size_xor = file.View.ReadUInt32 (0x104);
    if (0x64 != size_xor)
        return null;
    byte[] name_buf = file.View.ReadBytes (4, 0x100);
    int name_len = 0;
    for (int i = 0; i < name_buf.Length; ++i)
    {
        if (0 == name_buf[i])
            break;
        if (name_buf[i] >= 0x80 || name_buf[i] < 0x20)
            return null;
        ++name_len;
    }
    if (0 == name_len || name_len > 0x10)
        return null;

    uint header_key = GetKey (name_buf, name_len);
    uint unpacked = file.View.ReadUInt32 (0x108) ^ header_key;
    int count = (int)(file.View.ReadUInt32 (0x10c) ^ header_key);
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    uint header_size = file.View.ReadUInt32 (0x110) ^ size_xor;
    long base_offset = 0x114 + header_size;
    using (var input = file.CreateStream (0x114, header_size))
    using (var header_stream = new ZLibStream (input, CompressionMode.Decompress))
    using (var header = new BinaryReader (header_stream, Encoding.ASCII, true))
    {
        for (int i = 0; i < count; ++i)
        {
            name_len = header.ReadInt32();
            if (name_len <= 0 || name_len > name_buf.Length)
                return null;
            if (name_len != header.Read (name_buf, 0, name_len))
                return null;
            uint key = GetKey (name_buf, name_len);
            var name = Encodings.cp932.GetString (name_buf, 0, name_len);
            var entry = FormatCatalog.Instance.Create<PakEntry> (name);
            entry.Offset        = (header.ReadUInt32() ^ key) + base_offset;
            entry.UnpackedSize  = (header.ReadUInt32() ^ key);
            uint ignored        = (header.ReadUInt32() ^ key);
            entry.IsPacked      = (header.ReadUInt32() ^ key) != 0;
            uint packed_size    = (header.ReadUInt32() ^ key);
            entry.Key           = key;
            entry.Size          = entry.IsPacked ? packed_size : entry.UnpackedSize;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return dir;
    }
}
```

#### GetKey

```csharp
static uint GetKey (byte[] name, int length) {
    int key = 0;
    for (int i = 0; i < length; ++i)
    {
        key *= 0x89;
        key += (sbyte)name[i];
    }
    return (uint)key;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pak_entry = entry as PakEntry;
    if (pak_entry != null && !pak_entry.IsPacked)
        return OpenV3Entry (arc, pak_entry);

    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    var packed_entry = entry as PackedEntry;
    if (packed_entry != null && packed_entry.IsPacked)
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

#### OpenV3Entry

```csharp
private Stream OpenV3Entry (ArcFile arc, PakEntry entry) {
    uint enc_size = Math.Min (entry.Size, 0x10u);
    if (0 == enc_size)
        return Stream.Null;
    var buf = arc.File.View.ReadBytes (entry.Offset, enc_size);
    uint key = entry.Key;
    for (int i = 0; i < buf.Length; ++i)
    {
        buf[i] ^= (byte)key;
        key = Binary.RotR (key, 8);
    }
    if (enc_size == entry.Size)
        return new BinMemoryStream (buf, entry.Name);
    return new PrefixStream (buf, arc.File.CreateStream (entry.Offset+enc_size, entry.Size-enc_size));
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NitroPlus/ArcNitro.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
