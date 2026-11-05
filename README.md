# 💸 Pix & Boleto

App de desktop (Windows, PyQt6) **100% offline** com três abas:

1. **Gerar Pix (receber)** — você digita a SUA chave Pix (CPF, CNPJ, e-mail, telefone ou chave aleatória), nome, cidade, valor (opcional), identificador e mensagem. O app valida a chave (dígitos do CPF/CNPJ, telefone vira `+55...`), monta o **Pix Copia e Cola** no padrão BR Code do Banco Central (EMV-QRCPS, CRC16-CCITT) e mostra o **QR Code**. Dá pra copiar o texto e salvar o QR em PNG.
2. **Ler Pix** — cole um Pix Copia e Cola e veja chave, nome, cidade, valor, identificador e se o **CRC confere** (texto não foi corrompido/alterado).
3. **Conferir boleto** — cole a linha digitável (47 dígitos, bancário; 48 dígitos, contas de consumo/tributos) ou o código de barras (44). O app confere **todos os dígitos verificadores**, converte linha digitável ↔ código de barras e mostra banco, valor e vencimento (já com a virada do fator de vencimento de 22/02/2025).

> ⚠️ Esta ferramenta só **confere** boletos — não gera boleto nenhum. Números certos não garantem que o boleto é legítimo: confira se o banco e o beneficiário batem com quem você espera pagar.

## Como rodar

```
pip install -r requirements.txt   # segno (PyQt6 também é necessário)
python pix_boleto.pyw
```

## Arquivos

- `pix_boleto.pyw` — interface
- `pb_pix.py` — BR Code do Pix (montar, ler, CRC16, validação de chaves)
- `pb_boleto.py` — conferência de boletos (módulo 10/11, fator de vencimento, bancos)
- `pb_tests.py` — testes (`python pb_tests.py`), inclui o exemplo oficial do manual do BCB (CRC `1D3D`)

## Licença

MIT — veja `LICENSE`.
