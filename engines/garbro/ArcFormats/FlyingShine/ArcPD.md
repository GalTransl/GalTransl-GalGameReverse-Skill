# FlyingShine / ArcPD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PD/2` / `GameRes.Formats.Fs.FlyingShinePdOpener` | `pd` | `466c7969` | `False` |
| `PD/3` / `GameRes.Formats.Fs.Pd3Opener` | `pd` | 无固定签名或来源表达式未解析 | `False` |
| `PD` / `GameRes.Formats.Fs.PdOpener` | `pd` | `5061636b` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PdOpener.TryOpen` | `uint version = file.View.ReadUInt32 (4);` |
| `PdOpener.TryOpen` | `int count = file.View.ReadInt32 (0x40);` |
| `PdOpener.TryOpen` | `string name = file.View.ReadString (cur_offset, 0x80);` |
| `PdOpener.TryOpen` | `entry.Offset = file.View.ReadInt64 (cur_offset+0x80);` |
| `PdOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (cur_offset+0x88);` |
| `FlyingShinePdOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "ngShinePDFile\0"))` |
| `FlyingShinePdOpener.TryOpen` | `uint crc = file.View.ReadUInt16 (0x12);` |
| `FlyingShinePdOpener.TryOpen` | `byte key  = file.View.ReadByte (0x14);` |
| `FlyingShinePdOpener.TryOpen` | `int count = file.View.ReadInt32 (0x1c);` |
| `FlyingShinePdOpener.TryOpen` | `uint shift  = LittleEndian.ToUInt32 (buf, 0x24);` |
| `FlyingShinePdOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (buf, 0x28) - shift;` |
| `FlyingShinePdOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (buf, 0x2c) - shift;` |
| `FlyingShinePdOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `FlyingShinePdOpener.OpenOgg` | `var header = arc.File.View.ReadBytes (entry.Offset, header_length);` |
| `FlyingShinePdOpener.OpenOgg` | `if (!(header.AsciiEqual (0, "OggS") &&` |
| `FlyingShinePdOpener.OpenOgg` | `header.AsciiEqual (0x1D, "vorbis")))` |
| `Pd3Opener.TryOpen` | `int index_count = file.View.ReadInt32 (0);` |
| `Pd3Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Pd3Opener.TryOpen` | `uint total_size = file.View.ReadUInt32 (0xC);` |
| `Pd3Opener.TryOpen` | `if (0 != file.View.ReadByte (index_offset))` |
| `Pd3Opener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x104);` |
| `Pd3Opener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+0x108);` |
| `Pd3Opener.TryOpen` | `entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x10C);` |
| `Pd3Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Fs.PackPlusArchive

继承/接口：`ArcFile`。

### GameRes.Formats.Fs.PdOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint version = file.View.ReadUInt32 (4);
    if (0x796c6e4f != version && 0x73756c50 != version)
        return null;
    int count = file.View.ReadInt32 (0x40);
    if (!IsSaneCount (count) || count * 0x90 >= file.MaxOffset)
        return null;
    bool encrypted = 0x73756c50 == version;
    long cur_offset = 0x48;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (cur_offset, 0x80);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadInt64 (cur_offset+0x80);
        entry.Size = file.View.ReadUInt32 (cur_offset+0x88);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".dsf"))
            entry.Type = "script";
        dir.Add (entry);
        cur_offset += 0x90;
    }
    return encrypted ? new PackPlusArchive (file, this, dir) : new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (arc is PackPlusArchive)
        input = new XoredStream (input, 0xFF);
    return input;
}
```

#### CopyScrambled

```csharp
void CopyScrambled (Stream input, Stream output) {
    byte[] buffer = new byte[81920];
    for (;;)
    {
        int read = input.Read (buffer, 0, buffer.Length);
        if (0 == read)
            break;
        for (int i = 0; i < read; ++i)
            buffer[i] = (byte)~buffer[i];
        output.Write (buffer, 0, read);
    }
}
```

### GameRes.Formats.Fs.FlyingShinePdOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "ngShinePDFile\0"))
        return null;
    uint crc = file.View.ReadUInt16 (0x12);
    byte key  = file.View.ReadByte (0x14);
    int count = file.View.ReadInt32 (0x1c);
    if (!IsSaneCount (count))
        return null;
    uint index_size = (uint)(0x30 * count);
    if (index_size > file.View.Reserve (0x20, index_size))
        return null;
    var enc = Encodings.cp932;
    var buf = new byte[0x30];
    long index_offset = 0x20;
    var dir = new List<Entry> (count);
    for (uint i = 0; i < count; ++i)
    {
        file.View.Read (index_offset, buf, 0, 0x30);
        DecodeEntry (buf, key);
        int len = Array.IndexOf (buf, (byte)0);
        if (len <= 0 || len >= 0x24)
            return null;
        string name = enc.GetString (buf, 0, len);
        var entry = Create<Entry> (name);
        uint shift  = LittleEndian.ToUInt32 (buf, 0x24);
        entry.Offset = LittleEndian.ToUInt32 (buf, 0x28) - shift;
        entry.Size   = LittleEndian.ToUInt32 (buf, 0x2c) - shift;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x30;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Name.HasExtension (".ogg") && entry.Size > 0x22)
        return OpenOgg (arc, entry);
    if (!entry.Name.HasAnyOfExtensions (".def", ".dsf") || entry.Size < 2)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    byte key = (byte)(data[data.Length-1] ^ 0xA);
    if (0xD == (data[data.Length-2] ^ key))
    {
        DecodeEntry (data, key);
    }
    return new BinMemoryStream (data);
}
```

#### OpenOgg

```csharp
Stream OpenOgg (ArcFile arc, Entry entry) {
    const uint header_length = 0x23;
    var header = arc.File.View.ReadBytes (entry.Offset, header_length);
    if (!(header.AsciiEqual (0, "OggS") &&
          header[0x1A] != 1 && header[0x1B] == 0x1E && header[0x1C] == 1 &&
          header.AsciiEqual (0x1D, "vorbis")))
        return base.OpenEntry (arc, entry);
    header[0x1A] = 1;
    var rest = arc.File.CreateStream (entry.Offset+header_length, entry.Size-header_length);
    return new PrefixStream (header, rest);
}
```

#### DecodeEntry

```csharp
void DecodeEntry (byte[] buf, byte key) {
    for (int i = 0; i < buf.Length; ++i)
        buf[i] ^= key;
}
```

### GameRes.Formats.Fs.Pd3Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int index_count = file.View.ReadInt32 (0);
    int count = file.View.ReadInt32 (4);
    uint total_size = file.View.ReadUInt32 (0xC);
    if (index_count < count || !IsSaneCount (index_count) || !IsSaneCount (count))
        return null;
    uint index_size = 0x11C * (uint)index_count;
    if (index_size >= file.MaxOffset - 0x18)
        return null;
    uint index_offset = 0x18;
    long base_offset = index_size + index_offset;
    if (base_offset + total_size != file.MaxOffset)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < index_count; ++i)
    {
        if (0 != file.View.ReadByte (index_offset))
        {
            var name = file.View.ReadString (index_offset, 0x104);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Size = file.View.ReadUInt32 (index_offset+0x108);
            entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x10C);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += 0x11C;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!entry.Name.HasAnyOfExtensions (".def", ".dsf"))
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 0; i < data.Length; ++i)
        data[i] = Binary.RotByteR (data[i], 4);
    return new BinMemoryStream (data);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/FlyingShine/ArcPD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
