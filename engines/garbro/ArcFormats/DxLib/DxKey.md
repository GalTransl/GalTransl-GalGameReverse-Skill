# DxLib / DxKey：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DxLib.DxKey

继承/接口：`IDxKey`。

#### 状态与常量

```csharp
byte[]      m_pass ;

byte[]      m_key ;

public byte[] Password {
    get { return m_pass; }
    set { m_pass = value; m_key = null; }
}

public byte[] Key {
    get { return m_key ?? (m_key = CreateKey (m_pass)); }
    set { m_key = value; m_pass = RestoreKey (m_key); }
}
```

#### DxKey

```csharp
public DxKey (byte[] encoded) {
    Password = encoded;
}
```

#### GetEntryKey

```csharp
public virtual byte[] GetEntryKey (string name) {
    return Key;
}
```

#### CreateKey

```csharp
protected virtual byte[] CreateKey (byte[] keyword) {
    byte[] key;
    if (keyword == null || keyword.Length == 0)
    {
        key = Enumerable.Repeat<byte> (0xAA, 12).ToArray();
    }
    else
    {
        key = new byte[12];
        int byte_count = Math.Min (keyword.Length, 12);
        Buffer.BlockCopy (keyword, 0, key, 0, byte_count);
        if (byte_count < 12)
            Binary.CopyOverlapped (key, 0, byte_count, 12-byte_count);
    }
    key[0] ^= 0xFF;
    key[1]  = Binary.RotByteR (key[1], 4);
    key[2] ^= 0x8A;
    key[3]  = (byte)~Binary.RotByteR (key[3], 4);
    key[4] ^= 0xFF;
    key[5] ^= 0xAC;
    key[6] ^= 0xFF;
    key[7]  = (byte)~Binary.RotByteR (key[7], 3);
    key[8]  = Binary.RotByteL (key[8], 3);
    key[9] ^= 0x7F;
    key[10] = (byte)(Binary.RotByteR (key[10], 4) ^ 0xD6);
    key[11] ^= 0xCC;
    return key;
}
```

#### RestoreKey

```csharp
protected virtual byte[] RestoreKey (byte[] key) {
    var bin = key.Clone() as byte[];
    bin[0] ^= 0xFF;
    bin[1]  = Binary.RotByteL (bin[1], 4);
    bin[2] ^= 0x8A;
    bin[3]  = Binary.RotByteL ((byte)~bin[3], 4);
    bin[4] ^= 0xFF;
    bin[5] ^= 0xAC;
    bin[6] ^= 0xFF;
    bin[7]  = Binary.RotByteL ((byte)~bin[7], 3);
    bin[8]  = Binary.RotByteR (bin[8], 3);
    bin[9] ^= 0x7F;
    bin[10] = Binary.RotByteL ((byte)(bin[10] ^ 0xD6), 4);
    bin[11] ^= 0xCC;
    return bin;
}
```

#### CreateInstanceFromKey

```csharp
public static DxKey CreateInstanceFromKey (byte[] key) {
    var enc = new DxKey();
    enc.Key = key;
    return enc;
}
```

### GameRes.Formats.DxLib.DxKey8

继承/接口：`DxKey`。

#### 状态与常量

```csharp
int      m_codepage ;
```

#### DxKey8

```csharp
public DxKey8 (byte[] encoded, int codepage = 0) : base (encoded) {
    m_codepage = codepage;
}
```

#### GetEntryKey

```csharp
public override byte[] GetEntryKey (string name) {
    var password = this.Password;
    if (!string.IsNullOrEmpty (name))
    {
        var path = name.Split ('\\', '/');
        var append = string.Join ("", path.Reverse().Select (n => n.ToUpperInvariant()));
        var encoded = Encoding.GetEncoding (m_codepage).GetBytes (append);
        password = password.Concat (encoded).ToArray();
    }
    return CreateKey (password);
}
```

#### CreateKey

```csharp
protected override byte[] CreateKey (byte[] keyword) {

    int keylen = keyword.Length;
    if (keylen < 4)
    {
        Array.Resize (ref keyword, keylen + 8);
        keyword[keylen  ] = (byte)'D';
        keyword[keylen+1] = (byte)'X';
        keyword[keylen+2] = (byte)'L';
        keyword[keylen+3] = (byte)'I';
        keyword[keylen+4] = (byte)'B';
        keyword[keylen+5] = (byte)'A';
        keyword[keylen+6] = (byte)'R';
        keyword[keylen+7] = (byte)'C';
    }

    byte[] oddBuffer = new byte[(keyword.Length / 2) + (keyword.Length % 2)];
    int oddCounter = 0;
    byte[] evenBuffer = new byte[keyword.Length / 2];
    int evenCounter = 0;
    for (int i = 0; i < keyword.Length; i += 2, oddCounter++)
    {
        oddBuffer[oddCounter] = keyword[i];
    }
    for (int i = 1; i < keyword.Length; i += 2, evenCounter++)
    {
        evenBuffer[evenCounter] = keyword[i];
    }
    UInt32 crc_0, crc_1;
    crc_0 = Crc32.Compute (oddBuffer, 0, oddCounter);
    crc_1 = Crc32.Compute (evenBuffer, 0, evenCounter);

    byte[] key = new byte[7];
    byte[] crc_0_Bytes = BitConverter.GetBytes (crc_0);
    byte[] crc_1_Bytes = BitConverter.GetBytes (crc_1);
    key[0] = crc_0_Bytes[0];
    key[1] = crc_0_Bytes[1];
    key[2] = crc_0_Bytes[2];
    key[3] = crc_0_Bytes[3];
    key[4] = crc_1_Bytes[0];
    key[5] = crc_1_Bytes[1];
    key[6] = crc_1_Bytes[2];
    return key;

}
```

#### RestoreKey

```csharp
protected override byte[] RestoreKey (byte[] key) {
    throw new NotSupportedException ("CRC key cannot be restored.");
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/DxLib/DxKey.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
