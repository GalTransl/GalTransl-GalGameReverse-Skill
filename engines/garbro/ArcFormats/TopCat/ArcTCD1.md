# TopCat / ArcTCD1：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `TCD1` / `GameRes.Formats.TopCat.Tcd1Opener` | `tcd` | `54434431` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Tcd1Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Tcd1Opener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `Tcd1Opener.TryOpen` | `uint names_offset = file.View.ReadUInt32 (12);` |
| `Tcd1Opener.TryOpen` | `offsets[i] = file.View.ReadUInt32 (pos) - (index_offset << ((i & 7) + 8));` |
| `Tcd1Opener.TryOpen` | `offsets[count] = file.View.ReadUInt32 (pos);` |
| `Tcd1Opener.TryOpen` | `var names = file.View.ReadBytes (names_offset, (uint)(file.MaxOffset - names_offset));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.TopCat.Tcd1Opener

继承/接口：`ArchiveFormat`。

#### Tcd1Opener

```csharp
public Tcd1Opener () {
    Extensions = new string[] { "tcd" };
    Signatures = new uint[] { 0x31444354 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = file.View.ReadUInt32 (8);
    uint names_offset = file.View.ReadUInt32 (12);

    uint pos = index_offset;
    var offsets = new uint[count+1];
    for (int i = 0; i < count; ++i)
    {
        offsets[i] = file.View.ReadUInt32 (pos) - (index_offset << ((i & 7) + 8));
        pos += 4;
    }
    offsets[count] = file.View.ReadUInt32 (pos);
    var names = file.View.ReadBytes (names_offset, (uint)(file.MaxOffset - names_offset));
    var dir = new List<Entry> (count);
    int name_start = 0;
    int entry_num = 0;
    for (int i = 0; i < names.Length; ++i)
    {
        if (names[i] != 0)
        {
            names[i] -= 0x57;
        }
        else
        {
            var name = Encodings.cp932.GetString (names, name_start, i - name_start);
            name_start = i+1;
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = offsets[entry_num];
            entry.Size = offsets[entry_num+1] - offsets[entry_num];
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            ++entry_num;
        }
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/TopCat/ArcTCD1.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
