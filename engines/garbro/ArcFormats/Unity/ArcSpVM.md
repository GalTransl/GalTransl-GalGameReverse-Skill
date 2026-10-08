# Unity / ArcSpVM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BYTES/UNITY` / `GameRes.Formats.Unity.BytesOpener` | `bytes` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.BytesOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.EndsWith ("DAT.bytes", StringComparison.OrdinalIgnoreCase))
        return null;
    var inf_name = file.Name.Substring (0, file.Name.Length - "DAT.bytes".Length);
    inf_name += "INF.bytes";
    if (!VFS.FileExists (inf_name))
        return null;
    using (var inf = VFS.OpenStream (inf_name))
    {
        var bin = new BinaryFormatter { Binder = new SpTypeBinder() };
        var list = bin.Deserialize (inf) as List<LinkerInfo>;
        if (null == list || 0 == list.Count)
            return null;
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        string type = "";
        if (base_name.StartsWith ("WAVE", StringComparison.OrdinalIgnoreCase))
            type = "audio";
        else if (base_name.StartsWith ("CG", StringComparison.OrdinalIgnoreCase))
            type = "image";
        var dir = list.Select (e => new Entry {
            Name = e.name, Type = type, Offset = e.offset, Size = (uint)e.size
        }).ToList();
        return new ArcFile (file, this, dir);
    }
}
```

### GameRes.Formats.Unity.LinkerInfo

#### 状态与常量

```csharp
public string   name { get; set; }

public int    offset { get; set; }

public int      size { get; set; }
```

### GameRes.Formats.Unity.SpTypeBinder

继承/接口：`SerializationBinder`。

#### BindToType

```csharp
public override Type BindToType (string assemblyName, string typeName) {
    if ("Assembly-CSharp" == assemblyName && "SpVM.Library.LinkerInfo" == typeName)
    {
        return typeof(LinkerInfo);
    }
    if (assemblyName.StartsWith ("mscorlib,") && typeName.StartsWith ("System.Collections.Generic.List`1[[SpVM.Library.LinkerInfo"))
    {
        return typeof(List<LinkerInfo>);
    }
    return null;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Unity/ArcSpVM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
