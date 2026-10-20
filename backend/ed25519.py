"""Ed25519 imza/doğrulama -- yalnızca standart kütüphane (RFC 8032, bölüm 5.1).

2026-10-20: PTS lisansları artık açık anahtarlı imzayla (Ed25519) doğrulanır.
Eski yöntemde (HMAC) lisansı DOĞRULAYAN anahtar ile ÜRETEN anahtar aynıydı ve
müşterinin bilgisayarında (.env) duruyordu: kurulumu yapılan kişi kendine
istediği lisansı üretebiliyordu. Ed25519'da müşteride yalnızca AÇIK anahtar
bulunur; lisans üretmek için gereken ÖZEL anahtar yalnızca lisans verenin
bilgisayarında kalır.

Kod RFC 8032'deki başvuru uygulamasının sadeleştirilmiş halidir; testlerde
`cryptography` kütüphanesiyle ve RFC test vektörleriyle karşılaştırılır.
Yeni bir paket bağımlılığı eklememek için saf Python: doğrulama birkaç ms sürer.
"""
import hashlib

_p = 2 ** 255 - 19
_q = 2 ** 252 + 27742317777372353535851937790883648493
_d = (-121665 * pow(121666, _p - 2, _p)) % _p
_SQRT_M1 = pow(2, (_p - 1) // 4, _p)


def _sha512(veri: bytes) -> bytes:
    return hashlib.sha512(veri).digest()


def _sha512_mod_q(veri: bytes) -> int:
    return int.from_bytes(_sha512(veri), "little") % _q


# Noktalar genişletilmiş koordinatlarda: (X, Y, Z, T), x=X/Z, y=Y/Z, x*y=T/Z
def _topla(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _carp(s: int, P):
    Q = (0, 1, 1, 0)  # etkisiz eleman
    while s > 0:
        if s & 1:
            Q = _topla(Q, P)
        P = _topla(P, P)
        s >>= 1
    return Q


def _esit(P, Q) -> bool:
    if (P[0] * Q[2] - Q[0] * P[2]) % _p != 0:
        return False
    return (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _x_bul(y: int, isaret: int):
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p)
    if x2 == 0:
        return None if isaret else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _SQRT_M1 % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != isaret:
        x = _p - x
    return x


_g_y = 4 * pow(5, _p - 2, _p) % _p
_g_x = _x_bul(_g_y, 0)
_G = (_g_x, _g_y, 1, _g_x * _g_y % _p)


def _sikistir(P) -> bytes:
    zinv = pow(P[2], _p - 2, _p)
    x = P[0] * zinv % _p
    y = P[1] * zinv % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _ac(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    isaret = y >> 255
    y &= (1 << 255) - 1
    x = _x_bul(y, isaret)
    if x is None:
        return None
    return (x, y, 1, x * y % _p)


def _gizli_genislet(ozel: bytes):
    if len(ozel) != 32:
        raise ValueError("Ed25519 özel anahtarı 32 bayt olmalı")
    h = _sha512(ozel)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def acik_anahtar(ozel: bytes) -> bytes:
    a, _ = _gizli_genislet(ozel)
    return _sikistir(_carp(a, _G))


def imzala(ozel: bytes, mesaj: bytes) -> bytes:
    a, onek = _gizli_genislet(ozel)
    A = _sikistir(_carp(a, _G))
    r = _sha512_mod_q(onek + mesaj)
    Rs = _sikistir(_carp(r, _G))
    h = _sha512_mod_q(Rs + A + mesaj)
    s = (r + h * a) % _q
    return Rs + int.to_bytes(s, 32, "little")


def dogrula(acik: bytes, mesaj: bytes, imza: bytes) -> bool:
    if len(acik) != 32 or len(imza) != 64:
        return False
    A = _ac(acik)
    if not A:
        return False
    Rs = imza[:32]
    R = _ac(Rs)
    if not R:
        return False
    s = int.from_bytes(imza[32:], "little")
    if s >= _q:
        return False
    h = _sha512_mod_q(Rs + acik + mesaj)
    return _esit(_carp(s, _G), _topla(R, _carp(h, A)))
