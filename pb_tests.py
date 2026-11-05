"""Testes da lógica do Pix & Boleto. Rode: python pb_tests.py"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pb_boleto as B  # noqa: E402
import pb_pix as P  # noqa: E402

# --- CRC com o exemplo publicado no Manual de Padrões para Iniciação do Pix (BCB)
EXEMPLO_BCB = ("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-426655440000"
               "5204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D")
assert P.crc16(EXEMPLO_BCB[:-4]) == "1D3D", P.crc16(EXEMPLO_BCB[:-4])
assert P.crc16("123456789") == "29B1"  # vetor padrão CRC-16/CCITT-FALSE
r = P.ler_payload(EXEMPLO_BCB)
assert r["crc_ok"] and r["e_pix"] and r["chave"] == "123e4567-e12b-12d1-a456-426655440000"
assert r["nome"] == "Fulano de Tal" and r["cidade"] == "BRASILIA" and r["txid"] == "***"
assert not P.ler_payload(EXEMPLO_BCB.replace("Fulano", "Fulana"))["crc_ok"]

# --- montar e ler de volta
p, ch, tp = P.montar_payload("(11) 98765-4321", "João da Silva Pão", "São Paulo", 12.5, "PEDIDO 42",
                             "Aluguel de março")
assert ch == "+5511987654321" and tp == "Telefone", (ch, tp)
r = P.ler_payload(p)
assert r["crc_ok"] and r["valor"] == 12.5 and r["nome"] == "Joao da Silva Pao" and r["cidade"] == "Sao Paulo"
assert r["txid"] == "PEDIDO42" and r["mensagem"] == "Aluguel de marco" and "5405" + "12.50" in p
# reproduz o exemplo do BCB pelo montador
p2, _, _ = P.montar_payload("123e4567-e12b-12d1-a456-426655440000", "Fulano de Tal", "BRASILIA")
assert p2 == EXEMPLO_BCB, p2
# nome/cidade cortados
p3, _, _ = P.montar_payload("fulano@Email.com", "A" * 40, "B" * 40)
r = P.ler_payload(p3)
assert len(r["nome"]) == 25 and len(r["cidade"]) == 15 and r["chave"] == "fulano@email.com"

# --- chaves
assert P.normalizar_chave("529.982.247-25") == ("52998224725", "CPF")
assert P.normalizar_chave("11.222.333/0001-81") == ("11222333000181", "CNPJ")
assert P.normalizar_chave("12ABC34501DE35", "CNPJ")[0] == "12ABC34501DE35"  # CNPJ alfanumérico (exemplo Receita)
assert P.normalizar_chave("+55 21 3333-4444")[0] == "+552133334444"
assert P.normalizar_chave("5511987654321")[0] == "+5511987654321"
for ruim, tipo in (("529.982.247-24", "CPF"), ("11.222.333/0001-80", "CNPJ"), ("a@b", "E-mail"),
                   ("123", "Telefone"), ("xyz", "Chave aleatória"), ("abc", "Automático")):
    try:
        P.normalizar_chave(ruim, tipo)
        raise AssertionError(f"deveria falhar: {ruim}")
    except ValueError:
        pass

# --- QR decodifica (se o OpenCV estiver instalado)
try:
    import cv2
    import numpy as np
    import segno
    import io
    buf = io.BytesIO()
    segno.make(p, error="m", micro=False).save(buf, kind="png", scale=8, border=4)
    img = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), cv2.IMREAD_GRAYSCALE)
    txt, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert txt == p, txt
    print("QR decodificado pelo OpenCV: OK")
except ImportError:
    print("(OpenCV ausente: pulei a leitura do QR)")

# --- módulos
assert B.mod10("399903512") == 8  # exemplo clássico Febraban (campo 1 de boleto 399)
assert B.mod11_arrecadacao("0") == 0

# --- fator de vencimento
assert B.data_do_fator(1000, hoje=date(2000, 7, 1))[0] == date(2000, 7, 3)
assert B.data_do_fator(9999, hoje=date(2025, 2, 1))[0] == date(2025, 2, 21)
assert B.data_do_fator(1000, hoje=date(2026, 11, 5))[0] == date(2025, 2, 22)
assert B.data_do_fator(1645, hoje=date(2026, 11, 5))[0] == date(2026, 11, 29)
assert B.data_do_fator(0)[0] is None


# --- boleto bancário: montado só para o teste
def barras_teste(banco, fator, centavos, livre):
    sem_dv = f"{banco}9" + f"{fator:04d}{centavos:010d}{livre}"
    dv = B.mod11_bancario(sem_dv)
    return sem_dv[:4] + str(dv) + sem_dv[4:]


cb = barras_teste("341", 1645, 123456, "1790010435100479102015000")
linha = B.barras_para_linha_bancaria(cb)
assert len(cb) == 44 and len(linha) == 47
r = B.conferir(B.fmt_linha_bancaria(linha))
assert r["ok"] and r["barras"] == cb and r["banco_nome"] == "Itaú Unibanco" and r["valor"] == 1234.56, r
assert r["vencimento"] == date(2026, 11, 29)
r = B.conferir(cb)
assert r["ok"] and r["linha"] == linha
for pos in range(47):  # qualquer dígito trocado precisa ser detectado
    d = str((int(linha[pos]) + 3) % 10)
    alterada = linha[:pos] + d + linha[pos + 1:]
    assert not B.conferir(alterada)["ok"], pos
assert not B.conferir(cb[:10] + str((int(cb[10]) + 1) % 10) + cb[11:])["ok"]
assert B.conferir("123")["erro"]

# --- arrecadação: mod10 (3º dígito 6) e mod11 (3º dígito 8)
for ident in "68":
    resto = "00000012345" + "0001" + "2026110500123456789012345"
    base = "83" + ident
    sem_dv = base + resto[:40]
    fn = B.mod10 if ident == "6" else B.mod11_arrecadacao
    dv = fn(sem_dv)
    cba = sem_dv[:3] + str(dv) + sem_dv[3:]
    assert len(cba) == 44
    la = B.barras_para_linha_arrecadacao(cba)
    assert len(la) == 48
    r = B.conferir(B.fmt_linha_arrecadacao(la))
    assert r["ok"] and r["barras"] == cba and r["valor"] == 123.45 and "Energia" in r["segmento"], r
    assert B.conferir(cba)["ok"]
    ruim = la[:5] + str((int(la[5]) + 1) % 10) + la[6:]
    assert not B.conferir(ruim)["ok"]

print("Todos os testes de lógica passaram ✓")
