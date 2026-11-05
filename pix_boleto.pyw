"""💸 Pix & Boleto — gera o seu Pix (Copia e Cola + QR Code), lê um Pix colado e confere
boletos (dígitos verificadores, banco, valor e vencimento). Tudo offline.
Só CONFERE boletos: não gera boleto nenhum.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import segno  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFileDialog,  # noqa: E402
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QPushButton, QTabWidget, QVBoxLayout, QWidget)

import pb_boleto  # noqa: E402
import pb_pix  # noqa: E402

ACCENT = "#7c5cff"
OK_COR = "#79e0a8"
ERRO_COR = "#ff6b6b"

QSS = """
QWidget { background:#11131a; color:#e7e9f0; font:10pt 'Segoe UI'; }
#title { font:700 18pt 'Segoe UI'; }
#info { color:#8a93a8; }
#big { font:700 13pt 'Consolas','Segoe UI'; color:#79e0a8; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background:#1b202b; border:1px solid #2d3550;
    border-radius:8px; padding:6px; }
QPlainTextEdit { background:#0c0e14; border:1px solid #2d3550; border-radius:10px; color:#79e0a8;
    font:9pt 'Consolas'; }
QPushButton { background:#222a38; border:0; border-radius:10px; padding:9px 14px; }
QPushButton:hover { background:#2d3550; }
#go { background:#7c5cff; color:#fff; font-weight:600; padding:12px 16px; font-size:12pt; }
#go:hover { background:#8f74ff; }
#stop { background:#ff4d4d; color:#fff; font-weight:600; }
QTabWidget::pane { border:1px solid #2d3550; border-radius:10px; top:-1px; }
QTabBar::tab { background:#1b202b; padding:9px 18px; margin-right:4px; border-top-left-radius:8px;
    border-top-right-radius:8px; color:#8a93a8; }
QTabBar::tab:selected { background:#7c5cff; color:#fff; font-weight:600; }
#qr { background:#ffffff; border-radius:10px; }
#card { background:#171b25; border:1px solid #2d3550; border-radius:10px; padding:10px; }
#veredito { font:700 14pt 'Segoe UI'; padding:12px; border-radius:10px; }
#dica { color:#ffd479; background:#2a2416; border-radius:8px; padding:8px; }
"""


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(QColor("transparent"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ACCENT))
    p.translate(32, 32)
    p.rotate(45)
    p.drawRoundedRect(-20, -20, 40, 40, 8, 8)
    p.setBrush(QColor("#11131a"))
    p.drawRoundedRect(-8, -8, 16, 16, 3, 3)
    p.end()
    return QIcon(pm)


def campo_somente_leitura(texto=""):
    e = QLineEdit(texto)
    e.setReadOnly(True)
    return e


# ================================================================ aba 1
class AbaGerar(QWidget):
    def __init__(self):
        super().__init__()
        self.qr = None
        self.payload = ""
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(16)

        esq = QVBoxLayout()
        esq.addWidget(QLabel("Monte o Pix pra RECEBER com a sua própria chave.", objectName="info"))
        form = QFormLayout()
        form.setVerticalSpacing(8)
        kr = QHBoxLayout()
        self.chave = QLineEdit()
        self.chave.setPlaceholderText("CPF, CNPJ, e-mail, telefone ou chave aleatória")
        self.tipo = QComboBox()
        self.tipo.addItems(pb_pix.TIPOS)
        kr.addWidget(self.chave, 1)
        kr.addWidget(self.tipo)
        form.addRow("Sua chave Pix:", kr)
        self.nome = QLineEdit()
        self.nome.setMaxLength(25)
        self.nome.setPlaceholderText("Até 25 letras (acentos são removidos)")
        form.addRow("Nome do recebedor:", self.nome)
        self.cidade = QLineEdit()
        self.cidade.setMaxLength(15)
        self.cidade.setPlaceholderText("Até 15 letras")
        form.addRow("Cidade:", self.cidade)
        self.valor = QDoubleSpinBox()
        self.valor.setRange(0, 9_999_999_999.99)
        self.valor.setDecimals(2)
        self.valor.setPrefix("R$ ")
        self.valor.setSpecialValueText("Sem valor (quem paga digita)")
        self.valor.setGroupSeparatorShown(True)
        form.addRow("Valor (opcional):", self.valor)
        self.txid = QLineEdit("***")
        self.txid.setMaxLength(25)
        self.txid.setToolTip("Identificador: só letras e números, até 25. Deixe *** se não precisar.")
        form.addRow("Identificador (txid):", self.txid)
        self.msg = QLineEdit()
        self.msg.setPlaceholderText("Ex.: Aluguel de novembro (opcional)")
        form.addRow("Mensagem (opcional):", self.msg)
        esq.addLayout(form)

        self.go = QPushButton("⚡  Gerar Pix", objectName="go")
        self.go.clicked.connect(self.gerar)
        esq.addWidget(self.go)
        self.status = QLabel("", objectName="info")
        self.status.setWordWrap(True)
        esq.addWidget(self.status)
        esq.addWidget(QLabel("Pix Copia e Cola:"))
        self.saida = QPlainTextEdit()
        self.saida.setReadOnly(True)
        self.saida.setMaximumHeight(110)
        esq.addWidget(self.saida)
        br = QHBoxLayout()
        self.b_copiar = QPushButton("📋  Copiar texto")
        self.b_copiar.clicked.connect(self.copiar)
        self.b_salvar = QPushButton("💾  Salvar QR (PNG)")
        self.b_salvar.clicked.connect(self.salvar)
        br.addWidget(self.b_copiar)
        br.addWidget(self.b_salvar)
        esq.addLayout(br)
        esq.addStretch(1)
        root.addLayout(esq, 3)

        dir_ = QVBoxLayout()
        self.img = QLabel("O QR Code\naparece aqui", objectName="qr")
        self.img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img.setFixedSize(340, 340)
        self.img.setStyleSheet("color:#555;")
        dir_.addWidget(self.img, 0, Qt.AlignmentFlag.AlignHCenter)
        self.resumo = QLabel("", objectName="info")
        self.resumo.setWordWrap(True)
        self.resumo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dir_.addWidget(self.resumo)
        dir_.addStretch(1)
        root.addLayout(dir_, 2)
        self._botoes(False)

    def _botoes(self, on):
        self.b_copiar.setEnabled(on)
        self.b_salvar.setEnabled(on)

    def gerar(self):
        try:
            v = self.valor.value() or None
            payload, chave, tipo = pb_pix.montar_payload(
                self.chave.text(), self.nome.text(), self.cidade.text(), v,
                self.txid.text(), self.msg.text(), self.tipo.currentText())
        except ValueError as e:
            self.status.setText(f"<span style='color:{ERRO_COR}'>✗ {e}</span>")
            self.payload, self.qr = "", None
            self.saida.clear()
            self.resumo.clear()
            self.img.setPixmap(QPixmap())
            self.img.setText("O QR Code\naparece aqui")
            self._botoes(False)
            return
        self.payload = payload
        self.qr = segno.make(payload, error="m", micro=False)
        buf = io.BytesIO()
        self.qr.save(buf, kind="png", scale=8, border=3)
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "PNG")
        self.img.setPixmap(pm.scaled(330, 330, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        self.saida.setPlainText(payload)
        self.status.setText(f"<span style='color:{OK_COR}'>✓ Pix gerado.</span> Chave ({tipo}): {chave}")
        valor_txt = pb_boleto.fmt_reais(v) if v else "sem valor fixo"
        self.resumo.setText(f"{pb_pix.sem_acentos(self.nome.text())[:25]} — {valor_txt}\n"
                            "Teste lendo com o app do seu banco antes de mandar pra alguém.")
        self._botoes(True)

    def copiar(self):
        if self.payload:
            QApplication.clipboard().setText(self.payload)
            self.status.setText(f"<span style='color:{OK_COR}'>📋 Copiado! É só colar no chat.</span>")

    def salvar(self):
        if not self.qr:
            return
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar QR Code", os.path.expanduser("~/pix.png"),
                                                 "Imagem PNG (*.png)")
        if caminho:
            if not caminho.lower().endswith(".png"):
                caminho += ".png"
            self.qr.save(caminho, kind="png", scale=10, border=4)
            self.status.setText(f"<span style='color:{OK_COR}'>💾 Salvo em {caminho}</span>")


# ================================================================ aba 2
class AbaLer(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(9)
        root.addWidget(QLabel("Cole um Pix Copia e Cola pra ver pra quem vai o dinheiro antes de pagar.",
                              objectName="info"))
        self.entrada = QPlainTextEdit()
        self.entrada.setPlaceholderText("00020126...6304ABCD")
        self.entrada.setMaximumHeight(100)
        root.addWidget(self.entrada)
        br = QHBoxLayout()
        b_colar = QPushButton("📋  Colar")
        b_colar.clicked.connect(lambda: self.entrada.setPlainText(QApplication.clipboard().text()))
        self.go = QPushButton("🔍  Ler Pix", objectName="go")
        self.go.clicked.connect(self.ler)
        br.addWidget(b_colar)
        br.addWidget(self.go, 1)
        root.addLayout(br)

        self.veredito = QLabel("", objectName="veredito")
        self.veredito.setWordWrap(True)
        root.addWidget(self.veredito)
        form = QFormLayout()
        self.f = {}
        for k, rot in (("chave", "Chave Pix:"), ("tipo", "Tipo da chave:"), ("nome", "Nome do recebedor:"),
                       ("cidade", "Cidade:"), ("valor", "Valor:"), ("txid", "Identificador (txid):"),
                       ("mensagem", "Mensagem:"), ("url", "Link (Pix dinâmico):"), ("crc", "CRC:")):
            self.f[k] = campo_somente_leitura()
            form.addRow(rot, self.f[k])
        root.addLayout(form)
        root.addStretch(1)

    def ler(self):
        for e in self.f.values():
            e.clear()
        try:
            r = pb_pix.ler_payload(self.entrada.toPlainText())
        except ValueError as e:
            self._veredito(False, f"✗ {e}")
            return
        self.f["chave"].setText(r["chave"] or "(não encontrada)")
        self.f["tipo"].setText(pb_pix.tipo_da_chave(r["chave"]) if r["chave"] else
                               ("Pix dinâmico (dados ficam no link)" if r["url"] else "—"))
        self.f["nome"].setText(r["nome"])
        self.f["cidade"].setText(r["cidade"])
        self.f["valor"].setText(pb_boleto.fmt_reais(r["valor"]) if r["valor"] else "sem valor fixo")
        self.f["txid"].setText(r["txid"])
        self.f["mensagem"].setText(r["mensagem"])
        self.f["url"].setText(r["url"])
        if r["crc_lido"]:
            self.f["crc"].setText(f"lido {r['crc_lido']} · calculado {r['crc_calc'] or '?'}")
        else:
            self.f["crc"].setText("ausente")
        if not r["e_pix"]:
            self._veredito(False, "✗ Isso não tem o identificador br.gov.bcb.pix — não parece um Pix.")
        elif r["crc_ok"]:
            self._veredito(True, "✓ CRC confere — o texto não foi corrompido. Confira se o nome é de "
                                 "quem você quer pagar.")
        else:
            self._veredito(False, "✗ CRC não confere — o texto foi alterado ou está incompleto. Não pague.")

    def _veredito(self, ok, txt):
        cor = OK_COR if ok else ERRO_COR
        fundo = "#14301f" if ok else "#3a1618"
        self.veredito.setStyleSheet(f"color:{cor}; background:{fundo};")
        self.veredito.setText(txt)


# ================================================================ aba 3
class AbaBoleto(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(9)
        root.addWidget(QLabel("Cole a linha digitável (47 ou 48 números) ou o código de barras (44). "
                              "Pontos e espaços são ignorados. Este app só CONFERE boletos.",
                              objectName="info", wordWrap=True))
        er = QHBoxLayout()
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Ex.: 34191.79001 01043.510047 91020.150008 ...")
        self.entrada.returnPressed.connect(self.conferir)
        b_colar = QPushButton("📋  Colar")
        b_colar.clicked.connect(lambda: self.entrada.setText(QApplication.clipboard().text().strip()))
        er.addWidget(self.entrada, 1)
        er.addWidget(b_colar)
        root.addLayout(er)
        self.go = QPushButton("🔎  Conferir boleto", objectName="go")
        self.go.clicked.connect(self.conferir)
        root.addWidget(self.go)

        self.veredito = QLabel("", objectName="veredito")
        self.veredito.setWordWrap(True)
        root.addWidget(self.veredito)

        form = QFormLayout()
        self.f = {}
        for k, rot in (("tipo", "Tipo:"), ("banco", "Banco / segmento:"), ("valor", "Valor:"),
                       ("venc", "Vencimento:"), ("linha", "Linha digitável:"), ("barras", "Código de barras:"),
                       ("extra", "Outros dados:")):
            self.f[k] = campo_somente_leitura()
            form.addRow(rot, self.f[k])
        root.addLayout(form)
        root.addWidget(QLabel("Dígitos verificadores:"))
        self.detalhe = QPlainTextEdit()
        self.detalhe.setReadOnly(True)
        root.addWidget(self.detalhe, 1)
        dica = QLabel("💡 Dica: números certos não garantem que o boleto é legítimo — golpistas geram boletos "
                      "\"válidos\" com o banco deles. Confira se o BANCO e o BENEFICIÁRIO que aparecem no app "
                      "do seu banco batem com quem você espera pagar.", objectName="dica")
        dica.setWordWrap(True)
        root.addWidget(dica)

    def conferir(self):
        for e in self.f.values():
            e.clear()
        self.detalhe.clear()
        r = pb_boleto.conferir(self.entrada.text())
        if r["erro"]:
            self._veredito(False, f"✗ {r['erro']}")
            return
        self.f["tipo"].setText(f"{r['tipo']} — você colou o {r['entrada']}")
        if r["banco_codigo"]:
            self.f["banco"].setText(f"{r['banco_codigo']} — {r['banco_nome']}  ·  moeda: {r['moeda']}")
        else:
            self.f["banco"].setText(r["segmento"])
        self.f["valor"].setText(r["valor_txt"])
        if r["banco_codigo"]:
            if r["vencimento"]:
                self.f["venc"].setText(f"{r['vencimento']:%d/%m/%Y}  (fator {r['fator']}, {r['obs_venc']})")
            else:
                self.f["venc"].setText(f"{r['obs_venc']} (fator {r['fator']})")
        else:
            self.f["venc"].setText("contas de consumo/tributos não trazem vencimento no código")
        self.f["linha"].setText(r["linha_fmt"])
        self.f["barras"].setText(r["barras"])
        self.f["extra"].setText(r["empresa"] or (f"campo livre: {r['campo_livre']}" if r["campo_livre"] else ""))
        for e in self.f.values():
            e.setCursorPosition(0)
        linhas = []
        for nome, ok, lido, calc in r["checagens"]:
            marca = "✓" if ok else "✗"
            linhas.append(f"{marca} {nome}: lido {lido}, esperado {calc}")
        linhas += [f"⚠ {a}" for a in r["avisos"]]
        self.detalhe.setPlainText("\n".join(linhas))
        if r["ok"]:
            self._veredito(True, "✓ Números conferem")
        else:
            self._veredito(False, "✗ Algum dígito não confere — cuidado, pode ser boleto adulterado")

    def _veredito(self, ok, txt):
        cor = OK_COR if ok else ERRO_COR
        fundo = "#14301f" if ok else "#3a1618"
        self.veredito.setStyleSheet(f"color:{cor}; background:{fundo};")
        self.veredito.setText(txt)


# ================================================================ janela
class PixBoleto(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("💸 Pix & Boleto")
        self.setWindowIcon(app_icon())
        self.resize(1000, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(9)
        root.addWidget(QLabel("💸 Pix & Boleto", objectName="title"))
        root.addWidget(QLabel("Gere o seu Pix pra receber, leia um Pix antes de pagar e confira se um boleto "
                              "foi adulterado. Tudo offline.", objectName="info"))
        self.tabs = QTabWidget()
        self.aba_gerar = AbaGerar()
        self.aba_ler = AbaLer()
        self.aba_boleto = AbaBoleto()
        self.tabs.addTab(self.aba_gerar, "💰  Gerar Pix (receber)")
        self.tabs.addTab(self.aba_ler, "🔍  Ler Pix")
        self.tabs.addTab(self.aba_boleto, "🧾  Conferir boleto")
        root.addWidget(self.tabs, 1)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = PixBoleto()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
