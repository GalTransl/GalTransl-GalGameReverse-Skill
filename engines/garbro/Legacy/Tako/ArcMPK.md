# Tako / ArcMPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MPK/HG` / `GameRes.Formats.Tako.MpkOpener` | `mpk` | `48472d50`, `48472d57` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MpkOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `MpkOpener.TryOpen` | `bool has_sizes = file.View.ReadByte (3) != 'P';` |
| `MpkOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `MpkOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tako.MpkOpener

继承/接口：`ArchiveFormat`。

#### MpkOpener

```csharp
public MpkOpener () {
    Signatures = new uint[] { 0x502D4748, 0x572D4748 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count) || VFS.IsPathEqualsToFileName (file.Name, "00.mpk"))
        return null;
    var list_name = VFS.ChangeFileName (file.Name, "00.mpk");
    List<string> filelist;
    if (VFS.FileExists (list_name))
    {
        using (var s = VFS.OpenStream (list_name))
        using (var xs = new XoredStream (s, 0xA))
        using (var reader = new StreamReader (xs, Encodings.cp932))
        {
            filelist = new List<string> (count);
            string filename;
            while ((filename = reader.ReadLine()) != null)
                filelist.Add (filename);
        }
    }
    else
    {
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        filelist = Enumerable.Range (0, count).Select (x => string.Format ("{0}#{1:D4}", base_name, x)).ToList();
    }
    bool has_sizes = file.View.ReadByte (3) != 'P';
    uint index_offset = 8;
    uint record_size = has_sizes ? 8u : 4u;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = FormatCatalog.Instance.Create<Entry> (filelist[i]);
        entry.Offset = file.View.ReadUInt32 (index_offset);
        if (has_sizes)
        {
            entry.Size = file.View.ReadUInt32 (index_offset+4);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
        }
        else if (entry.Offset > file.MaxOffset)
            return null;
        dir.Add (entry);
        index_offset += record_size;
    }
    if (!has_sizes)
    {
        for (int i = 1; i < count; ++i)
        {
            dir[i-1].Size = (uint)(dir[i].Offset - dir[i-1].Offset);
        }
        dir[dir.Count-1].Size = (uint)(file.MaxOffset - dir[dir.Count-1].Offset);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../../ArcFormats/CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Tako/ArcMPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
