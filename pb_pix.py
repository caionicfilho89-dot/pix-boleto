"""Pix BR Code (estático) — monta, lê e confere payloads "Pix Copia e Cola".

Segue o padrão EMV-QRCPS usado pelo Banco Central (Manual de Padrões para Iniciação do Pix).
Tudo offline: nada aqui fala com a internet.
"""
import re
import unicodedata

GUI = "br.gov.bcb.pix"


# ---------------------------------------------------------------- CRC16
def crc16(data: str) -> str:
    """CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF), 4 dígitos hex maiúsculos."""
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def tlv(tag: str, value: str) -> str:
    n = len(value)
    if n > 99:
        raise ValueError(f"Campo {tag} grande demais ({n} caracteres, máximo 99).")
    return f"{tag}{n:02d}{value}"


# ---------------------------------------------------------------- texto
def sem_acentos(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s if 32 <= ord(c) < 127).strip()


# ---------------------------------------------------------------- chaves
def cpf_valido(d: str) -> bool:
    if not re.fullmatch(r"\d{11}", d) or d == d[0] * 11:
        return False
    for n in (9, 10):
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        dv = (s * 10) % 11 % 10
        if dv != int(d[n]):
            return False
    return True


def cnpj_valido(d: str) -> bool:
    """Aceita CNPJ numérico e o novo CNPJ alfanumérico (DVs sempre numéricos)."""
    d = d.upper()
    if not re.fullmatch(r"[0-9A-Z]{12}\d{2}", d) or d == d[0] * 14:
        return False
    vals = [ord(c) - 48 for c in d]
    for n in (12, 13):
        pesos = list(range(n - 7, 1, -1)) + list(range(9, 1, -1))
        s = sum(v * p for v, p in zip(vals[:n], pesos))
        r = s % 11
        dv = 0 if r < 2 else 11 - r
        if dv != vals[n]:
            return False
    return True


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
EVP_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

TIPOS = ["Automático", "CPF", "CNPJ", "E-mail", "Telefone", "Chave aleatória"]


def _telefone(raw: str):
    d = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        if not d.startswith("55"):
            return None
        d = d[2:]
    elif len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) not in (10, 11):
        return None
    ddd, num = d[:2], d[2:]
    if ddd[0] == "0" or ddd[1] == "0":
        return None
    if len(num) == 9 and num[0] != "9":
        return None
    return "+55" + d


def normalizar_chave(raw: str, tipo: str = "Automático"):
    """Devolve (chave_normalizada, tipo). Levanta ValueError se inválida."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("Preencha a sua chave Pix.")
    digitos = re.sub(r"\D", "", s)
    sem_pont = re.sub(r"[.\-/ ]", "", s)
    if tipo == "Automático":
        if "@" in s:
            tipo = "E-mail"
        elif EVP_RE.match(s.lower()):
            tipo = "Chave aleatória"
        elif s.startswith("+"):
            tipo = "Telefone"
        elif re.fullmatch(r"[\d.\-/ ]+", s) and len(digitos) == 11 and cpf_valido(digitos):
            tipo = "CPF"
        elif re.fullmatch(r"[0-9A-Za-z.\-/ ]+", s) and len(sem_pont) == 14 and cnpj_valido(sem_pont):
            tipo = "CNPJ"
        elif re.fullmatch(r"[\d()+.\- ]+", s) and _telefone(s):
            tipo = "Telefone"
        else:
            raise ValueError("Não reconheci essa chave. Escolha o tipo na lista ou confira os números.")
    if tipo == "CPF":
        if not cpf_valido(digitos):
            raise ValueError("CPF inválido (dígitos verificadores não conferem).")
        return digitos, tipo
    if tipo == "CNPJ":
        c = sem_pont.upper()
        if not cnpj_valido(c):
            raise ValueError("CNPJ inválido (dígitos verificadores não conferem).")
        return c, tipo
    if tipo == "E-mail":
        e = s.lower()
        if not EMAIL_RE.match(e) or len(e) > 77:
            raise ValueError("E-mail inválido.")
        return e, tipo
    if tipo == "Telefone":
        t = _telefone(s)
        if not t:
            raise ValueError("Telefone inválido. Use DDD + número, ex.: (11) 98765-4321.")
        return t, tipo
    if tipo == "Chave aleatória":
        e = s.lower()
        if not EVP_RE.match(e):
            raise ValueError("Chave aleatória inválida (formato 8-4-4-4-12, ex.: 123e4567-e89b-...).")
        return e, tipo
    raise ValueError("Tipo de chave desconhecido.")


# ---------------------------------------------------------------- montar
def montar_payload(chave, nome, cidade, valor=None, txid="***", mensagem="", tipo="Automático"):
    """Monta o BR Code estático. Devolve (payload, chave_normalizada, tipo)."""
    chave, tipo = normalizar_chave(chave, tipo)
    nome = sem_acentos(nome)[:25].strip()
    cidade = sem_acentos(cidade)[:15].strip()
    if not nome:
        raise ValueError("Preencha o nome do recebedor.")
    if not cidade:
        raise ValueError("Preencha a cidade.")
    txid = (txid or "").strip()
    if txid != "***":
        txid = re.sub(r"[^A-Za-z0-9]", "", txid)[:25] or "***"
    mensagem = sem_acentos(mensagem)

    mai = tlv("00", GUI) + tlv("01", chave)
    if mensagem:
        livre = 99 - len(mai) - 4
        if livre > 0:
            mai += tlv("02", mensagem[:livre])

    p = tlv("00", "01")
    p += tlv("26", mai)
    p += tlv("52", "0000")
    p += tlv("53", "986")
    if valor is not None:
        v = round(float(valor), 2)
        if v < 0:
            raise ValueError("Valor não pode ser negativo.")
        if v > 0:
            vs = f"{v:.2f}"
            if len(vs) > 13:
                raise ValueError("Valor grande demais.")
            p += tlv("54", vs)
    p += tlv("58", "BR")
    p += tlv("59", nome)
    p += tlv("60", cidade)
    p += tlv("62", tlv("05", txid))
    p += "6304"
    return p + crc16(p), chave, tipo


# ---------------------------------------------------------------- ler
def parse_tlv(s: str):
    """Lista de (tag, valor). Levanta ValueError se mal formado."""
    out, i = [], 0
    while i < len(s):
        if i + 4 > len(s):
            raise ValueError(f"Texto cortado perto da posição {i}.")
        tag, ln = s[i:i + 2], s[i + 2:i + 4]
        if not (tag.isdigit() and ln.isdigit()):
            raise ValueError(f"Campo mal formado na posição {i} — isso não parece um Pix Copia e Cola.")
        n = int(ln)
        val = s[i + 4:i + 4 + n]
        if len(val) != n:
            raise ValueError(f"Campo {tag} está cortado (texto incompleto).")
        out.append((tag, val))
        i += 4 + n
    return out


def ler_payload(texto: str) -> dict:
    s = (texto or "").strip().replace("\r", "").replace("\n", "")
    if not s:
        raise ValueError("Cole um Pix Copia e Cola.")
    campos = parse_tlv(s)
    d = dict(campos)
    r = {"chave": "", "nome": d.get("59", ""), "cidade": d.get("60", ""), "valor": None,
         "txid": "", "mensagem": "", "url": "", "e_pix": False, "dinamico": False,
         "crc_lido": d.get("63", ""), "crc_calc": "", "crc_ok": False, "campos": campos}
    if "54" in d:
        try:
            r["valor"] = float(d["54"])
        except ValueError:
            r["valor"] = None
    r["dinamico"] = d.get("01") == "12"
    for tag in [str(x) for x in range(26, 52)]:
        if tag in d:
            try:
                sub = dict(parse_tlv(d[tag]))
            except ValueError:
                continue
            if sub.get("00", "").lower() == GUI:
                r["e_pix"] = True
                r["chave"] = sub.get("01", "")
                r["mensagem"] = sub.get("02", "")
                r["url"] = sub.get("25", "")
                break
    if "62" in d:
        try:
            r["txid"] = dict(parse_tlv(d["62"])).get("05", "")
        except ValueError:
            pass
    pos = s.rfind("6304")
    if pos >= 0 and pos + 8 == len(s):
        r["crc_calc"] = crc16(s[:pos + 4])
        r["crc_ok"] = r["crc_calc"] == s[pos + 4:].upper()
    return r


def tipo_da_chave(chave: str) -> str:
    try:
        return normalizar_chave(chave)[1]
    except ValueError:
        return "?"
