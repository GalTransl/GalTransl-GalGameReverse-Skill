# Eushully / ArcGPC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GPC` / `GameRes.Formats.Eushully.GpcOpener` | `gpc` | 无固定签名或来源表达式未解析 | `False` |
| `SND` / `GameRes.Formats.Eushully.SndOpener` | `snd` | 无固定签名或来源表达式未解析 | `False` |
| `SNR` / `GameRes.Formats.Eushully.SnrOpener` | `snr` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `HOpener.TryOpenWithIndex` | `int name_length = idx.View.ReadByte (idx_offset++);` |
| `HOpener.TryOpenWithIndex` | `entry.Offset = idx.View.ReadUInt32 (idx_offset);` |
| `SndOpener.OpenEntry` | `uint data_size = arc.File.View.ReadUInt32 (entry.Offset+0x11);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Eushully.HOpener

继承/接口：`ArchiveFormat`。

#### TryOpenWithIndex

```csharp
protected ArcFile TryOpenWithIndex (ArcView file, string entry_type, string entry_ext = "") {
    var ext = Path.GetExtension (file.Name).ToUpperInvariant();
    if (ext.Length != 4 || 'H' == ext[3])
        return null;

    var idx_name = Path.ChangeExtension (file.Name, string.Concat (ext.Substring (0, 3), "H"));
    if (!VFS.FileExists (idx_name))
        return null;

    using (var idx = VFS.OpenView (idx_name))
    {
        long idx_offset = 0;
        var name_buffer = new byte[0x40];
        var dir = new List<Entry>();
        while (idx_offset < idx.MaxOffset)
        {
            int name_length = idx.View.ReadByte (idx_offset++);
            if (name_length > name_buffer.Length)
                name_buffer = new byte[name_length];
            if (name_length != idx.View.Read (idx_offset, name_buffer, 0, (uint)name_length))
                return null;
            for (int i = 0; i < name_length; ++i)
                name_buffer[i] ^= 0xFF;
            var name = Encodings.cp932.GetString (name_buffer, 0, name_length);
            var entry = new Entry { Name = name + entry_ext, Type = entry_type };
            idx_offset += name_length;
            entry.Offset = idx.View.ReadUInt32 (idx_offset);
            if (entry.Offset > file.MaxOffset)
                return null;
            idx_offset += 4;
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        dir.Sort ((a, b) => (int)(a.Offset - b.Offset));
        for (int i = 0; i < dir.Count; ++i)
        {
            long next_offset = i+1 == dir.Count ? file.MaxOffset : dir[i+1].Offset;
            dir[i].Size = (uint)(next_offset - dir[i].Offset);
        }
        return new ArcFile (file, this, dir);
    }
}
```

### GameRes.Formats.Eushully.GpcOpener

继承/接口：`HOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    return TryOpenWithIndex (file, "image", ".gpcf");
}
```

### GameRes.Formats.Eushully.SndOpener

继承/接口：`HOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    return TryOpenWithIndex (file, "audio", ".wav");
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size < 0x16)
        return base.OpenEntry (arc, entry);

    var header = new byte[0x2C];
    LittleEndian.Pack (0x46464952, header, 0x0);
    LittleEndian.Pack (0x45564157, header, 0x8);
    LittleEndian.Pack (0x20746d66, header, 0xC);
    header[0x10] = 0x10;
    arc.File.View.Read (entry.Offset+1, header, 0x14, 0x10);
    LittleEndian.Pack (0x61746164, header, 0x24);
    uint data_size = arc.File.View.ReadUInt32 (entry.Offset+0x11);
    LittleEndian.Pack (data_size, header, 0x28);
    LittleEndian.Pack (data_size+0x24u, header, 4);
    var pcm = arc.File.CreateStream (entry.Offset+0x15, data_size);
    return new PrefixStream (header, pcm);
}
```

### GameRes.Formats.Eushully.SnrOpener

继承/接口：`HOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    return TryOpenWithIndex (file, "script");
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Eushully/ArcGPC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
