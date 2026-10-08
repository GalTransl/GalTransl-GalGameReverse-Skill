# Musica / ArcMIP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MIP` / `GameRes.Formats.Musica.MipOpener` | `mip` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MipOpener.GetSizesFromExe` | `uint size = exe_file.View.ReadUInt32(table_ofs + 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Musica.MipOpener

继承/接口：`ArchiveFormat`。

#### MipOpener

```csharp
public MipOpener() {
    Extensions = new string[] { "mip" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    string extension;
    uint[] sizes;

    string basename = Path.GetFileName(file.Name).ToLower();
    if (basename == "res.mip") {
        extension = ".png";
        sizes = GetSizesFromExe(file, 0);
    }
    else if (basename == "sc.mip") {
        extension = "";
        sizes = GetSizesFromExe(file, 1);
    }
    else
        return null;

    int count = sizes.Length;
    var dir = new List<Entry>(count);
    uint offset = 0;
    for (int i = 0; i < count; i++) {
        var entry = new Entry {
            Name = i.ToString("D4") + extension,
            Type = extension == "" ? "script" : "image",
            Offset = offset,
            Size = sizes[i]
        };
        if (!entry.CheckPlacement(file.MaxOffset))
            return null;
        dir.Add(entry);
        offset += entry.Size;
    }

    return new ArcFile(file, this, dir);
}
```

#### GetSizesFromExe

```csharp
uint[] GetSizesFromExe(ArcView file, int type) {
    foreach (var exe_name in KnownGameMap.Keys) {
        if (VFS.FileExists(exe_name)) {
            using (var exe_file = VFS.OpenView(exe_name)) {
                var exe = new ExeFile(exe_file);
                long table_ofs = exe.GetAddressOffset(KnownGameMap[exe_name][type]);
                var sizes = new List<uint>();
                while (table_ofs < exe_file.MaxOffset) {

                    uint size = exe_file.View.ReadUInt32(table_ofs + 4);
                    if (size == 0)
                        break;
                    sizes.Add(size);
                    table_ofs += 8;
                }
                return sizes.ToArray();
            }
        }
    }
    throw new FileNotFoundException();
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var s = new XoredStream(arc.File.CreateStream(entry.Offset, entry.Size), 0xFF);
    if (entry.Name.EndsWith(".png"))
        return new PrefixStream(PngFormat.HeaderBytes, s);
    return s;
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Musica/ArcMIP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
