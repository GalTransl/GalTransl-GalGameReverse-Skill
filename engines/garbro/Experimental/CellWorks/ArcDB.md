# CellWorks / ArcDB：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/IGS` / `GameRes.Formats.CellWorks.IgsDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CellWorks.IgsDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (VFS.IsVirtual || !file.Name.HasExtension (".dat"))
        return null;
    var db_files = VFS.GetFiles (VFS.CombinePath (VFS.GetDirectoryName (file.Name), "*.db"));
    if (!db_files.Any())
        return null;
    using (var igs = new IgsDbReader (file.Name))
    {
        foreach (var db_name in db_files.Select (e => e.Name))
        {
            int arc_id;
            if (igs.GetArchiveId (db_name, out arc_id))
            {
                var dir = igs.ReadIndex (arc_id);
                if (0 == dir.Count)
                    return null;
                return new ArcFile (file, this, dir);
            }
        }
        return null;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    using (var aes = Aes.Create())
    {
        var name_bytes = Encoding.UTF8.GetBytes (entry.Name);
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.PKCS7;
        aes.Key = CreateKey (32, name_bytes);
        aes.IV = CreateKey (16, name_bytes);
        using (var decryptor = aes.CreateDecryptor())
        using (var enc = arc.File.CreateStream (entry.Offset, 0x110))
        using (var input = new CryptoStream (enc, decryptor, CryptoStreamMode.Read))
        {
            var header = new byte[Math.Min (entry.Size, 0x100u)];
            input.Read (header, 0, header.Length);
            if (entry.Size <= 0x100)
                return new BinMemoryStream (header);
            var rest = arc.File.CreateStream (entry.Offset+0x110, entry.Size-0x100);
            return new PrefixStream (header, rest);
        }
    }
}
```

#### CreateKey

```csharp
internal static byte[] CreateKey (int length, byte[] src) {
    var key = new byte[length];
    Buffer.BlockCopy (src, 0, key, 0, Math.Min (src.Length, length));
    for (int i = length; i < src.Length; ++i)
        key[i % length] ^= src[i];
    return key;
}
```

### GameRes.Formats.CellWorks.IgsDbReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
SQLiteConnection    m_conn ;

SQLiteCommand       m_arc_cmd ;

bool _disposed = false ;
```

#### IgsDbReader

```csharp
public IgsDbReader (string arc_name) {
    m_conn = new SQLiteConnection();
    m_arc_cmd = m_conn.CreateCommand();
    m_arc_cmd.CommandText = @"SELECT id FROM archives WHERE name=?";
    m_arc_cmd.Parameters.Add (m_arc_cmd.CreateParameter());
    m_arc_cmd.Parameters[0].Value = Path.GetFileNameWithoutExtension (arc_name);
}
```

#### GetArchiveId

```csharp
public bool GetArchiveId (string db_name, out int arc_id) {
    foreach (var password in IgsDatOpener.KnownPasswords)
    {
        SQLiteConnectionStringBuilder csb = new SQLiteConnectionStringBuilder()
        {
            DataSource = db_name,
            ReadOnly = true,
            Password = password
        };
        m_conn.ConnectionString = csb.ConnectionString;
        m_conn.Open();
        try
        {
            using (var reader = m_arc_cmd.ExecuteReader())
            {
                if (reader.Read())
                {
                    arc_id = reader.GetInt32 (0);
                    return true;
                }
            }

            m_conn.Close();
            break;
        }
        catch (SQLiteException)
        {

        }
        m_conn.Close();
    }
    arc_id = -1;
    return false;
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex (int arc_id) {

    using (var cmd = m_conn.CreateCommand())
    {
        cmd.CommandText = @"SELECT filepath,offset,size FROM file_infos WHERE archiveID=?";
        cmd.Parameters.Add (cmd.CreateParameter());
        cmd.Parameters[0].Value = arc_id;
        using (var reader = cmd.ExecuteReader())
        {
            var dir = new List<Entry>();
            while (reader.Read())
            {
                var name = reader.GetString (0);
                var entry = FormatCatalog.Instance.Create<Entry> (name);
                entry.Offset = reader.GetInt64 (1);
                entry.Size = (uint)reader.GetInt32 (2);
                dir.Add (entry);
            }
            return dir;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Experimental/CellWorks/ArcDB.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
