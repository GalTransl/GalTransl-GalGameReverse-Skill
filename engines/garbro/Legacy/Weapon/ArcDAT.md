# Weapon / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/WEAPON` / `GameRes.Formats.Weapon.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

该入口只在来源 Debug 配置注册，不能当作 Release 工具的可用格式保证。

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Weapon.CgEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint     Width ;

public uint     Height ;
```

### GameRes.Formats.Weapon.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const uint DefaultWidth = 800 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name);
    Size[] dim_table;
    if (!KnownFileTables.TryGetValue (arc_name, out dim_table))
        return null;
    uint offset = 0;
    var base_name = Path.GetFileNameWithoutExtension (arc_name);
    var dir = new List<Entry> (dim_table.Length);
    for (int i = 0; i < dim_table.Length; ++i)
    {
        var name = string.Format ("{0}#{1:D4}", base_name, i);
        uint width = (uint)dim_table[i].Width;
        uint height = (uint)dim_table[i].Height;
        var entry = new CgEntry {
            Name = name,
            Type = "image",
            Offset = offset,
            Size = height * width * 2,
            Width = width,
            Height = height,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        offset += entry.Size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Weapon/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
