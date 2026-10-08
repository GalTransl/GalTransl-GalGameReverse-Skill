# MAI / ArcMAI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MAI` / `GameRes.Formats.MAI.ArcOpener` | `arc` | `4d41490a` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `uint file_size = file.View.ReadUInt32 (4);` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `ArcOpener.TryOpen` | `int dir_level = file.View.ReadByte (0x0d);` |
| `ArcOpener.TryOpen` | `int dir_entries = file.View.ReadUInt16 (0x0e);` |
| `ArcOpener.TryOpen` | `Name = file.View.ReadString (dir_offset, 4),` |
| `ArcOpener.TryOpen` | `Index = file.View.ReadInt32 (dir_offset+4)` |
| `ArcOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x10);` |
| `ArcOpener.TryOpen` | `var offset = file.View.ReadUInt32 (index_offset+0x10);` |
| `ArcOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (offset);` |
| `ArcOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+0x14);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MAI.ArcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<ImageFormat> s_AmFormat  = new ResourceInstance<ImageFormat> ("AM/MAI") ;

static readonly ResourceInstance<ImageFormat> s_CmFormat  = new ResourceInstance<ImageFormat> ("CM/MAI") ;

static readonly ResourceInstance<ImageFormat> s_MskFormat = new ResourceInstance<ImageFormat> ("MSK/MAI") ;
```

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint file_size = file.View.ReadUInt32 (4);
    if (file_size != file.MaxOffset)
        return null;
    int count = file.View.ReadInt32 (8);
    if (count <= 0 || count > 0xfffff)
        return null;
    int dir_level = file.View.ReadByte (0x0d);
    int dir_entries = file.View.ReadUInt16 (0x0e);
    uint index_offset = 0x10;
    uint index_size = (uint)(count * 0x18 + dir_entries * 8);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    List<DirEntry> folders = null;
    if (0 != dir_entries && 2 == dir_level)
    {
        folders = new List<DirEntry> (dir_entries);
        uint dir_offset = index_offset + (uint)count*0x18;
        for (int i = 0; i < dir_entries; ++i)
        {
            folders.Add (new DirEntry {
                Name = file.View.ReadString (dir_offset, 4),
                Index = file.View.ReadInt32 (dir_offset+4)
            });
            dir_offset += 8;
        }
    }
    bool is_mask_arc = VFS.IsPathEqualsToFileName (file.Name, "mask.arc");
    var dir = new List<Entry> (count);
    int next_folder = null == folders ? count : folders[0].Index;
    int folder = 0;
    string current_folder = "";
    for (int i = 0; i < count; ++i)
    {
        while (i >= next_folder && folder < folders.Count)
        {
            current_folder = folders[folder++].Name;
            if (folders.Count == folder)
                next_folder = count;
            else
                next_folder = folders[folder].Index;
        }
        string name = file.View.ReadString (index_offset, 0x10);
        if (0 == name.Length)
            return null;
        var offset = file.View.ReadUInt32 (index_offset+0x10);
        var entry = new AutoEntry (Path.Combine (current_folder, name), () => {
            if (is_mask_arc)
                return s_MskFormat.Value;
            uint signature = file.View.ReadUInt32 (offset);
            switch (signature & 0xFFFF)
            {
            case 0x4D43: return s_CmFormat.Value;
            case 0x4D41: return s_AmFormat.Value;
            case 0x4D42: return ImageFormat.Bmp;
            default: return AutoEntry.DetectFileType (signature);
            }
        });
        entry.Offset = offset;
        entry.Size = file.View.ReadUInt32 (index_offset+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.MAI.ArcOpener.DirEntry

#### 状态与常量

```csharp
public string Name ;

public int    Index ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MAI/ArcMAI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
