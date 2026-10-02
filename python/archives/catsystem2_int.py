"""CatSystem2 INT archive (KIF) index parsing, member decryption and exe passphrase recovery.
Sources: msg-tool, src/scripts/cat_system/archive/int.rs, twister.rs, int_password.rs
(f72716cee88554d40c1cdface2812493b14ca653; GPL-3.0-or-later);
GARbro, ArcFormats/CatSystem/ArcINT.cs OpenEncrypted/DecipherName/GetPassFromExe and
ArcFormats/Blowfish.cs (MIT, Copyright morkt).
Both upstreams agree on the encrypted layout: 8-byte header, first index slot is a
plaintext `__key__.dat` name, entries are 0x48-byte records starting at 0x50, the entry
index is added to the stored offset before Blowfish decryption, an MT19937-variant seeded
by the u32 at 0x4C derives the 4-byte Blowfish key, per-entry names are
substitution-ciphered with the MT reseeded by key+i, and member data is Blowfish ECB with
little-endian block I/O (only size/8*8 bytes are transformed). The passphrase key is
CRC32-normal (MSB-first, no final xor) of the CP932 passphrase, recoverable from the game
exe's V_CODE2/DATA resource, itself Blowfish-LE encrypted with the KEY_CODE/KEY resource
XORed with 0xCD (default "windmill"). Member bytes then feed
python/engines/catsystem2.read_cst.
"""
from dataclasses import dataclass, field
import io
import os
import struct

_MAGIC = b"KIF\0"
_KEY_ENTRY = b"__key__.dat\0"
_ENTRY_RECORD = 0x48
_NAME_FIELD = 0x40
_NAME_SIZES = (0x20, 0x40)
_MAX_ENTRIES = 1 << 22
_MAX_INDEX = 512 * 1024 * 1024
_MAX_MEMBER = 256 * 1024 * 1024
_MAX_EXE = 256 * 1024 * 1024
_DEFAULT_EXE_KEY = b"windmill"

# Blowfish initial P-array and S-boxes: the first 1042 words of pi's hex expansion.
_BLOWFISH_HEX = (
    "243f6a8885a308d313198a2e03707344a4093822299f31d0082efa98ec4e6c89452821e6"
    "38d01377be5466cf34e90c6cc0ac29b7c97c50dd3f84d5b5b54709179216d5d98979fb1b"
    "d1310ba698dfb5ac2ffd72dbd01adfb7b8e1afed6a267e96ba7c9045f12c7f9924a19947"
    "b3916cf70801f2e2858efc16636920d871574e69a458fea3f4933d7e0d95748f728eb658"
    "718bcd5882154aee7b54a41dc25a59b59c30d5392af26013c5d1b023286085f0ca417918"
    "b8db38ef8e79dcb0603a180e6c9e0e8bb01e8a3ed71577c1bd314b2778af2fda55605c60"
    "e65525f3aa55ab945748986263e8144055ca396a2aab10b6b4cc5c341141e8cea15486af"
    "7c72e993b3ee1411636fbc2a2ba9c55d741831f6ce5c3e169b87931eafd6ba336c24cf5c"
    "7a325381289586773b8f48986b4bb9afc4bfe81b6628219361d809ccfb21a991487cac60"
    "5dec8032ef845d5de98575b1dc262302eb651b8823893e81d396acc50f6d6ff383f44239"
    "2e0b4482a484200469c8f04a9e1f9b5e21c66842f6e96c9a670c9c61abd388f06a51a0d2"
    "d8542f68960fa728ab5133a36eef0b6c137a3be4ba3bf0507efb2a98a1f1651d39af0176"
    "66ca593e82430e888cee8619456f9fb47d84a5c33b8b5ebee06f75d885c12073401a449f"
    "56c16aa64ed3aa62363f77061bfedf72429b023d37d0d724d00a1248db0fead349f1c09b"
    "075372c980991b7b25d479d8f6e8def7e3fe501ab6794c3b976ce0bd04c006bac1a94fb6"
    "409f60c45e5c9ec2196a246368fb6faf3e6c53b51339b2eb3b52ec6f6dfc511f9b30952c"
    "cc814544af5ebd09bee3d004de334afd660f2807192e4bb3c0cba85745c8740fd20b5f39"
    "b9d3fbdb5579c0bd1a60320ad6a100c6402c7279679f25fefb1fa3cc8ea5e9f8db3222f8"
    "3c7516dffd616b152f501ec8ad0552ab323db5fafd23876053317b483e00df829e5c57bb"
    "ca6f8ca01a87562edf1769dbd542a8f6287effc3ac6732c68c4f5573695b27b0bbca58c8"
    "e1ffa35db8f011a010fa3d98fd2183b84afcb56c2dd1d35b9a53e479b6f84565d28e49bc"
    "4bfb9790e1ddf2daa4cb7e3362fb1341cee4c6e8ef20cada36774c01d07e9efe2bf11fb4"
    "95dbda4dae909198eaad8e716b93d5a0d08ed1d0afc725e08e3c5b2f8e7594b78ff6e2fb"
    "f2122b648888b812900df01c4fad5ea0688fc31cd1cff191b3a8c1ad2f2f2218be0e1777"
    "ea752dfe8b021fa1e5a0cc0fb56f74e818acf3d6ce89e299b4a84fe0fd13e0b77cc43b81"
    "d2ada8d9165fa2668095770593cc7314211a1477e6ad206577b5fa86c75442f5fb9d35cf"
    "ebcdaf0c7b3e89a0d6411bd3ae1e7e4900250e2d2071b35e226800bb57b8e0af2464369b"
    "f009b91e5563911d59dfa6aa78c14389d95a537f207d5ba202e5b9c5832603766295cfa9"
    "11c819684e734a41b3472dca7b14a94a1b5100529a532915d60f573fbc9bc6e42b60a476"
    "81e6740008ba6fb5571be91ff296ec6b2a0dd915b6636521e7b9f9b6ff34052ec5855664"
    "53b02d5da99f8fa108ba47996e85076a4b7a70e9b5b32944db75092ec4192623ad6ea6b0"
    "49a7df7d9cee60b88fedb266ecaa8c71699a17ff5664526cc2b19ee1193602a575094c29"
    "a0591340e4183a3e3f54989a5b429d656b8fe4d699f73fd6a1d29c07efe830f54d2d38e6"
    "f0255dc14cdd20868470eb266382e9c6021ecc5e09686b3f3ebaefc93c9718146b6a70a1"
    "687f358452a0e286b79c5305aa5007373e07841c7fdeae5c8e7d44ec5716f2b8b03ada37"
    "f0500c0df01c1f040200b3ffae0cf51a3cb574b225837a58dc0921bdd19113f97ca92ff6"
    "9432477322f547013ae5e58137c2dadcc8b576349af3dda7a94461460fd0030eecc8c73e"
    "a4751e41e238cd993bea0e2f3280bba1183eb3314e548b384f6db9086f420d03f60a04bf"
    "2cb8129024977c795679b072bcaf89afde9a771fd9930810b38bae12dccf3f2e5512721f"
    "2e6b7124501adde69f84cd877a5847187408da17bc9f9abce94b7d8cec7aec3adb851dfa"
    "63094366c464c3d2ef1c18473215d908dd433b3724c2ba1612a14d432a65c45150940002"
    "133ae4dd71dff89e10314e5581ac77d65f11199b043556f1d7a3c76b3c11183b5924a509"
    "f28fe6ed97f1fbfa9ebabf2c1e153c6e86e34570eae96fb1860e5e0a5a3e2ab3771fe71c"
    "4e3d06fa2965dcb999e71d0f803e89d65266c8252e4cc9789c10b36ac6150eba94e2ea78"
    "a5fc3c531e0a2df4f2f74ea7361d2b3d1939260f19c279605223a708f71312b6ebadfe6e"
    "eac31f66e3bc4595a67bc883b17f37d1018cff28c332ddefbe6c5aa56558218568ab9802"
    "eecea50fdb2f953b2aef7dad5b6e2f841521b62829076170ecdd4775619f151013cca830"
    "eb61bd960334fe1eaa0363cfb5735c904c70a239d59e9e0bcbaade14eecc86bc60622ca7"
    "9cab5cabb2f3846e648b1eaf19bdf0caa02369b9655abb5040685a323c2ab4b3319ee9d5"
    "c021b8f79b540b19875fa09995f7997e623d7da8f837889a97e32d7711ed935f16681281"
    "0e358829c7e61fd696dedfa17858ba9957f584a51b2272639b83c3ff1ac24696cdb30aeb"
    "532e30548fd948e46dbc312858ebf2ef34c6ffeafe28ed61ee7c3c735d4a14d9e864b7e3"
    "42105d14203e13e045eee2b6a3aaabeadb6c4f15facb4fd0c742f442ef6abbb5654f3b1d"
    "41cd2105d81e799e86854dc7e44b476a3d816250cf62a1f25b8d2646fc8883a0c1c7b6a3"
    "7f1524c369cb749247848a0b5692b285095bbf00ad19489d1462b17423820e0058428d2a"
    "0c55f5ea1dadf43e233f70613372f0928d937e41d65fecf16c223bdb7cde3759cbee7460"
    "4085f2a7ce77326ea607808419f8509ee8efd85561d99735a969a7aac50c06c25a04abfc"
    "800bcadc9e447a2ec3453484fdd567050e1e9ec9db73dbd3105588cd675fda79e3674340"
    "c5c43465713e38d83d28f89ef16dff20153e21e78fb03d4ae6e39f2bdb83adf7e93d5a68"
    "948140f7f64c261c94692934411520f77602d4f7bcf46b2ed4a20068d40824713320f46a"
    "43b7d4b7500061af1e39f62e9724454614214f74bf8b88404d95fc1d96b591af70f4ddd3"
    "66a02f45bfbc09ec03bd97857fac6dd031cb850496eb27b355fd3941da2547e6abca0a9a"
    "28507825530429f40a2c86dae9b66dfb68dc1462d7486900680ec0a427a18dee4f3ffea2"
    "e887ad8cb58ce0067af4d6b6aace1e7cd3375fecce78a399406b2a4220fe9e35d9f385b9"
    "ee39d7ab3b124e8b1dc9faf74b6d185626a36631eae397b23a6efa74dd5b43326841e7f7"
    "ca7820fbfb0af54ed8feb397454056acba48952755533a3a20838d87fe6ba9b7d096954b"
    "55a867bca1159a58cca9296399e1db33a62a4a563f3125f95ef47e1c9029317cfdf8e802"
    "04272f7080bb155c05282ce395c11548e4c66d2248c1133fc70f86dc07f9c9ee41041f0f"
    "404779a45d886e17325f51ebd59bc0d1f2bcc18f41113564257b7834602a9c60dff8e8a3"
    "1f636c1b0e12b4c202e1329eaf664fd1cad181156b2395e0333e92e13b240b62eebeb922"
    "85b2a20ee6ba0d99de720c8c2da2f728d012784595b794fd647d0862e7ccf5f05449a36f"
    "877d48fac39dfd27f33e8d1e0a476341992eff743a6f6eabf4f8fd37a812dc60a1ebddf8"
    "991be14cdb6e6b0dc67b55106d672c372765d43bdcd0e804f1290dc7cc00ffa3b5390f92"
    "690fed0b667b9ffbcedb7d9ca091cf0bd9155ea3bb132f88515bad247b9479bf763bd6eb"
    "37392eb3cc1159798026e297f42e312d6842ada7c66a2b3b12754ccc782ef11c6a124237"
    "b79251e706a1bbe64bfb63501a6b101811caedfa3d25bdd8e2e1c3c9444216590a121386"
    "d90cec6ed5abea2a64af674eda86a85fbebfe98864e4c3fe9dbc8057f0f7c08660787bf8"
    "6003604dd1fd8346f6381fb07745ae04d736fccc83426b33f01eab71b08041873c005e5f"
    "77a057bebde8ae2455464299bf582e614e58f48ff2ddfda2f474ef388789bdc25366f9c3"
    "c8b38e74b475f25546fcd9b97aeb26618b1ddf84846a0e79915f95e2466e598e20b45770"
    "8cd55591c902de4cb90bace1bb8205d011a862487574a99eb77f19b6e0a9dc09662d09a1"
    "c4324633e85a1f0209f0be8c4a99a0251d6efe101ab93d1d0ba5a4dfa186f20f2868f169"
    "dcb7da83573906fea1e2ce9b4fcd7f5250115e01a70683faa002b5c40de6d0279af88c27"
    "773f8641c3604c0661a806b5f0177a28c0f586e0006058aa30dc7d6211e69ed72338ea63"
    "53c2dd94c2c21634bbcbee5690bcb6deebfc7da1ce591d766f05e4094b7c018839720a3d"
    "7c927c2486e3725f724d9db91ac15bb4d39eb8fced54557808fca5b5d83d7cd34dad0fc4"
    "1e50ef5eb161e6f8a28514d96c51133c6fd5c7e756e14ec4362abfceddc6c837d79a3234"
    "92638212670efa8e406000e03a39ce37d3faf5cfabc277375ac52d1b5cb0679e4fa33742"
    "d382274099bc9bbed5118e9dbf0f7315d62d1c7ec700c47bb78c1b6b21a19045b26eb1be"
    "6a366eb45748ab2fbc946e79c6a376d26549c2c8530ff8ee468dde7dd5730a1d4cd04dc6"
    "2939bbdba9ba4650ac9526e8be5ee304a1fad5f06a2d519a63ef8ce29a86ee22c089c2b8"
    "43242ef6a51e03aa9cf2d0a483c061ba9be96a4d8fe51550ba645bd62826a2f9a73a3ae1"
    "4ba99586ef5562e9c72fefd3f752f7da3f046f6977fa0a5980e4a91587b086019b09e6ad"
    "3b3ee593e990fd5a9e34d7972cf0b7d9022b8b5196d5ac3a017da67dd1cf3ed67c7d2d28"
    "1f9f25cfadf2b89b5ad6b4725a88f54ce029ac71e019a5e647b0acfded93fa9be8d3c48d"
    "283b57ccf8d5662979132e28785f0191ed756055f7960e44e3d35e8c15056dd488f46dba"
    "03a161250564f0bdc3eb9e153c9057a297271aeca93a072a1b3f6d9b1e6321f5f59c66fb"
    "26dcf3197533d928b155fdf5035634828aba3cbb28517711c20ad9f8abcc5167ccad925f"
    "4de817513830dc8e379d58629320f991ea7a90c2fb3e7bce5121ce64774fbe32a8b6e37e"
    "c3293d4648de53696413e680a2ae0810dd6db22469852dfd09072166b39a460a6445c0dd"
    "586cdecf1c20c8ae5bbef7dd1b588d40ccd2017f6bb4e3bbdda26a7e3a59ff453e350a44"
    "bcb4cdd572eacea8fa6484bb8d6612aebf3c6f47d29be463542f5d9eaec2771bf64e6370"
    "740e0d8de75b1357f8721671af537d5d4040cb084eb4e2cc34d2466a0115af84e1b00428"
    "95983a1d06b89fb4ce6ea0486f3f3b823520ab82011a1d4b277227f8611560b1e7933fdc"
    "bb3a792b344525bda08839e151ce794b2f32c9b7a01fbac9e01cc87ebcc7d1f6cf0111c3"
    "a1e8aac71a908749d44fbd9ad0dadecbd50ada380339c32ac69136678df9317ce0b12b4f"
    "f79e59b743f5bb3af2d519ff27d9459cbf97222c15e6fc2a0f91fc719b941525fae59361"
    "ceb69cebc2a8645912baa8d1b6c1075ee3056a0c10d25065cb03a442e0ec6e0e1698db3b"
    "4c98a0be3278e9649f1f9532e0d392dfd3a0342b8971f21e1b0a74414ba3348cc5be7120"
    "c37632d8df359f8d9b992f2ee60b6f470fe3f11de54cda541edad891ce6279cfcd3e7e6f"
    "1618b166fd2c1d05848fd2c5f6fb2299f523f357a632762393a8353156cccd02acf08162"
    "5a75ebb56e16369788d273ccde96629281b949d04c50901b71c65614e6c6c7bd327a140a"
    "45e1d006c3f27b9ac9aa53fd62a80f00bb25bfe235bdd2f671126905b2040222b6cbcf7c"
    "cd769c2b53113ec01640e3d338abbd602547adf0ba38209cf746ce7677afa1c520756060"
    "85cbfe4e8ae88dd87aaaf9b04cf9aa7e1948c25c02fb8a8c01c36ae4d6ebe1f990d4f869"
    "a65cdea03f09252dc208e69fb74e6132ce77e25b578fdfe33ac372e6"
)

_BLOWFISH_HEX = "".join(_BLOWFISH_HEX.split()).replace(" ", "")


def _blowfish_boxes() -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...],
                                tuple[int, ...], tuple[int, ...]]:
    words = [int(_BLOWFISH_HEX[i:i + 8], 16) for i in range(0, len(_BLOWFISH_HEX), 8)]
    if len(words) != 1042 or words[0] != 0x243F6A88 or words[18] != 0xD1310BA6:
        raise AssertionError("Blowfish constant table is corrupt")
    return tuple(words[:18]), tuple(words[18:274]), tuple(words[274:530]), \
        tuple(words[530:786]), tuple(words[786:1042])


_P_INIT, _S0, _S1, _S2, _S3 = _blowfish_boxes()


@dataclass(frozen=True)
class IntEntry:
    index: int
    name: str
    offset: int
    size: int
    name_known: bool = True


@dataclass(frozen=True)
class IntArchive:
    encrypted: bool
    entries: tuple[IntEntry, ...]
    cipher: object = field(default=None, repr=False)
    names_recovered: bool = True
    source_size: int = 0


@dataclass(frozen=True)
class IntProbe:
    encrypted: bool
    entry_count: int
    index_size: int


def _crc32_normal_table() -> tuple[int, ...]:
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) if c & 0x80000000 else (c << 1)
        table.append(c & 0xFFFFFFFF)
    return tuple(table)


_CRC32_NORMAL = _crc32_normal_table()


def encode_passphrase(password: str) -> int:
    """msg-tool get_key / GARbro KeyData.EncodePassPhrase (CRC32-normal, no final xor)."""
    if not isinstance(password, str):
        raise ValueError("CatSystem2 passphrase must be text")
    data = password.encode("cp932", errors="strict")
    key = 0xFFFFFFFF
    for c in data:
        key = (~_CRC32_NORMAL[((key >> 24) ^ c) & 0xFF] ^ (key << 8)) & 0xFFFFFFFF
    return key


class MersenneTwister:
    """CatSystem2 MT variant (msg-tool twister.rs; MT19937 tempering, LCG seeding)."""

    _N = 624
    _M = 397
    _MATRIX_A = 0x9908B0DF
    _SIGN = 0x80000000
    _LOWER = 0x7FFFFFFF
    _MASK_B = 0x9D2C5680
    _MASK_C = 0xEFC60000

    def __init__(self, seed: int):
        self.mt = [0] * self._N
        self.mti = self._N
        self.s_rand(seed)

    def s_rand(self, seed: int) -> None:
        seed &= 0xFFFFFFFF
        for i in range(self._N):
            upper = seed & 0xFFFF0000
            seed = (seed * 69069 + 1) & 0xFFFFFFFF
            self.mt[i] = upper | ((seed & 0xFFFF0000) >> 16)
            seed = (seed * 69069 + 1) & 0xFFFFFFFF
        self.mti = self._N

    def rand(self) -> int:
        mt, n, m = self.mt, self._N, self._M
        if self.mti >= n:
            mag01 = (0, self._MATRIX_A)
            for kk in range(n - m):
                y = (mt[kk] & self._SIGN) | (mt[kk + 1] & self._LOWER)
                mt[kk] = mt[kk + m] ^ (y >> 1) ^ mag01[y & 1]
            for kk in range(n - m, n - 1):
                y = (mt[kk] & self._SIGN) | (mt[kk + 1] & self._LOWER)
                mt[kk] = mt[kk - (n - m)] ^ (y >> 1) ^ mag01[y & 1]
            y = (mt[n - 1] & self._SIGN) | (mt[0] & self._LOWER)
            mt[n - 1] = mt[m - 1] ^ (y >> 1) ^ mag01[y & 1]
            self.mti = 0
        y = mt[self.mti]
        self.mti += 1
        y ^= y >> 11
        y ^= (y << 7) & self._MASK_B
        y ^= (y << 15) & self._MASK_C
        y ^= y >> 18
        return y & 0xFFFFFFFF


class Blowfish:
    """Standard Blowfish; block buffers use little-endian I/O (GARbro Blowfish.Decipher,
    msg-tool BlowfishLE). The u32-pair API is positional (GARbro Decipher(ref,ref))."""

    def __init__(self, key: bytes):
        if not 4 <= len(key) <= 56:
            raise ValueError("blowfish key must be 4..56 bytes")
        self.p = list(_P_INIT)
        self.s = [list(_S0), list(_S1), list(_S2), list(_S3)]
        key_pos = 0
        for i in range(18):
            word = 0
            for _ in range(4):
                word = (word << 8) | key[key_pos]
                key_pos = (key_pos + 1) % len(key)
            self.p[i] ^= word
        lr = (0, 0)
        for i in range(9):
            lr = self.encrypt(*lr)
            self.p[2 * i], self.p[2 * i + 1] = lr
        for box in self.s:
            for j in range(0, 256, 2):
                lr = self.encrypt(*lr)
                box[j], box[j + 1] = lr

    def _f(self, x: int) -> int:
        s = self.s
        a = (s[0][(x >> 24) & 0xFF] + s[1][(x >> 16) & 0xFF]) & 0xFFFFFFFF
        b = (a ^ s[2][(x >> 8) & 0xFF]) + s[3][x & 0xFF]
        return b & 0xFFFFFFFF

    def encrypt(self, l: int, r: int) -> tuple[int, int]:
        p = self.p
        for i in range(16):
            l = (l ^ p[i]) & 0xFFFFFFFF
            r = (r ^ self._f(l)) & 0xFFFFFFFF
            l, r = r, l
        l, r = r, l
        r = (r ^ p[16]) & 0xFFFFFFFF
        l = (l ^ p[17]) & 0xFFFFFFFF
        return l, r

    def decrypt(self, l: int, r: int) -> tuple[int, int]:
        p = self.p
        for i in range(17, 1, -1):
            l = (l ^ p[i]) & 0xFFFFFFFF
            r = (r ^ self._f(l)) & 0xFFFFFFFF
            l, r = r, l
        l, r = r, l
        r = (r ^ p[1]) & 0xFFFFFFFF
        l = (l ^ p[0]) & 0xFFFFFFFF
        return l, r

    def decrypt_block_le(self, buf: bytearray, length: int | None = None) -> None:
        end = len(buf) if length is None else length
        if end % 8 or end > len(buf):
            raise ValueError("blowfish length must be a multiple of 8 within the buffer")
        for i in range(0, end, 8):
            l, r = struct.unpack_from("<II", buf, i)
            l, r = self.decrypt(l, r)
            struct.pack_into("<II", buf, i, l, r)


def _decrypt_name(raw: bytes, key: int) -> str:
    """msg-tool decrypt_name == GARbro DecipherName (alphabet z..aZ..A, step mod 0x34)."""
    alphabet = b"zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA"
    out = bytearray(raw)
    k = ((key >> 24) + (key >> 16) + (key >> 8) + key) & 0xFF
    i = 0
    while i < len(out) and out[i] != 0:
        v = out[i]
        if 65 <= v <= 90 or 97 <= v <= 122:
            j = alphabet.index(v)
            j -= k % 0x34
            if j < 0:
                j += 0x34
            out[i] = alphabet[0x33 - j]
        k = (k + 1) & 0xFFFFFFFF
        i += 1
    return out[:i].decode("cp932", errors="strict")


def _as_stream(source):
    """Return ``(binary_stream, should_close)`` for bytes, paths or seekable streams."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        return io.BytesIO(bytes(source)), True
    if hasattr(source, "read") and hasattr(source, "seek"):
        return source, False
    try:
        return open(os.fspath(source), "rb"), True
    except (TypeError, OSError) as exc:
        raise ValueError("INT source must be bytes, a path or a seekable binary stream") from exc


def _size_of(stream) -> int:
    try:
        position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(position)
    except (AttributeError, OSError) as exc:
        raise ValueError("INT source must be seekable") from exc
    if not isinstance(size, int) or size < 0:
        raise ValueError("invalid INT source size")
    return size


def _read_at(stream, offset: int, size: int, total: int, what: str) -> bytes:
    if type(offset) is not int or type(size) is not int or offset < 0 or size < 0 \
            or offset > total or size > total - offset:
        raise ValueError(f"{what} lies outside INT archive")
    try:
        stream.seek(offset)
        data = stream.read(size)
    except (AttributeError, OSError) as exc:
        raise ValueError(f"failed to read INT {what}") from exc
    if not isinstance(data, bytes) or len(data) != size:
        raise ValueError(f"INT {what} is truncated or not binary")
    return data


def probe_int(source, *, max_entries: int = _MAX_ENTRIES,
              max_index_size: int = _MAX_INDEX) -> IntProbe:
    """Read only the KIF header and report encryption/count/index budget."""
    if type(max_entries) is not int or max_entries < 0 or type(max_index_size) is not int \
            or max_index_size < 8:
        raise ValueError("invalid INT index limits")
    stream, close = _as_stream(source)
    try:
        total = _size_of(stream)
        header = _read_at(stream, 0, min(total, 0x50), total, "header")
        if len(header) < 8 or header[:4] != _MAGIC:
            raise ValueError("not a CatSystem2 INT archive (KIF)")
        count, = struct.unpack_from("<I", header, 4)
        if count > max_entries:
            raise ValueError("INT entry count exceeds limit")
        encrypted = len(header) >= 8 + len(_KEY_ENTRY) and header[8:8 + len(_KEY_ENTRY)] == _KEY_ENTRY
        if encrypted:
            if count < 1:
                raise ValueError("encrypted INT has an invalid entry count")
            index_size = 0x50 + (count - 1) * _ENTRY_RECORD
        else:
            index_size = 8 + count * (min(_NAME_SIZES) + 8)
        if index_size > max_index_size:
            raise ValueError("INT index exceeds limit")
        if index_size > total:
            raise ValueError("INT index is truncated")
        return IntProbe(encrypted, count, index_size)
    finally:
        if close:
            stream.close()


def _parse_unencrypted(stream, file_size: int, count: int,
                       max_index_size: int) -> tuple[IntEntry, ...]:
    budget_blocked = False
    for name_size in _NAME_SIZES:
        record_size = name_size + 8
        index_end = 8 + count * record_size
        if index_end > max_index_size:
            budget_blocked = True
            continue
        if index_end > file_size:
            continue
        entries = []
        ok = True
        for i in range(count):
            pos = 8 + i * record_size
            record = _read_at(stream, pos, record_size, file_size, "plain index record")
            name_field = record[:name_size]
            terminator = name_field.find(b"\0")
            if terminator <= 0:
                ok = False
                break
            try:
                name = name_field[:terminator].decode("cp932", errors="strict")
            except UnicodeDecodeError:
                ok = False
                break
            offset, size = struct.unpack_from("<II", record, name_size)
            if offset < index_end or size > file_size or offset > file_size - size:
                ok = False
                break
            entries.append(IntEntry(i, name, offset, size))
        if ok:
            return tuple(entries)
    if budget_blocked:
        raise ValueError("INT index exceeds limit")
    raise ValueError("INT index does not match plain layout (name size 0x20/0x40)")


def read_int(source, *, password: str | None = None, key: int | None = None,
             max_entries: int = _MAX_ENTRIES, max_index_size: int = _MAX_INDEX) -> IntArchive:
    """Parse an INT index without loading member payloads.

    A password/key recovers encrypted filenames only. Offsets, sizes and member data use
    the archive seed and remain readable without it; unknown names become stable ordinal
    placeholders with ``name_known=False``.
    """
    stream, close = _as_stream(source)
    try:
        file_size = _size_of(stream)
        header = _read_at(stream, 0, min(file_size, 0x50), file_size, "header")
        probe = probe_int(header if file_size <= len(header) else stream,
                          max_entries=max_entries, max_index_size=max_index_size)
        count = probe.entry_count
        if probe.encrypted:
            seed, = struct.unpack_from("<I", header, 0x4C)
            twister = MersenneTwister(seed)
            cipher = Blowfish(struct.pack("<I", twister.rand()))
            if key is None and password is not None:
                key = encode_passphrase(password)
            if key is not None and (type(key) is not int or not 0 <= key <= 0xFFFFFFFF):
                raise ValueError("INT password key must be a u32")
            names_recovered = key is not None
            entries = []
            for i in range(1, count):
                pos = 0x50 + (i - 1) * _ENTRY_RECORD
                record = _read_at(stream, pos, _ENTRY_RECORD, file_size,
                                  f"encrypted index record {i}")
                stored_offset, size = struct.unpack_from("<II", record, _NAME_FIELD)
                offset, size = cipher.decrypt((stored_offset + i) & 0xFFFFFFFF, size)
                if names_recovered:
                    twister.s_rand((key + i) & 0xFFFFFFFF)
                    name = _decrypt_name(record[:_NAME_FIELD], twister.rand())
                else:
                    name = f"m{i:08d}.bin"
                if offset < probe.index_size or offset > file_size or size > file_size \
                        or offset > file_size - size:
                    label = repr(name) if names_recovered else str(i)
                    raise ValueError(f"INT entry {label} points outside archive")
                entries.append(IntEntry(i, name, offset, size, names_recovered))
            return IntArchive(True, tuple(entries), cipher, names_recovered, file_size)
        if count == 0:
            return IntArchive(False, (), None, True, file_size)
        entries = _parse_unencrypted(stream, file_size, count, max_index_size)
        return IntArchive(False, entries, None, True, file_size)
    finally:
        if close:
            stream.close()


def probe_member(source, entry: IntEntry, cipher: Blowfish | None = None, *,
                 max_bytes: int = 0x220) -> bytes:
    """Read and decrypt a bounded member prefix without loading the whole member."""
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("invalid INT member probe limit")
    stream, close = _as_stream(source)
    try:
        total = _size_of(stream)
        amount = min(entry.size, max_bytes)
        raw = bytearray(_read_at(stream, entry.offset, amount, total, "member probe"))
        if cipher is not None:
            cipher.decrypt_block_le(raw, len(raw) // 8 * 8)
        return bytes(raw)
    finally:
        if close:
            stream.close()


def read_member(source, entry: IntEntry, cipher: Blowfish | None = None,
                *, max_member: int = _MAX_MEMBER) -> bytes:
    """Read/decrypt one member; a trailing partial Blowfish block remains verbatim."""
    if type(max_member) is not int or max_member < 0:
        raise ValueError("invalid INT member limit")
    if entry.size > max_member:
        raise ValueError("INT member exceeds limit")
    stream, close = _as_stream(source)
    try:
        total = _size_of(stream)
        raw = bytearray(_read_at(stream, entry.offset, entry.size, total, "member"))
        if cipher is not None:
            cipher.decrypt_block_le(raw, len(raw) // 8 * 8)
        return bytes(raw)
    finally:
        if close:
            stream.close()


def _pe_resource_tree(data: bytes) -> dict | None:
    """Walk a bounded PE32/PE32+ resource tree as type -> name -> language -> leaf."""
    try:
        if len(data) < 0x40 or data[:2] != b"MZ":
            return None
        pe_off, = struct.unpack_from("<I", data, 0x3C)
        if pe_off > len(data) - 24 or data[pe_off:pe_off + 4] != b"PE\0\0":
            return None
        coff = pe_off + 4
        num_sections, = struct.unpack_from("<H", data, coff + 2)
        opt_size, = struct.unpack_from("<H", data, coff + 16)
        opt_off = coff + 20
        sections_off = opt_off + opt_size
        if sections_off > len(data) or num_sections > (len(data) - sections_off) // 40:
            return None
        sections = []
        for i in range(num_sections):
            base = sections_off + 40 * i
            vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, base + 8)
            sections.append((vaddr, vsize, raddr, rsize))

        def rva_to_off(rva: int, size: int = 1) -> int | None:
            for vaddr, vsize, raddr, rsize in sections:
                span = max(vsize, rsize)
                delta = rva - vaddr
                if 0 <= delta < span and size <= rsize and delta <= rsize - size \
                        and raddr <= len(data) and delta + size <= len(data) - raddr:
                    return raddr + delta
            return None

        magic, = struct.unpack_from("<H", data, opt_off)
        if magic == 0x10B:
            directory = opt_off + 0x60
        elif magic == 0x20B:
            directory = opt_off + 0x70
        else:
            return None
        if directory + 3 * 8 > opt_off + opt_size:
            return None
        rsrc_rva, rsrc_size = struct.unpack_from("<II", data, directory + 2 * 8)
        if not rsrc_rva or not rsrc_size:
            return None
        rsrc_off = rva_to_off(rsrc_rva, min(rsrc_size, 16))
        if rsrc_off is None:
            return None
        rsrc_end = min(len(data), rsrc_off + rsrc_size)

        def resource_slice(relative: int, size: int) -> bytes:
            start = rsrc_off + relative
            if relative < 0 or size < 0 or start < rsrc_off or start > rsrc_end \
                    or size > rsrc_end - start:
                raise ValueError("PE resource structure exceeds its directory")
            return data[start:start + size]

        def read_dir(relative: int, depth: int = 0) -> dict:
            if depth > 3:
                raise ValueError("PE resource tree is too deep")
            header = resource_slice(relative, 16)
            _chars, _timestamp, _major, _minor, named, ids = struct.unpack("<IIHHHH", header)
            count = named + ids
            records = resource_slice(relative + 16, count * 8)
            out = {}
            for i in range(count):
                name_field, target_field = struct.unpack_from("<II", records, i * 8)
                if name_field & 0x80000000:
                    string_relative = name_field & 0x7FFFFFFF
                    length, = struct.unpack("<H", resource_slice(string_relative, 2))
                    key = resource_slice(string_relative + 2, length * 2).decode("utf-16le")
                else:
                    key = name_field
                target_relative = target_field & 0x7FFFFFFF
                if target_field & 0x80000000:
                    out[key] = read_dir(target_relative, depth + 1)
                else:
                    leaf = resource_slice(target_relative, 16)
                    data_rva, size, _codepage, _reserved = struct.unpack("<IIII", leaf)
                    file_off = rva_to_off(data_rva, size)
                    if file_off is None:
                        raise ValueError("PE resource payload lies outside file-backed sections")
                    out[key] = (file_off, size)
            return out

        return read_dir(0)
    except (IndexError, KeyError, RecursionError, struct.error, UnicodeDecodeError, ValueError):
        return None


def _resource_leaf(node) -> tuple[int, int] | None:
    if isinstance(node, tuple) and len(node) == 2:
        return node
    if not isinstance(node, dict):
        return None
    for language in (0x411, 1041, 0x409, 1033):
        if language in node:
            leaf = _resource_leaf(node[language])
            if leaf is not None:
                return leaf
    for child in node.values():
        leaf = _resource_leaf(child)
        if leaf is not None:
            return leaf
    return None


def _find_named_resource(tree: dict, names: tuple[str, ...]) -> tuple[int, int] | None:
    """Locate a named type/name resource and descend through its language node."""
    if len(names) != 2:
        raise ValueError("resource lookup requires type and name")
    for outer, inner in (names, tuple(reversed(names))):
        subtree = tree.get(outer)
        if isinstance(subtree, dict) and inner in subtree:
            leaf = _resource_leaf(subtree[inner])
            if leaf is not None:
                return leaf
    return None


def extract_exe_password(source, *, max_exe_size: int = _MAX_EXE) -> str:
    """Recover the INT passphrase from a CatSystem2 PE without executing the image."""
    if type(max_exe_size) is not int or max_exe_size < 1:
        raise ValueError("invalid executable size limit")
    stream, close = _as_stream(source)
    try:
        total = _size_of(stream)
        if total > max_exe_size:
            raise ValueError("CatSystem2 executable exceeds limit")
        exe = _read_at(stream, 0, total, total, "executable")
    finally:
        if close:
            stream.close()
    tree = _pe_resource_tree(exe)
    if not tree:
        raise ValueError("no valid PE32/PE32+ resource tree")
    code_ref = _find_named_resource(tree, ("V_CODE2", "DATA"))
    if code_ref is None:
        raise ValueError("exe has no V_CODE2/DATA resource")
    off, size = code_ref
    code = bytearray(exe[off:off + size])
    if len(code) < 8:
        raise ValueError("V_CODE2 resource is too short")
    key_ref = _find_named_resource(tree, ("KEY_CODE", "KEY"))
    if key_ref is not None:
        key = bytearray(exe[key_ref[0]:key_ref[0] + key_ref[1]])
        for i in range(len(key)):
            key[i] ^= 0xCD
    else:
        key = bytearray(_DEFAULT_EXE_KEY)
    if not 4 <= len(key) <= 56:
        raise ValueError("KEY_CODE resource is not a valid Blowfish key")
    Blowfish(bytes(key)).decrypt_block_le(code, len(code) // 8 * 8)
    end = code.find(0)
    if end < 0:
        end = len(code)
    return code[:end].decode("cp932", errors="strict")
