# Musica / ArcANI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ANI/PAZ` / `GameRes.Formats.Musica.AniOpener` | `ani` | `00010400`, `00010200` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AniOpener.TryOpen` | `if (file.View.ReadUInt16 (0) != 0x100)` |
| `AniOpener.TryOpen` | `int count = file.View.ReadInt16 (2);` |
| `AniOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != 0)` |
| `AniOpener.TryOpen` | `var name = input.ReadCString();` |
| `AniOpener.TryOpen` | `uint width  = input.ReadUInt16();` |
| `AniOpener.TryOpen` | `uint height = input.ReadUInt16();` |
| `AniOpener.TryOpen` | `ushort bpp  = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Musica.AniOpener

继承/接口：`ArchiveFormat`。

#### AniOpener

```csharp
public AniOpener () {
    Signatures = new uint[] { 0x040100, 0x020100, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt16 (0) != 0x100)
        return null;
    int count = file.View.ReadInt16 (2);
    if (!IsSaneCount (count))
        return null;
    if (file.View.ReadUInt32 (4) != 0)
        return null;
    using (var input = file.CreateStream())
    {
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        input.Position = 8;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = input.ReadCString();
            if (string.IsNullOrWhiteSpace (name))
                return null;
            var entry = new Entry {
                Name = string.Format ("{0}#{1}", base_name, name),
                Type = "image",
                Offset = input.Position,
            };
            uint width  = input.ReadUInt16();
            uint height = input.ReadUInt16();
            ushort bpp  = input.ReadUInt16();
            entry.Size = width * height * bpp / 8 + 10;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            input.Position = entry.Offset + entry.Size;
        }
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Musica/ArcANI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
