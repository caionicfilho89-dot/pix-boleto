"""Conferência de boletos (bancário e arrecadação/convênio) — só CONFERE, não gera boleto.

Valida os dígitos verificadores, converte linha digitável <-> código de barras e lê banco,
valor e vencimento (com a virada do fator de vencimento de 22/02/2025). Tudo offline.
"""
import re
from datetime import date, timedelta

BANCOS = {
    "001": "Banco do Brasil", "003": "Banco da Amazônia", "004": "Banco do Nordeste",
    "021": "Banestes", "033": "Santander", "037": "Banpará", "041": "Banrisul",
    "047": "Banese", "070": "BRB", "077": "Banco Inter", "085": "Ailos",
    "104": "Caixa Econômica Federal", "133": "Cresol", "136": "Unicred", "197": "Stone",
    "208": "BTG Pactual", "212": "Banco Original", "237": "Bradesco", "246": "ABC Brasil",
    "260": "Nubank", "290": "PagBank (PagSeguro)", "318": "Banco BMG", "323": "Mercado Pago",
    "336": "C6 Bank", "341": "Itaú Unibanco", "380": "PicPay", "389": "Banco Mercantil",
    "403": "Cora", "422": "Banco Safra", "623": "Banco Pan", "633": "Rendimento",
    "634": "Banco Triângulo", "655": "Banco Votorantim (BV)", "707": "Daycoval",
    "745": "Citibank", "748": "Sicredi", "756": "Sicoob",
}

SEGMENTOS = {
    "1": "Prefeituras", "2": "Saneamento (água/esgoto)", "3": "Energia elétrica e gás",
    "4": "Telecomunicações", "5": "Órgãos governamentais", "6": "Carnês e demais empresas",
    "7": "Multas de trânsito", "9": "Uso exclusivo do banco",
}

BASE_ANTIGA = date(1997, 10, 7)       # fator 1000 = 03/07/2000 ... 9999 = 21/02/2025
BASE_NOVA = date(2025, 2, 22)         # a partir daqui o fator recomeça em 1000


# ---------------------------------------------------------------- módulos
def mod10(num: str) -> int:
    s, peso = 0, 2
    for c in reversed(num):
        p = int(c) * peso
        s += p // 10 + p % 10
        peso = 1 if peso == 2 else 2
    return (10 - s % 10) % 10


def _soma11(num: str) -> int:
    s, peso = 0, 2
    for c in reversed(num):
        s += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    return s


def mod11_bancario(num: str) -> int:
    """DV geral do código de barras bancário (0, 10 e 11 viram 1)."""
    dv = 11 - _soma11(num) % 11
    return 1 if dv in (0, 10, 11) else dv


def mod11_arrecadacao(num: str) -> int:
    """DV de arrecadação em módulo 11 (resto 0/1 -> 0; resto 10 -> 1)."""
    r = _soma11(num) % 11
    if r in (0, 1):
        return 0
    if r == 10:
        return 1
    return 11 - r


# ---------------------------------------------------------------- vencimento
def data_do_fator(fator: int, hoje: date = None):
    """Devolve (data ou None, observação). Escolhe o ciclo (antigo/novo) mais perto de hoje."""
    if fator == 0:
        return None, "sem vencimento definido"
    hoje = hoje or date.today()
    antiga = BASE_ANTIGA + timedelta(days=fator)
    if fator < 1000:
        return antiga, "fator fora do padrão"
    nova = BASE_NOVA + timedelta(days=fator - 1000)
    if abs((nova - hoje).days) < abs((antiga - hoje).days):
        return nova, "ciclo novo do fator (após 22/02/2025)"
    return antiga, "ciclo antigo do fator (até 21/02/2025)"


# ---------------------------------------------------------------- formatação
def fmt_linha_bancaria(l: str) -> str:
    return f"{l[0:5]}.{l[5:10]} {l[10:15]}.{l[15:21]} {l[21:26]}.{l[26:32]} {l[32]} {l[33:47]}"


def fmt_linha_arrecadacao(l: str) -> str:
    return " ".join(f"{l[i:i + 11]}-{l[i + 11]}" for i in range(0, 48, 12))


def fmt_reais(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


# ---------------------------------------------------------------- bancário
def _bancario_de_barras(cb: str, r: dict):
    dv_calc = mod11_bancario(cb[:4] + cb[5:])
    r["checagens"].append(("DV geral (módulo 11)", int(cb[4]) == dv_calc, cb[4], str(dv_calc)))
    banco = cb[:3]
    r["banco_codigo"] = banco
    r["banco_nome"] = BANCOS.get(banco, "banco não está na lista do app")
    r["moeda"] = "Real (R$)" if cb[3] == "9" else f"código {cb[3]} (não é Real!)"
    if cb[3] != "9":
        r["avisos"].append("Código de moeda diferente de 9 (Real) — muito estranho para um boleto brasileiro.")
    fator = int(cb[5:9])
    r["fator"] = fator
    r["vencimento"], r["obs_venc"] = data_do_fator(fator)
    v = int(cb[9:19]) / 100
    r["valor"] = v
    r["valor_txt"] = fmt_reais(v) if v > 0 else "valor em aberto (definido na hora de pagar)"
    r["campo_livre"] = cb[19:44]


def _conferir_bancario_linha(l: str, r: dict):
    c1, c2, c3 = l[0:9], l[10:20], l[21:31]
    for nome, campo, dv in (("Campo 1", c1, l[9]), ("Campo 2", c2, l[20]), ("Campo 3", c3, l[31])):
        calc = mod10(campo)
        r["checagens"].append((f"{nome} (módulo 10)", int(dv) == calc, dv, str(calc)))
    cb = l[0:4] + l[32] + l[33:47] + l[4:9] + l[10:20] + l[21:31]
    r["barras"] = cb
    r["linha"] = l
    _bancario_de_barras(cb, r)


def barras_para_linha_bancaria(cb: str) -> str:
    livre = cb[19:44]
    c1 = cb[0:4] + livre[0:5]
    c2 = livre[5:15]
    c3 = livre[15:25]
    return (c1 + str(mod10(c1)) + c2 + str(mod10(c2)) + c3 + str(mod10(c3))
            + cb[4] + cb[5:19])


# ---------------------------------------------------------------- arrecadação
def _mod_arrec(cb_or_first: str):
    ident = cb_or_first[2]
    if ident in "67":
        return mod10, "módulo 10"
    if ident in "89":
        return mod11_arrecadacao, "módulo 11"
    return None, ""


def _arrecadacao_de_barras(cb: str, r: dict):
    fn, nome_mod = _mod_arrec(cb)
    if fn is None:
        r["checagens"].append(("Identificador de valor (3º dígito: 6, 7, 8 ou 9)", False, cb[2], "6/7/8/9"))
        return
    dv = fn(cb[:3] + cb[4:])
    r["checagens"].append((f"DV geral ({nome_mod})", int(cb[3]) == dv, cb[3], str(dv)))
    r["segmento"] = SEGMENTOS.get(cb[1], f"segmento {cb[1]} (desconhecido)")
    efetivo = cb[2] in "68"
    v = int(cb[4:15]) / 100
    r["valor"] = v
    if efetivo:
        r["valor_txt"] = fmt_reais(v) if v > 0 else "valor em aberto (definido na hora de pagar)"
    else:
        r["valor_txt"] = f"valor de referência {int(cb[4:15])} (não é em reais)"
    if cb[1] == "6":
        r["empresa"] = f"CNPJ (8 primeiros dígitos): {cb[15:23]}"
    else:
        r["empresa"] = f"código da empresa/órgão: {cb[15:19]}"


def _conferir_arrecadacao_linha(l: str, r: dict):
    fn, nome_mod = _mod_arrec(l)
    blocos = [l[i:i + 12] for i in range(0, 48, 12)]
    cb = "".join(b[:11] for b in blocos)
    if fn is not None:
        for i, b in enumerate(blocos, 1):
            calc = fn(b[:11])
            r["checagens"].append((f"Bloco {i} ({nome_mod})", int(b[11]) == calc, b[11], str(calc)))
    r["barras"] = cb
    r["linha"] = l
    _arrecadacao_de_barras(cb, r)


def barras_para_linha_arrecadacao(cb: str) -> str:
    fn, _ = _mod_arrec(cb)
    if fn is None:
        return ""
    return "".join(cb[i:i + 11] + str(fn(cb[i:i + 11])) for i in range(0, 44, 11))


# ---------------------------------------------------------------- entrada única
def conferir(texto: str) -> dict:
    """Confere linha digitável ou código de barras. Devolve dict com tudo pro app mostrar."""
    d = re.sub(r"\D", "", texto or "")
    r = {"tipo": "", "entrada": "", "linha": "", "barras": "", "linha_fmt": "", "checagens": [],
         "avisos": [], "ok": False, "erro": "", "banco_codigo": "", "banco_nome": "", "moeda": "",
         "fator": None, "vencimento": None, "obs_venc": "", "valor": None, "valor_txt": "",
         "segmento": "", "empresa": "", "campo_livre": ""}
    n = len(d)
    if n == 0:
        r["erro"] = "Cole a linha digitável ou o código de barras do boleto."
        return r
    if n == 47:
        r["tipo"], r["entrada"] = "Boleto bancário", "linha digitável"
        _conferir_bancario_linha(d, r)
    elif n == 48:
        if d[0] != "8":
            r["erro"] = "Tem 48 dígitos mas não começa com 8 — não é uma conta de arrecadação/convênio válida."
            return r
        r["tipo"], r["entrada"] = "Arrecadação / convênio (contas, tributos)", "linha digitável"
        _conferir_arrecadacao_linha(d, r)
    elif n == 44:
        if d[0] == "8":
            r["tipo"], r["entrada"] = "Arrecadação / convênio (contas, tributos)", "código de barras"
            r["barras"] = d
            _arrecadacao_de_barras(d, r)
            r["linha"] = barras_para_linha_arrecadacao(d)
        else:
            r["tipo"], r["entrada"] = "Boleto bancário", "código de barras"
            r["barras"] = d
            _bancario_de_barras(d, r)
            r["linha"] = barras_para_linha_bancaria(d)
    else:
        r["erro"] = (f"Encontrei {n} dígitos. Boleto bancário tem 47 (linha digitável) ou 44 (código de "
                     "barras); conta de consumo/tributo tem 48 (linha) ou 44 (barras).")
        return r
    if r["linha"]:
        r["linha_fmt"] = (fmt_linha_bancaria(r["linha"]) if len(r["linha"]) == 47
                          else fmt_linha_arrecadacao(r["linha"]))
    r["ok"] = bool(r["checagens"]) and all(c[1] for c in r["checagens"])
    return r
