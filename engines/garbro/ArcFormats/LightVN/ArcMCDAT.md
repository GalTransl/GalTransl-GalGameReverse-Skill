# LightVN / ArcMCDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MCDAT/LightVN` / `GameRes.Formats.LightVN.McdatOpener` | `mcdat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `McdatOpener.TryOpen` | `byte[] index = file.View.ReadBytes(0L, (uint)file.MaxOffset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.LightVN.McdatArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
private readonly Dictionary<string, string> mMap ;

private readonly string mRoot ;

private readonly byte[] mKey ;
```

#### McdatArchive

```csharp
public McdatArchive(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir,
                    Dictionary<string, string> map, string root, byte[] key)
        : base(arc, impl, dir) {
    this.mMap = map;
    this.mRoot = root;
    this.mKey = key;
}
```

#### GetFilePath

```csharp
public string GetFilePath(string name) {
    if (this.mMap.TryGetValue(name, out string relativePath))
    {
        return Path.Combine(this.mRoot, relativePath);
    }
    else
    {
        return string.Empty;
    }
}
```

#### RestoreSize

```csharp
public void RestoreSize() {
    foreach(Entry e in this.Dir)
    {
        string path = this.GetFilePath(e.Name);
        if(!string.IsNullOrEmpty(path) && System.IO.File.Exists(path))
        {
            FileInfo fi = new FileInfo(path);
            e.Size = (uint)fi.Length;
        }
    }
}
```

#### Decrypt

```csharp
public void Decrypt(byte[] data) {
    McdatArchive.Decrypt(data, this.mKey, 100);
}
```

#### Decrypt

```csharp
public static void Decrypt(byte[] data, byte[] key, int length) {
    int dataLen = data.Length;

    int decLen;
    if (length < 0)
    {
        decLen = dataLen;
    }
    else
    {
        decLen = Math.Min(dataLen, length);
    }

    for (int i = 1; i < decLen; ++i)
    {
        byte k = key[i % key.Length];
        data[dataLen - i] ^= k;
    }

    for (int i = 0; i < decLen; ++i)
    {
        byte k = key[i % key.Length];
        data[i] ^= k;
    }
}
```

### GameRes.Formats.LightVN.McdatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private static readonly string smIndexRelativePath = "\\Data\\_\\0.mcdat" ;

public static readonly byte[] DefaultKey = new byte[] {
    0x64, 0x36, 0x63, 0x35, 0x66, 0x4B, 0x49, 0x33, 0x47, 0x67, 0x42, 0x57, 0x70, 0x5A, 0x46, 0x33,
    0x54, 0x7A, 0x36, 0x69, 0x61, 0x33, 0x6B, 0x46, 0x30,
}
```

#### McdatOpener

```csharp
public McdatOpener() {
    Extensions = new string[] { "mcdat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.Name.EndsWith(smIndexRelativePath))
    {
        return null;
    }

    string root = file.Name.Remove(file.Name.Length - smIndexRelativePath.Length);
    byte[] key = this.QueryKey();

    byte[] index = file.View.ReadBytes(0L, (uint)file.MaxOffset);
    McdatArchive.Decrypt(index, key, -1);

    Dictionary<string, string> map = null;
    try
    {
        string json = Encoding.UTF8.GetString(index);
        map = JsonConvert.DeserializeObject<Dictionary<string, string>>(json);
    }
    catch
    {
        return null;
    }

    if (map == null)
    {
        return null;
    }

    List<Entry> entries = new List<Entry>(map.Count);
    foreach (string name in map.Keys)
    {
        Entry entry = Create<Entry>(name);
        entry.Offset = 0L;
        entry.Size = 0u;
        entries.Add(entry);
    }

    McdatArchive mcdatArc = new McdatArchive(file, this, entries, map, root, key);
    mcdatArc.RestoreSize();
    return mcdatArc;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    McdatArchive mcdatArc = (McdatArchive)arc;

    string path = mcdatArc.GetFilePath(entry.Name);
    if (!string.IsNullOrEmpty(path) && File.Exists(path))
    {
        byte[] data = File.ReadAllBytes(path);
        mcdatArc.Decrypt(data);
        return new MemoryStream(data, false);
    }
    return Stream.Null;
}
```

#### QueryKey

```csharp
private byte[] QueryKey() {
    return DefaultKey;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/LightVN/ArcMCDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
