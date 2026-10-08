# Lune / ArcPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/LUNE` / `GameRes.Formats.Lune.PackOpener` | `dat`, `wda` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0);` |
| `PackOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `PackOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+4),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lune.PackOpener

继承/接口：`ArchiveFormat`。

#### PackOpener

```csharp
public PackOpener () {
    Extensions = new string[] { "dat", "wda" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint first_offset = file.View.ReadUInt32 (0);
    if (first_offset <= 8 || first_offset >= file.MaxOffset || 0 != (first_offset & 7))
        return null;
    int count = (int)(first_offset / 8);
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    string type = file.Name.HasAnyOfExtensions (".wda", ".bgm") ? "audio"
                : file.Name.HasExtension (".scr") ? "script"
                : "image";
    if (base_name == "pack")
        base_name = Path.GetExtension (file.Name).TrimStart ('.');
    uint index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D5}", base_name, i),
            Type = type,
            Offset = file.View.ReadUInt32 (index_offset),
            Size   = file.View.ReadUInt32 (index_offset+4),
        };
        if (entry.Offset < first_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        if (entry.Size > 0)
            dir.Add (entry);
        index_offset += 8;
    }
    if (dir.Count == 0 || dir[dir.Count-1].Offset + dir[dir.Count-1].Size != file.MaxOffset)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!arc.File.Name.HasAnyOfExtensions (".wda", ".bgm"))
        return base.OpenEntry (arc, entry);
    uint sample_rate = arc.File.Name.HasExtension (".bgm") ? 44100u : 22050u;
    var format = new WaveFormat {
        FormatTag = 1,
        Channels = 1,
        SamplesPerSecond = sample_rate,
        BlockAlign = 2,
        BitsPerSample = 16,
    };
    format.SetBPS();
    byte[] wav_header;
    using (var output = new MemoryStream (0x2C))
    {
        WaveAudio.WriteRiffHeader (output, format, entry.Size);
        wav_header = output.ToArray();
    }
    var pcm_data = arc.File.CreateStream (entry.Offset, entry.Size);
    return new PrefixStream (wav_header, pcm_data);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Lune/ArcPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
