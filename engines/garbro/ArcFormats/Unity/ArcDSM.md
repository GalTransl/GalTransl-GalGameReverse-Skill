# Unity / ArcDSM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DSM/UNITY` / `GameRes.Formats.Unity.DsmOpener` | `dsm` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DsmOpener.TryOpen` | `\|\| (file.View.ReadUInt32 (0) & 0xFFFFFF) != 0xBFBBEF)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.DsmOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const string DefaultPassword = "pass" ;

static readonly byte[] DefaultSalt = Encoding.UTF8.GetBytes("saltは必ず8バイト以上") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "data.dsm")
        || (file.View.ReadUInt32 (0) & 0xFFFFFF) != 0xBFBBEF)
        return null;

    var dir = new List<Entry> {
        new Entry {
            Name = "data.txt",
            Type = "script",
            Offset = 0,
            Size = (uint)file.MaxOffset / 4 * 3,
        }
    };
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    using (var input = arc.File.CreateStream())
    using (var reader = new StreamReader (input))
    {
        var sourceString = reader.ReadToEnd();
        var text = DecryptString (sourceString, DefaultPassword);
        return new BinMemoryStream (text, entry.Name);
    }
}
```

#### DecryptString

```csharp
static byte[] DecryptString (string sourceString, string password) {
    var rijndaelManaged = new RijndaelManaged();
    byte[] key, iv;
    GenerateKeyFromPassword (password, rijndaelManaged.KeySize, out key, rijndaelManaged.BlockSize, out iv);
    rijndaelManaged.Key = key;
    rijndaelManaged.IV = iv;
    var array = Convert.FromBase64String (sourceString);
    using (var cryptoTransform = rijndaelManaged.CreateDecryptor())
    {
        return cryptoTransform.TransformFinalBlock (array, 0, array.Length);
    }
}
```

#### GenerateKeyFromPassword

```csharp
static void GenerateKeyFromPassword (string password, int keySize, out byte[] key, int blockSize, out byte[] iv) {
    var rfc2898DeriveBytes = new Rfc2898DeriveBytes (password, DefaultSalt);
    rfc2898DeriveBytes.IterationCount = 1000;
    key = rfc2898DeriveBytes.GetBytes (keySize / 8);
    iv = rfc2898DeriveBytes.GetBytes (blockSize / 8);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Unity/ArcDSM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
