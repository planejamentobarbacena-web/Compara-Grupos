import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(
    page_title="Validador de Credores – PCASP",
    layout="wide"
)

st.title("📊 Validação de Credores – Grupos 7 e 8")
st.caption(
    "Upload de CSV para validação automática entre "
    "Atos Potenciais Ativos (Grupo 7) e sua Execução (Grupo 8)."
)

uploaded_file = st.file_uploader(
    "📤 Envie o arquivo CSV do balancete",
    type=["csv"]
)

if uploaded_file:

    df = pd.read_csv(
        uploaded_file,
        sep=";",
        decimal=",",
        encoding="latin1",
        engine="python"
    )

# normaliza nomes de colunas
df.columns = (
    df.columns
    .str.strip()
    .str.lower()
    .str.normalize("NFKD")
    .str.encode("ascii", errors="ignore")
    .str.decode("utf-8")
)

col_mascara = "mascara"
col_desc = "descricao"
col_saldo = "saldo atual"
col_tipo = "tipo saldo"


    # --- 1️⃣ Reconstrução da máscara ---
    ultima = None
    completas = []

    for _, row in df.iterrows():
        if pd.notna(row[col_mascara]):
            ultima = str(row[col_mascara]).strip()
        completas.append(ultima)

    df["Mascara_Completa"] = completas

    # --- 2️⃣ Grupo ---
    df["Grupo"] = df["Mascara_Completa"].str.extract(r"^([78])")

    df = df[df["Grupo"].isin(["7", "8"])]

    # --- 3️⃣ Normalização ---
    def normalizar(m):
        partes = m.split(".")
        return ".".join(partes[1:6])

    df["Mascara_Normalizada"] = df["Mascara_Completa"].apply(normalizar)

    # --- 4️⃣ Valor ---
    def valor(row):
        if row["Grupo"] == "7" and row[col_tipo] == "D":
            return row[col_saldo]
        if row["Grupo"] == "8" and row[col_tipo] == "C":
            return row[col_saldo]
        return 0

    df["Valor"] = df.apply(valor, axis=1)

    # linhas com CNPJ
    df = df[df[col_desc].str.contains(r"\d{11,14}", na=False)]

    # --- 5️⃣ Agrupamento ---
    resumo = (
        df.groupby(["Mascara_Normalizada", col_desc, "Grupo"])["Valor"]
        .sum()
        .reset_index()
    )

    g7 = resumo[resumo["Grupo"] == "7"].rename(columns={"Valor": "Valor_G7"})
    g8 = resumo[resumo["Grupo"] == "8"].rename(columns={"Valor": "Valor_G8"})

    final = pd.merge(
        g7,
        g8,
        on=["Mascara_Normalizada", col_desc],
        how="outer"
    ).fillna(0)

    final["Diferença"] = final["Valor_G7"] - final["Valor_G8"]
    final["Status"] = final["Diferença"].apply(
        lambda x: "CORRETO" if abs(x) < 0.01 else "DIVERGENTE"
    )

    corretos = final[final["Status"] == "CORRETO"]
    divergentes = final[final["Status"] == "DIVERGENTE"]

    st.subheader("⚠️ Credores com Divergência")
    st.dataframe(divergentes, use_container_width=True)

    # --- Exportação ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        corretos.to_excel(writer, sheet_name="Credores Corretos", index=False)
        divergentes.to_excel(writer, sheet_name="Credores com Divergência", index=False)

    st.download_button(
        "📥 Baixar resultado",
        data=output.getvalue(),
        file_name="resultado_validacao_credores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


