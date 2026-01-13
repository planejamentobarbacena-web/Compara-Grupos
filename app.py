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
    "Comparação automática entre CONTROLES DEVEDORES (Grupo 7) "
    "e CONTROLES CREDORES (Grupo 8)."
)

# --------------------------------------------------
# Upload
# --------------------------------------------------
uploaded_file = st.file_uploader(
    "📤 Arraste e solte o arquivo CSV aqui ou clique para selecionar",
    type=["csv"]
)

if not uploaded_file:
    st.stop()

# --------------------------------------------------
# Leitura robusta do CSV
# --------------------------------------------------
try:
    df = pd.read_csv(uploaded_file, sep=";", decimal=",", encoding="utf-8", engine="python")
except UnicodeDecodeError:
    df = pd.read_csv(uploaded_file, sep=";", decimal=",", encoding="latin1", engine="python")

df.columns = df.columns.str.strip().str.lower()

# --------------------------------------------------
# Mapeamento fixo de colunas
# --------------------------------------------------
COL_MASCARA = "máscara"
COL_DESC = "descrição"
COL_SALDO = "saldo atual"
COL_TIPO = "tipo saldo.1" if "tipo saldo.1" in df.columns else "tipo saldo"

# --------------------------------------------------
# Função de formatação monetária (DEFINIDA ANTES DO USO)
# --------------------------------------------------
def formatar_moeda(df, colunas):
    for col in colunas:
        df[col] = df[col].apply(
            lambda x: f"R$ {x:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    return df

# --------------------------------------------------
# Reconstrução da máscara completa
# --------------------------------------------------
ultima = None
mascaras = []

for _, row in df.iterrows():
    val = row.get(COL_MASCARA)
    if pd.notna(val) and str(val).strip() != "":
        ultima = str(val).strip()
    mascaras.append(ultima)

df["mascara_completa"] = mascaras

# --------------------------------------------------
# Identificação do grupo
# --------------------------------------------------
df["grupo"] = df["mascara_completa"].str.extract(r"^([78])")
df = df[df["grupo"].isin(["7", "8"])]

# --------------------------------------------------
# Normalização da máscara
# remove 7/8 e mantém até o nível correto
# --------------------------------------------------
def normalizar_mascara(m):
    partes = m.split(".")
    partes = partes[1:]  # remove grupo
    return ".".join(partes[:5])

df["mascara_normalizada"] = df["mascara_completa"].apply(normalizar_mascara)

# --------------------------------------------------
# Conversão do saldo atual
# --------------------------------------------------
df[COL_SALDO] = (
    df[COL_SALDO]
    .astype(str)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)

df[COL_SALDO] = pd.to_numeric(df[COL_SALDO], errors="coerce").fillna(0)

# --------------------------------------------------
# Regra de valor (Saldo Atual + Tipo Saldo)
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
# Agrupamento
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

final = final.drop(columns=["grupo_x", "grupo_y"], errors="ignore")

# --------------------------------------------------
# Validação
# --------------------------------------------------
final["diferença"] = final["valor_g7"] - final["valor_g8"]
final["status"] = final["diferença"].apply(
    lambda x: "CORRETO" if abs(x) < 0.01 else "DIVERGENTE"
)

# --------------------------------------------------
# Ajuste final de colunas (exibição)
# --------------------------------------------------
final = final.rename(columns={
    "mascara_normalizada": "Máscara Delimitada",
    "descrição": "Credor",
    "valor_g7": "Valor - Grupo 7",
    "valor_g8": "Valor - Grupo 8",
    "diferença": "Diferença",
    "status": "Status"
})

corretos = final[final["Status"] == "CORRETO"].copy()
divergentes = final[final["Status"] == "DIVERGENTE"].copy()

COLS_MOEDA = [
    "Valor - Grupo 7",
    "Valor - Grupo 8",
    "Diferença"
]

corretos = formatar_moeda(corretos, COLS_MOEDA)
divergentes = formatar_moeda(divergentes, COLS_MOEDA)

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

