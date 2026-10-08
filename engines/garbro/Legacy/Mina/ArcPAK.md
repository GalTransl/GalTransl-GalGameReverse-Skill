# Mina / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/MINA/BMP` / `GameRes.Formats.Mina.BmpPakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |
| `PAK/MINA/SPT` / `GameRes.Formats.Mina.ScriptPakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |
| `PAK/MINA/WAV` / `GameRes.Formats.Mina.WavPakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BmpPakOpener.TryOpen` | `if (0 == file.View.ReadByte (pos))` |
| `BmpPakOpener.TryOpen` | `if (pos >= 0x10 \|\| pos <= 4 \|\| !file.View.AsciiEqual (pos-4, ".BMP"))` |
| `BmpPakOpener.TryOpen` | `var name = input.ReadCString();` |
| `BmpPakOpener.TryOpen` | `uint size = input.ReadUInt32();` |
| `WavPakOpener.TryOpen` | `if (0 == file.View.ReadByte (pos))` |
| `WavPakOpener.TryOpen` | `if (pos >= 0x14 \|\| pos <= 8 \|\| !file.View.AsciiEqual (pos-4, ".WAV"))` |
| `WavPakOpener.TryOpen` | `uint data_size = input.ReadUInt32();` |
| `WavPakOpener.TryOpen` | `var name = input.ReadCString();` |
| `WavPakOpener.TryOpen` | `uint fmt_size = input.ReadUInt32();` |
| `WavPakOpener.OpenEntry` | `uint fmt_size = arc.File.View.ReadUInt32 (entry.Offset);` |
| `WavPakOpener.OpenEntry` | `var fmt = arc.File.View.ReadBytes (entry.Offset+4, fmt_size);` |
| `ScriptPakOpener.TryOpen` | `var name = input.ReadCString();` |
| `ScriptPakOpener.TryOpen` | `entry.Size = input.ReadUInt32();` |
| `ScriptPakOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `ScriptPakOpener.OpenEntry` | `int num = data.ToUInt16 (1);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Mina.BmpPakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".PAK"))
        return null;
    int pos;
    for (pos = 0; pos < 0x10; ++pos)
    {
        if (0 == file.View.ReadByte (pos))
            break;
    }
    if (pos >= 0x10 || pos <= 4 || !file.View.AsciiEqual (pos-4, ".BMP"))
        return null;
    using (var input = file.CreateStream())
    {
        var dir = new List<Entry>();
        while (input.PeekByte() != -1)
        {
            var name = input.ReadCString();
            if (name.Length > 0x10)
                return null;
            var entry = Create<Entry> (name);
            entry.Offset = input.Position;
            input.Seek (5, SeekOrigin.Current);
            uint size = input.ReadUInt32();
            entry.Size = size + 9;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            input.Seek (size, SeekOrigin.Current);
        }
        return new ArcFile (file, this, dir);
    }
}
```

### GameRes.Formats.Mina.WavPakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".PAK"))
        return null;
    int pos;
    for (pos = 4; pos < 0x14; ++pos)
    {
        if (0 == file.View.ReadByte (pos))
            break;
    }
    if (pos >= 0x14 || pos <= 8 || !file.View.AsciiEqual (pos-4, ".WAV"))
        return null;
    using (var input = file.CreateStream())
    {
        var dir = new List<Entry>();
        while (input.PeekByte() != -1)
        {
            uint data_size = input.ReadUInt32();
            var name = input.ReadCString();
            if (name.Length > 0x10)
                return null;
            var entry = Create<Entry> (name);
            entry.Offset = input.Position;
            uint fmt_size = input.ReadUInt32();
            if (fmt_size < 0x10)
                return null;
            entry.Size = data_size + fmt_size + 4;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            input.Seek (data_size + fmt_size, SeekOrigin.Current);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    uint fmt_size = arc.File.View.ReadUInt32 (entry.Offset);
    uint pcm_size = entry.Size - 4 - fmt_size;
    using (var mem = new MemoryStream ((int)fmt_size))
    {
        using (var buffer = new BinaryWriter (mem, Encoding.ASCII, true))
        {
            buffer.Write (AudioFormat.Wav.Signature);
            buffer.Write (entry.Size+0x10);
            buffer.Write (0x45564157);
            buffer.Write (0x20746d66);
            buffer.Write (fmt_size);
            var fmt = arc.File.View.ReadBytes (entry.Offset+4, fmt_size);
            buffer.Write (fmt, 0, fmt.Length);
            buffer.Write (0x61746164);
            buffer.Write (pcm_size);
        }
        var header = mem.ToArray();
        var data = arc.File.CreateStream (entry.Offset+4+fmt_size, pcm_size);
        return new PrefixStream (header, data);
    }
}
```

### GameRes.Formats.Mina.ScriptPakOpener

继承/接口：`ArchiveFormat`。

#### ScriptPakOpener

```csharp
public ScriptPakOpener () {
    ContainedFormats = new[] { "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "SCRIPT.PAK"))
        return null;
    using (var input = file.CreateStream())
    {
        var dir = new List<Entry>();
        while (input.PeekByte() != -1)
        {
            var name = input.ReadCString();
            if (name.Length > 0x10)
                return null;
            var entry = Create<Entry> (name);
            entry.Size = input.ReadUInt32();
            entry.Offset = input.Position;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            input.Seek (entry.Size, SeekOrigin.Current);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    var mem = new MemoryStream (data.Length);
    int pos = 0;
    while (pos < data.Length)
    {
        int len = data[pos]+1;
        int num = data.ToUInt16 (1);
        pos += 3;
        for (int j = 0; j < len; ++j)
            data[pos+j] = Binary.RotByteR (data[pos+j], 4);
        mem.Write (data, pos, len);
        mem.WriteByte (0xD);
        mem.WriteByte (0xA);
        pos += len;
    }
    mem.Position = 0;
    return mem;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Mina/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
