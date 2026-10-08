# NScripter / ArcNS2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NS2` / `GameRes.Formats.NScripter.Ns2Opener` | `ns2` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Ns2Opener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (0);` |
| `Ns2Opener.ReadIndex` | `uint base_offset = input.ReadUInt32();` |
| `Ns2Opener.ReadIndex` | `entry.Size   = input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NScripter.Ns2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    List<Entry> dir = null;
    uint data_offset = file.View.ReadUInt32 (0);
    if (data_offset > 4 && data_offset < file.MaxOffset)
    {
        try
        {
            using (var input = file.CreateStream())
            {
                dir = ReadIndex (input);
                if (null != dir)
                    return new ArcFile (file, this, dir);
            }
        }
        catch {  }
    }
    if (!file.Name.HasExtension (".ns2"))
        return null;

    var password = QueryPassword();
    if (string.IsNullOrEmpty (password))
        return null;
    var key = Encoding.ASCII.GetBytes (password);

    using (var input = OpenEncryptedStream (file, key))
    {
        dir = ReadIndex (input);
        if (null == dir)
            return null;
        return new NsaEncryptedArchive (file, this, dir, key);
    }
}
```

#### ReadIndex

```csharp
protected List<Entry> ReadIndex (Stream file) {
    using (var input = new BinaryReader (file, Encodings.cp932, true))
    {
        uint base_offset = input.ReadUInt32();
        if (base_offset <= 4 || base_offset >= file.Length)
            return null;

        var name_buffer = new char[0x100];
        long current_offset = base_offset;
        var dir = new List<Entry>();
        while (file.Position < base_offset)
        {
            if (input.ReadChar() != '"')
                break;
            char c;
            int i = 0;
            while ((c = input.ReadChar()) != '"')
            {
                if (name_buffer.Length == i)
                    return null;
                name_buffer[i++] = c;
            }
            if (0 == i)
                return null;
            var name = new string (name_buffer, 0, i);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = current_offset;
            entry.Size   = input.ReadUInt32();
            if (!entry.CheckPlacement (file.Length))
                return null;
            current_offset += entry.Size;
            dir.Add (entry);
        }
        return dir.Count > 0 ? dir : null;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var nsa_arc = arc as NsaEncryptedArchive;
    if (null == nsa_arc)
    {
        return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    var encrypted = OpenEncryptedStream (arc.File, nsa_arc.Key);
    return new StreamRegion (encrypted, entry.Offset, entry.Size);
}
```

#### OpenEncryptedStream

```csharp
Stream OpenEncryptedStream (ArcView file, byte[] key) {
    if (key.Length < 96)
        return new EncryptedViewStream (file, key);
    else
        return new Ns2Stream (file, key);
}
```

#### QueryPassword

```csharp
private string QueryPassword () {
    var options = Query<NsaOptions> (arcStrings.ArcEncryptedNotice);
    return options.Password;
}
```

### GameRes.Formats.NScripter.Ns2Stream

继承/接口：`ViewStreamBase`。

#### 状态与常量

```csharp
byte[]          m_key ;

readonly Cryptography.MD5 MD5 = new Cryptography.MD5() ;

const int BlockSize   = 32 ;

byte[] m_seed = new byte[64] ;
```

#### Ns2Stream

```csharp
public Ns2Stream (ArcView mmap, byte[] key) : base (mmap) {
    m_key = key;
}
```

#### DecryptBlock

```csharp
protected override void DecryptBlock () {
    var temp = new byte[32];
    var hash = new byte[16];
    for (int src = 0; src < m_current_block_length; src += BlockSize)
    {
        int src2 = src + 16;
        int key1 = 0;
        int key2 = 48;

        Buffer.BlockCopy (m_current_block, src2, m_seed, 0,  16);
        Buffer.BlockCopy (m_key,           key1, m_seed, 16, 48);

        MD5.Initialize();
        MD5.Update (m_seed, 0, m_seed.Length);
        Buffer.BlockCopy (MD5.State, 0, hash, 0, 16);

        for (int j = 0; j < 16; ++j)
        {
            temp[j] = m_seed[j] = (byte)(hash[j] ^ m_current_block[src + j]);
        }

        Buffer.BlockCopy (m_key, key2, m_seed, 16, 48);

        MD5.Initialize();
        MD5.Update (m_seed, 0, m_seed.Length);
        Buffer.BlockCopy (MD5.State, 0, hash, 0, 16);

        for (int j = 0; j < 16; ++j)
        {
            temp[16 + j] = m_seed[j] = (byte)(hash[j] ^ m_current_block[src2 + j]);
        }

        Buffer.BlockCopy (m_key, key1, m_seed, 16, 48);

        MD5.Initialize();
        MD5.Update (m_seed, 0, m_seed.Length);
        Buffer.BlockCopy (MD5.State, 0, hash, 0, 16);

        Buffer.BlockCopy (temp, 16, m_current_block, src, 16);
        for (int j = 0; j < 16; ++j)
        {
            m_current_block[src2 + j] = (byte)(hash[j] ^ temp[j]);
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/NScripter/ArcNSA.cs](ArcNSA.md)：本页引用的随包算法资料。
- [ArcFormats/NScripter/EncryptedStream.cs](EncryptedStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/NScripter/ArcNS2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
