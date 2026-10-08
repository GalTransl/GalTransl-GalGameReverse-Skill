# KiriKiri / ArcTLG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `TLG` / `GameRes.Formats.KiriKiri.TlgOpener` | `tlg` | `544c4771` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `TlgOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "TLGqoi") \|\| !file.View.AsciiEqual (7, "raw"))` |
| `TlgOpener.TryOpen` | `var entry_signature = file.View.ReadInt32 (offset);` |
| `TlgOpener.TryOpen` | `var entry_size = file.View.ReadInt32 (offset+4);` |
| `TlgOpener.TryOpen` | `qhdr = file.View.ReadBytes (offset, (uint)entry_size);` |
| `TlgOpener.TryOpen` | `var layer_count = qhdr.ToInt32 (4);` |
| `TlgOpener.TryOpen` | `var block_count = qhdr.ToInt32 (12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KiriKiri.TlgLayerEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int Index ;
```

### GameRes.Formats.KiriKiri.TlgOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<ImageFormat> s_TlgFormat = new ResourceInstance<ImageFormat> ("TLG") ;
```

#### TlgOpener

```csharp
public TlgOpener () {
    Extensions = new string[] { "tlg" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "TLGqoi") || !file.View.AsciiEqual (7, "raw"))
        return null;
    var qhdr = Array.Empty<byte> ();
    var offset = 0x14;
    while (true)
    {
        var entry_signature = file.View.ReadInt32 (offset);
        var entry_size = file.View.ReadInt32 (offset+4);
        offset += 8;
        if (0x52444851 == entry_signature)
        {
            if (0x30 != entry_size)
                return null;
            qhdr = file.View.ReadBytes (offset, (uint)entry_size);
            if (entry_size != qhdr.Length)
                return null;
            offset += entry_size;
        }
        else if (0 == entry_signature && 0 == entry_size)
            break;
        else
            return null;
    }
    if (0 == qhdr.Length)
        return null;
    var layer_count = qhdr.ToInt32 (4);
    if (layer_count < 1)
        return null;
    var block_count = qhdr.ToInt32 (12);
    if (0 == block_count)
        return null;
    var dir = new List<Entry> (layer_count);
    for (var i = 0; i < layer_count; i++)
    {
        dir.Add (new TlgLayerEntry
        {
            Name = string.Format ("{0}#{1:D3}.tlg", Path.GetFileNameWithoutExtension (file.Name), i),
            Offset = 0,
            Size = (uint)file.MaxOffset,
            Type = "image",
            Index = i,
        });
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/KiriKiri/ArcTLG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
