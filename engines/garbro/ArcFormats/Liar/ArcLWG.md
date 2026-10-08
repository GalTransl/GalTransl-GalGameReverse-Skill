# Liar / ArcLWG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LWG` / `GameRes.Formats.Liar.LwgOpener` | `lwg` | `4c470100` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LwgOpener.TryOpen` | `uint height = file.View.ReadUInt32 (4);` |
| `LwgOpener.TryOpen` | `uint width  = file.View.ReadUInt32 (8);` |
| `LwgOpener.TryOpen` | `int count   = file.View.ReadInt32 (12);` |
| `LwgOpener.TryOpen` | `uint dir_size = file.View.ReadUInt32 (20);` |
| `LwgOpener.TryOpen` | `uint data_size = file.View.ReadUInt32 (data_offset);` |
| `LwgOpener.TryOpen` | `entry.PosX = file.View.ReadInt32 (cur_offset);` |
| `LwgOpener.TryOpen` | `entry.PosY = file.View.ReadInt32 (cur_offset+4);` |
| `LwgOpener.TryOpen` | `entry.BPP = file.View.ReadByte (cur_offset+8);` |
| `LwgOpener.TryOpen` | `entry.Offset = data_offset + file.View.ReadUInt32 (cur_offset+9);` |
| `LwgOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (cur_offset+13);` |
| `LwgOpener.TryOpen` | `uint name_length = file.View.ReadByte (cur_offset+17);` |
| `LwgOpener.TryOpen` | `string name = file.View.ReadString (cur_offset+18, name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Liar.LwgImageEntry

继承/接口：`ImageEntry`。

#### 状态与常量

```csharp
public int PosX ;

public int PosY ;

public int BPP ;
```

### GameRes.Formats.Liar.LwgOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint height = file.View.ReadUInt32 (4);
    uint width  = file.View.ReadUInt32 (8);
    int count   = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;
    uint dir_size = file.View.ReadUInt32 (20);
    uint cur_offset = 24;
    uint data_offset = cur_offset + dir_size;
    uint data_size = file.View.ReadUInt32 (data_offset);
    data_offset += 4;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new LwgImageEntry();
        entry.PosX = file.View.ReadInt32 (cur_offset);
        entry.PosY = file.View.ReadInt32 (cur_offset+4);
        entry.BPP = file.View.ReadByte (cur_offset+8);
        entry.Offset = data_offset + file.View.ReadUInt32 (cur_offset+9);
        entry.Size = file.View.ReadUInt32 (cur_offset+13);

        uint name_length = file.View.ReadByte (cur_offset+17);
        string name = file.View.ReadString (cur_offset+18, name_length);
        entry.Name = name + ".wcg";
        cur_offset += 18+name_length;
        if (cur_offset > dir_size+24)
            return null;
        if (entry.Size > 0 && entry.CheckPlacement (data_offset + data_size))
            dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Liar/ArcLWG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
