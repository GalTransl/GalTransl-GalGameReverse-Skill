# Silky / ArcAWF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AWF` / `GameRes.Formats.Silky.AwfOpener` | `awf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AwfOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `AwfOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x20);` |
| `AwfOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x20);` |
| `AwfOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x24);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Silky.AwfOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {

    if (!file.Name.HasExtension (".awf"))
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 4;
    uint index_size = (uint)count*0x34;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    bool is_mp3 = VFS.IsPathEqualsToFileName (file.Name, "voice.awf");
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x20);
        if (is_mp3)
            name = Path.ChangeExtension (name, "mp3");
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x20);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x34;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Name.HasExtension (".mp3"))
        return base.OpenEntry (arc, entry);

    var header = new byte[0x2C];
    using (var mem = new MemoryStream (header))
    using (var wav = new BinaryWriter (mem))
    {
        wav.Write ("RIFF".ToCharArray());
        wav.Write ((uint)(entry.Size + 0x24u));
        wav.Write ("WAVE".ToCharArray());
        wav.Write ("fmt ".ToCharArray());
        wav.Write (0x10);
        wav.Write ((ushort)1);
        wav.Write ((ushort)2);
        wav.Write (22050);
        wav.Write (22050*4);
        wav.Write ((ushort)4);
        wav.Write ((ushort)16);
        wav.Write ("data".ToCharArray());
        wav.Write (entry.Size);
    }
    var pcm = arc.File.CreateStream (entry.Offset, entry.Size);
    return new PrefixStream (header, pcm);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Silky/ArcAWF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
