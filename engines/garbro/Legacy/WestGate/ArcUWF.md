# WestGate / ArcUWF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `UWF` / `GameRes.Formats.WestGate.UwfOpener` | `uwf`, `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `UwfOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0x14FC);` |
| `UwfOpener.OpenEntry` | `uint fmt_size = arc.File.View.ReadUInt16 (entry.Offset);` |
| `UwfOpener.OpenEntry` | `uint pcm_size = arc.File.View.ReadUInt32 (entry.Offset+2+fmt_size);` |
| `UwfOpener.OpenEntry` | `var fmt = arc.File.View.ReadBytes (entry.Offset+2, fmt_size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.WestGate.UwfOpener

继承/接口：`ArchiveFormat`。

#### UwfOpener

```csharp
public UwfOpener () {
    Extensions = new[] { "uwf", "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 0x1500)
        return null;
    uint first_offset = file.View.ReadUInt32 (0x14FC);
    if (first_offset >= file.MaxOffset || first_offset < 0x1500)
        return null;
    int count = (int)((first_offset - 0x14F0) / 0x10);
    if (!IsSaneCount (count))
        return null;
    var dir = UcaTool.ReadIndex (file, 0x14F0, count, "audio");
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    uint fmt_size = arc.File.View.ReadUInt16 (entry.Offset);
    if (fmt_size >= entry.Size)
        return base.OpenEntry (arc, entry);
    uint pcm_size = arc.File.View.ReadUInt32 (entry.Offset+2+fmt_size);
    if (pcm_size >= entry.Size)
        return base.OpenEntry (arc, entry);
    using (var mem = new MemoryStream())
    using (var riff = new BinaryWriter (mem))
    {
        uint total_size = (uint)(0x1C + fmt_size + pcm_size);
        riff.Write (AudioFormat.Wav.Signature);
        riff.Write (total_size);
        riff.Write (0x45564157);
        riff.Write (0x20746d66);
        riff.Write (fmt_size);
        var fmt = arc.File.View.ReadBytes (entry.Offset+2, fmt_size);
        riff.Write (fmt);
        riff.Write (0x61746164);
        riff.Flush();
        var wav_header = mem.ToArray();
        var pcm = arc.File.CreateStream (entry.Offset+fmt_size+2, pcm_size+4);
        return new PrefixStream (wav_header, pcm);
    }
}
```

## 配套算法与外部条件

- [Legacy/WestGate/ArcUCA.cs](ArcUCA.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/WestGate/ArcUWF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
