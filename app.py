import streamlit as st
import pandas as pd
from io import BytesIO

# --------------------------------------------------
# Configuração da página
# --------------------------------------------------
st.set_page_config(
    page_title="Validador de Credores – PCASP",
    layout="wide"
)

st.title("📊 Validação de Credores – Grupos 7 e 8")
st.caption(
    "Validação automática entre CONTROLES DEVEDORES (Grupo 7) "
    "e CONTROLES CREDORES – EXECUÇÃO (Grupo 8)."
)

# --------------------------------------------------
# Upload
# --------------------------------------------------
uploaded_file = st.file_uploader(
    "📤 Envie o arquivo CSV do balancete",
    type=["csv"]
)

if not uploaded_file:
    st.stop()

# --------------------------------------------------
# Leitura segura do CSV
# --------------------------------------------------
try:
    df = pd.read_csv(
        uploaded_file,
        sep=";",
        decimal=",",
        encoding="utf-8",
        engine="python"
    )
except UnicodeDecodeError:
    df = pd.read_csv(
        uploaded_file,
        sep=";",
        decimal=",",
        encoding="latin1",
        engine="python"
    )

# --------------------------------------------------
# Normalização leve de colunas
# --------------------------------------------------
df.columns = df.columns.str.strip().str.lower()

# --------------------------------------------------
# Mapeamento FIXO de colunas (layout conhecido)
# --------------------------------------------------
COL_MASCARA = "máscara"
COL_DESC = "descrição"
COL_SALDO = "saldo atual"
COL_TIPO_1 = "tipo saldo"
COL_TIPO_2 = "tipo saldo.1"

# escolhe automaticamente a coluna correta de tipo saldo
if COL_TIPO_2 in df.columns:
    COL_TIPO = COL_TIPO_2
else:
    COL_TIPO = COL_TIPO_1

# --------------------------------------------------
# Reconstrução da máscara completa
# --------------------------------------------------
ultima_mascara = None
mascaras = []

for _, row in df.iterrows():
    valor = row.get(COL_MASCARA)
    if pd.notna(valor) and str(valor).strip() != "":
        ultima_mascara = str(valor).strip()
    mascaras.append(ultima_mascara)

df["mascara_completa"] = mascaras

# --------------------------------------------------
# Identificação do Grupo (7 ou 8)
# --------------------------------------------------
df["grupo"] = df["mascara_completa"].str.extract(r"^([78])")
df = df[df["grupo"].isin(["7", "8"])]

# --------------------------------------------------
# Normalização da máscara
# remove 7 ou 8 e limita até nível 6
# --------------------------------------------------
def normalizar_mascara(m):
    partes = m.split(".")
    return ".".join(partes[1:7])

df["mascara_normalizada"] = df["mascara_completa"].apply(normalizar_mascara)

# --------------------------------------------------
# Conversão segura do saldo
# --------------------------------------------------
df[COL_SALDO] = (
    df[COL_SALDO]
    .astype(str)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)

df[COL_SALDO] = pd.to_numeric(df[COL_SALDO], errors="coerce").fillna(0)

# --------------------------------------------------
# Regra de valor
# Grupo 7 → Débito
# Grupo 8 → Crédito
# --------------------------------------------------
def calcular_valor(row):
    tipo = row.get(COL_TIPO)

    if not isinstance(tipo, str):
        return 0

    tipo = tipo.upper().strip()

    if row["grupo"] == "7" and tipo.startswith("D"):
        return row[COL_SALDO]

    if row["grupo"] == "8" and tipo.startswith("C"):
        return row[COL_SALDO]

    return 0

df["valor"] = df.apply(calcular_valor, axis=1)

# --------------------------------------------------
# Apenas linhas com CPF/CNPJ
# --------------------------------------------------
df = df[df[COL_DESC].str.contains(r"\d{11,14}", na=False)]

# --------------------------------------------------
# Agrupamento (aceita soma entre níveis)
# --------------------------------------------------
resumo = (
    df.groupby(
        ["mascara_normalizada", COL_DESC, "grupo"],
        as_index=False
    )["valor"]
    .sum()
)

g7 = resumo[resumo["grupo"] == "7"].rename(columns={"valor": "valor_g7"})
g8 = resumo[resumo["grupo"] == "8"].rename(columns={"valor": "valor_g8"})

final = pd.merge(
    g7,
    g8,
    on=["mascara_normalizada", COL_DESC],
    how="outer"
).fillna(0)

# --------------------------------------------------
# Validação
# --------------------------------------------------
final["diferença"] = final["valor_g7"] - final["valor_g8"]
final["status"] = final["diferença"].apply(
    lambda x: "CORRETO" if abs(x) < 0.01 else "DIVERGENTE"
)

corretos = final[final["status"] == "CORRETO"]
divergentes = final[final["status"] == "DIVERGENTE"]

# --------------------------------------------------
# Exibição
# --------------------------------------------------
st.subheader("⚠️ Credores com Divergência")
st.dataframe(divergentes, use_container_width=True)

st.subheader("✅ Credores Corretos")
st.dataframe(corretos, use_container_width=True)

# --------------------------------------------------
# Exportação Excel
# --------------------------------------------------
output = BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    corretos.to_excel(writer, sheet_name="Credores Corretos", index=False)
    divergentes.to_excel(writer, sheet_name="Credores com Divergência", index=False)

st.download_button(
    "📥 Baixar resultado em Excel",
    data=output.getvalue(),
    file_name="validacao_credores_grupos_7_e_8.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
