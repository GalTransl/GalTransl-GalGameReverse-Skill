# Nejii / ArcPCD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCD/NEJII` / `GameRes.Formats.Nejii.PcdOpener` | `pcd` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PcdOpener.TryOpen` | `ushort channels = file.View.ReadUInt16 (0x12);` |
| `PcdOpener.TryOpen` | `uint rate = file.View.ReadUInt32 (0x14);` |
| `PcdOpener.TryOpen` | `uint bps = file.View.ReadUInt32 (0x18);` |
| `PcdOpener.TryOpen` | `uint block_align = file.View.ReadUInt16 (0x1C);` |
| `PcdOpener.TryOpen` | `bps = file.View.ReadUInt16 (0x1E);` |
| `PcdOpener.TryOpen` | `var name = file.View.ReadString (offset, 0x10);` |
| `PcdOpener.TryOpen` | `entry.WaveFormat = file.View.ReadBytes (offset+0x10, 0x10);` |
| `PcdOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (entry.Offset) + 4;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nejii.PcdEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte[] WaveFormat ;
```

### GameRes.Formats.Nejii.PcdOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset < 0x30 || !file.Name.HasExtension (".pcd"))
        return null;

    ushort channels = file.View.ReadUInt16 (0x12);
    if (0 == channels || channels > 2)
        return null;
    uint rate = file.View.ReadUInt32 (0x14);
    uint bps = file.View.ReadUInt32 (0x18);
    uint block_align = file.View.ReadUInt16 (0x1C);
    if (block_align * rate != bps)
        return null;
    bps = file.View.ReadUInt16 (0x1E);
    if (bps != 8 && bps != 16)
        return null;

    long offset = 0;
    var dir = new List<Entry>();
    while (offset < file.MaxOffset)
    {
        var name = file.View.ReadString (offset, 0x10);
        var entry = FormatCatalog.Instance.Create<PcdEntry> (name);
        entry.WaveFormat = file.View.ReadBytes (offset+0x10, 0x10);
        entry.Offset = offset + 0x20;
        entry.Size = file.View.ReadUInt32 (entry.Offset) + 4;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        offset = entry.Offset+entry.Size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PcdEntry)entry;
    using (var riff_mem = new MemoryStream (0x2C))
    using (var riff = new BinaryWriter (riff_mem))
    {
        uint riff_size = entry.Size + 0x20;
        riff.Write (AudioFormat.Wav.Signature);
        riff.Write (riff_size);
        riff.Write (0x45564157);
        riff.Write (0x20746d66);
        riff.Write (0x10);
        riff.Write (pent.WaveFormat);
        riff.Write (0x61746164);
        riff.Flush();
        var header = riff_mem.ToArray();
        var pcm = arc.File.CreateStream (entry.Offset, entry.Size);
        return new PrefixStream (header, pcm);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Nejii/ArcPCD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
