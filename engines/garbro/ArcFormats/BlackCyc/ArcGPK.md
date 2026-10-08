# BlackCyc / ArcGPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GPK` / `GameRes.Formats.BlackCyc.GpkOpener` | `gpk` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GpkOpener.TryOpen` | `int count = gtb.View.ReadInt32 (0);` |
| `GpkOpener.TryOpen` | `uint next_offset = gtb.View.ReadUInt32 (offsets_index);` |
| `GpkOpener.TryOpen` | `int name_offset = name_base + gtb.View.ReadInt32 (name_index);` |
| `GpkOpener.TryOpen` | `string name = gtb.View.ReadString (name_offset, (uint)(gtb.MaxOffset-name_offset));` |
| `GpkOpener.TryOpen` | `next_offset = gtb.View.ReadUInt32 (offsets_index);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackCyc.GpkOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".gpk"))
        return null;
    var gtb_name = Path.ChangeExtension (file.Name, "gtb");
    if (!VFS.FileExists (gtb_name))
        return null;
    using (var gtb = VFS.OpenView (gtb_name))
    {
        int count = gtb.View.ReadInt32 (0);
        if (!IsSaneCount (count))
            return null;

        gtb.View.Reserve (0, (uint)gtb.MaxOffset);
        int name_index = 4;
        int offsets_index = name_index + count * 4;
        int name_base = offsets_index + count * 4;
        if (name_base >= gtb.MaxOffset)
            return null;
        uint next_offset = gtb.View.ReadUInt32 (offsets_index);
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            offsets_index += 4;
            int name_offset = name_base + gtb.View.ReadInt32 (name_index);
            name_index += 4;
            if (name_offset < name_base || name_offset >= gtb.MaxOffset)
                return null;
            string name = gtb.View.ReadString (name_offset, (uint)(gtb.MaxOffset-name_offset));
            name += ".dwq";
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = next_offset;
            if (i + 1 == count)
                next_offset = (uint)file.MaxOffset;
            else
                next_offset = gtb.View.ReadUInt32 (offsets_index);
            entry.Size = next_offset - (uint)entry.Offset;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/BlackCyc/ArcGPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
