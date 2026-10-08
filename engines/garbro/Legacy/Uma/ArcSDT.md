# Uma / ArcSDT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SDT/UMA` / `GameRes.Formats.Uma.SdtOpener` | `sdt` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SdtOpener.TryOpen` | `int signature = file.View.ReadInt32 (0);` |
| `SdtOpener.TryOpen` | `int is_packed = input.ReadInt32();` |
| `SdtOpener.TryOpen` | `uint size = input.ReadUInt32();` |
| `SdtOpener.TryOpen` | `var name = input.ReadCString();` |
| `SdtOpener.TryOpen` | `entry.HeaderSize = input.ReadUInt32();` |
| `SdtOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (entry.Offset, snd_ent.HeaderSize);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Uma.SdtEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint HeaderSize ;
```

### GameRes.Formats.Uma.SdtOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".sdt"))
        return null;
    int signature = file.View.ReadInt32 (0);
    if (signature != 0 && signature != 1)
        return null;
    using (var input = file.CreateStream())
    {
        var dir = new List<Entry>();
        while (input.PeekByte() != -1)
        {
            int is_packed = input.ReadInt32();
            if (is_packed != 0 && is_packed != 1)
                return null;
            uint size = input.ReadUInt32();
            var name = input.ReadCString();
            if (string.IsNullOrWhiteSpace (name))
                return null;
            var entry = FormatCatalog.Instance.Create<SdtEntry> (name);
            entry.HeaderSize = input.ReadUInt32();
            entry.Size = entry.HeaderSize + size;
            entry.UnpackedSize = size;
            entry.Offset = input.Position;
            entry.IsPacked = is_packed != 0;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.ChangeType (AudioFormat.Wav);
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
    var snd_ent = (SdtEntry)entry;
    var header = arc.File.View.ReadBytes (entry.Offset, snd_ent.HeaderSize);
    using (var mem = new MemoryStream ((int)snd_ent.HeaderSize + 0x18))
    using (var fmt = new BinaryWriter (mem))
    {
        uint total_size = snd_ent.Size + 0x18;
        fmt.Write (AudioFormat.Wav.Signature);
        fmt.Write (total_size);
        fmt.Write (0x45564157);
        fmt.Write (0x20746d66);
        fmt.Write (header.Length);
        fmt.Write (header, 0, header.Length);
        fmt.Write (0x61746164);
        fmt.Write (snd_ent.UnpackedSize);
        fmt.Flush();
        header = mem.ToArray();
    }
    Stream input = arc.File.CreateStream (entry.Offset+snd_ent.HeaderSize, snd_ent.UnpackedSize);
    if (snd_ent.IsPacked)
        input = new LzssStream (input);
    return new PrefixStream (header, input);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Uma/ArcSDT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
