# ArcFormats / ImageMNG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MNG` / `GameRes.Formats.MngOpener` | `mng` | `8a4d4e47` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MngOpener.TryOpen` | `uint chunk_size = Binary.BigEndian (input.ReadUInt32());` |
| `MngOpener.TryOpen` | `if (Binary.AsciiEqual (chunk_type, "MEND"))` |
| `MngOpener.TryOpen` | `if (Binary.AsciiEqual (chunk_type, "IHDR"))` |
| `MngOpener.TryOpen` | `else if (Binary.AsciiEqual (chunk_type, "IEND"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MngMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public long PngOffset ;
```

### GameRes.Formats.MngOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
ImageFormat MngFormat { get { return s_MngFormat.Value; } }

static readonly ResourceInstance<ImageFormat> s_MngFormat = new ResourceInstance<ImageFormat> ("MNG") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var input = file.CreateStream())
    {
        var info = MngFormat.ReadMetaData (input) as MngMetaData;
        if (null == info)
            return null;
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        long chunk_pos = info.PngOffset;
        var chunk_type = new byte[4];
        long ihdr_pos = 0;
        var dir = new List<Entry>();
        while (chunk_pos < file.MaxOffset)
        {
            input.Position = chunk_pos;
            uint chunk_size = Binary.BigEndian (input.ReadUInt32());
            input.Read (chunk_type, 0, 4);
            if (Binary.AsciiEqual (chunk_type, "MEND"))
                break;
            if (Binary.AsciiEqual (chunk_type, "IHDR"))
            {
                ihdr_pos = chunk_pos;
            }
            else if (Binary.AsciiEqual (chunk_type, "IEND"))
            {
                if (0 == ihdr_pos)
                    return null;
                var entry = new Entry {
                    Name = string.Format ("{0}#{1:D2}.png", base_name, dir.Count),
                    Type = "image",
                    Offset = ihdr_pos,
                    Size = (uint)(chunk_pos + chunk_size + 12 - ihdr_pos),
                };
                dir.Add (entry);
                ihdr_pos = 0;
            }
            chunk_pos += chunk_size + 12;
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ImageMNG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
