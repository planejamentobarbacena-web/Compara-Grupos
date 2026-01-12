import streamlit as st
import pandas as pd
from io import BytesIO
import unicodedata

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

# -----------------------------
# Funções auxiliares
# -----------------------------
def normalizar_coluna(col):
    col = col.strip().lower()
    col = unicodedata.normalize("NFKD", col)
    col = col.encode("ascii", errors="ignore").decode("utf-8")
    return col

def localizar_coluna(df, palavras):
    for col in df.columns:
        for p in palavras:
            if p in col:
                return col
    return None

# -----------------------------
# Processamento
# -----------------------------
if uploaded_file:

    # leitura segura do CSV
    try:
        df = pd.read_csv(
            uploaded_file,
            sep=";",
            decimal=",",
            encoding="latin1",
            engine="python"
        )
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        st.stop()

    # normaliza nomes de colunas
    df.columns = [normalizar_coluna(c) for c in df.columns]

    # tenta localizar colunas necessárias
    col_mascara = localizar_coluna(df, ["mascara"])
    col_desc = localizar_coluna(df, ["descricao", "conta", "nome"])
    col_saldo = localizar_coluna(df, ["saldo"])
    col_tipo = localizar_coluna(df, ["tipo", "natureza"])

    colunas_necessarias = {
        "Máscara": col_mascara,
        "Descrição": col_desc,
        "Saldo": col_saldo,
        "Tipo de Saldo": col_tipo
    }

    faltando = [k for k, v in colunas_necessarias.items() if v is None]

    if faltando:
        st.error(
            "❌ Não foi possível identificar as seguintes colunas no arquivo:\n\n"
            + ", ".join(faltando)
        )
        st.stop()

    # -----------------------------
    # 1️⃣ Reconstrução da máscara
    # -----------------------------
    ultima = None
    completas = []

    for _, row in df.iterrows():
        if pd.notna(row[col_mascara]):
            ultima = str(row[col_mascara]).strip()
        completas.append(ultima)

    df["Mascara_Completa"] = completas

    # -----------------------------
    # 2️⃣ Identifica Grupo 7 ou 8
    # -----------------------------
    df["Grupo"] = df["Mascara_Completa"].str.extract(r"^([78])")
    df = df[df["Grupo"].isin(["7", "8"])]

    # -----------------------------
    # 3️⃣ Normaliza máscara (remove o grupo)
    # -----------------------------
    def normalizar_mascara(m):
        partes = m.split(".")
        return ".".join(partes[1:6]) if len(partes) > 1 else m

    df["Mascara_Normalizada"] = df["Mascara_Completa"].apply(normalizar_mascara)

    # -----------------------------
    # 4️⃣ Calcula valor correto
    # -----------------------------
    def calcular_valor(row):
        if row["Grupo"] == "7" and str(row[col_tipo]).upper().startswith("D"):
            return row[col_saldo]
        if row["Grupo"] == "8" and str(row[col_tipo]).upper().startswith("C"):
            return row[col_saldo]
        return 0

    df["Valor"] = df.apply(calcular_valor, axis=1)

    # -----------------------------
    # 5️⃣ Mantém apenas linhas com CPF/CNPJ
    # -----------------------------
    df = df[df[col_desc].astype(str).str.contains(r"\d{11,14}", na=False)]

    # -----------------------------
    # 6️⃣ Agrupamento
    # -----------------------------
    resumo = (
        df.groupby(["Mascara_Normalizada", col_desc, "Grupo"], as_index=False)["Valor"]
        .sum()
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

    # -----------------------------
    # Exibição
    # -----------------------------
    st.subheader("⚠️ Credores com Divergência")
    st.dataframe(divergentes, use_container_width=True)

    # -----------------------------
    # Exportação Excel
    # -----------------------------
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
