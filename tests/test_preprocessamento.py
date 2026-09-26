"""`preprocessamento.limpar` — o que ele promete e o que ele faz.

Primeira etapa do pipeline. Depois daqui `features.construir` assume quadro limpo, então
tudo que passar batido aqui vira feature com cara de medição.

Os testes de defeito nascem do que a ficha técnica exige e o código não faz: converter
psi, rejeitar unidade desconhecida, imputar vibração dentro da faixa física, não sumir
com linha em silêncio, desduplicar leitura reenviada, nomear a coluna no erro, e deixar
rastrear a linha de origem.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sentinela as sn
from suite import fabrica, ficha

pytestmark = pytest.mark.unitario


@pytest.fixture
def lote():
    return fabrica.lote(n_maquinas=3, n_horas=48, seed=42)


# --- o que `limpar` cumpre -------------------------------------------------

def test_limpar_nao_modifica_o_quadro_de_entrada(lote):
    antes = lote.copy(deep=True)
    sn.preprocessamento.limpar(lote)
    pd.testing.assert_frame_equal(lote, antes)


def test_limpar_converte_timestamp_para_datetime(lote):
    limpo = sn.preprocessamento.limpar(lote)
    assert pd.api.types.is_datetime64_any_dtype(limpo["timestamp"])


def test_limpar_normaliza_id_maquina_e_operador_para_maiusculo(lote):
    sujo = lote.assign(
        id_maquina="  " + lote["id_maquina"].str.lower() + " ",
        id_operador="  " + lote["id_operador"].str.lower() + " ",
    )
    limpo = sn.preprocessamento.limpar(sujo)

    assert (limpo["id_maquina"] == limpo["id_maquina"].str.strip().str.upper()).all()
    assert (limpo["id_operador"] == limpo["id_operador"].str.strip().str.upper()).all()


def test_limpar_normaliza_unidade_pressao_para_minusculo(lote):
    sujo = lote.assign(unidade_pressao=" BAR ")
    limpo = sn.preprocessamento.limpar(sujo)
    assert set(limpo["unidade_pressao"].unique()) == {"bar"}


def test_limpar_e_idempotente(lote):
    """`limpar(limpar(df))` tem de ser `limpar(df)`: a etapa não pode acumular efeito."""
    uma = sn.preprocessamento.limpar(lote)
    duas = sn.preprocessamento.limpar(uma)
    pd.testing.assert_frame_equal(uma, duas)


# --- o que `limpar` deveria cumprir e não cumpre ---------------------------

@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D03 — `unidade_pressao` é normalizada mas nunca usada: psi entra como se fosse bar")
def test_limpar_converte_pressao_de_psi_para_bar(lote):
    """A mesma pressão física em duas unidades tem de sair igual — Mars Climate Orbiter.

    O SUT normaliza `unidade_pressao` para minúsculo e nunca a usa para converter.
    """
    em_psi = fabrica.com_linhas_em_psi(lote, fracao=1.0, seed=1)
    limpo = sn.preprocessamento.limpar(em_psi)

    esperado = ficha.converter_pressao_para_bar(em_psi).to_numpy()
    np.testing.assert_allclose(limpo["pressao"].to_numpy(), esperado, rtol=1e-9)


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D19 — só `.lower()` em `unidade_pressao`, sem validar o domínio")
def test_limpar_rejeita_unidade_de_pressao_desconhecida(lote):
    """Um CLP novo reportando em kgf/cm² não pode entrar sem aviso."""
    desconhecida = lote.assign(unidade_pressao="kgf/cm2")
    with pytest.raises(ValueError, match="unidade_pressao"):
        sn.preprocessamento.limpar(desconhecida)


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D04 — `fillna(0.0)` imputa 0,0 mm/s, fora da faixa física 1,2–8,0 do sensor")
def test_vibracao_imputada_fica_na_faixa_fisica_do_sensor(lote):
    """O SUT imputa 0,0; a ficha diz que o sensor mede 1,2–8,0 mm/s.

    0,0 mm/s não é "sensor falhou", é "motor parado" — e o modelo lê como medição.
    """
    com_buraco = fabrica.com_dropout_de_vibracao(lote, fracao=0.2, seed=3)
    faltava = com_buraco["vibracao_rms"].isna().to_numpy()
    limpo = sn.preprocessamento.limpar(com_buraco)

    imputados = limpo["vibracao_rms"].to_numpy()[faltava[: len(limpo)]]
    faixa = ficha.FICHA["vibracao_rms"]
    fora = imputados[(imputados < faixa.minimo) | (imputados > faixa.maximo)]
    assert fora.size == 0, (
        f"{fora.size} valores imputados fora da faixa física "
        f"[{faixa.minimo}, {faixa.maximo}] mm/s; exemplo: {fora[:3]}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D05 — `limpo[limpo['rpm'] >= 1.0]` descarta linhas sem registro auditável")
def test_limpar_nao_descarta_linhas_silenciosamente(lote):
    """Se uma leitura some, tem de haver registro de que sumiu."""
    com_parado = fabrica.com_leitura_fora_de_faixa(lote, "rpm", 0.5, posicao=0)
    limpo = sn.preprocessamento.limpar(com_parado)
    assert len(limpo) == len(com_parado), (
        f"{len(com_parado) - len(limpo)} linhas desapareceram sem auditoria"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D05 — o corte é em 1,0 rpm, mas a ficha diz que medição válida começa em 1.650")
def test_limpar_descarta_so_o_que_a_ficha_chama_de_eixo_parado(lote):
    """O SUT corta em rpm < 1,0. A ficha diz que medição válida começa em 1.650 rpm.

    Entre 1,0 e 1.650 há leitura inválida atravessando como se fosse boa.
    """
    invalida = fabrica.com_leitura_fora_de_faixa(lote, "rpm", 5.0, posicao=0)
    limpo = sn.preprocessamento.limpar(invalida)
    assert 5.0 not in set(limpo["rpm"].to_numpy()), (
        "rpm=5 atravessou a limpeza: o SUT só corta abaixo de "
        f"{sn.preprocessamento.RPM_MINIMO}"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D16 — `limpar` não desduplica `(id_maquina, timestamp)`: reenvio dobra o peso")
def test_limpar_desduplica_a_chave_id_maquina_timestamp(lote):
    """Reenvio do historiador não pode dobrar o peso de uma leitura nas janelas."""
    reenviado = fabrica.com_leitura_duplicada(lote, posicao=0)
    limpo = sn.preprocessamento.limpar(reenviado)
    assert not limpo.duplicated(["id_maquina", "timestamp"]).any(), (
        f"{int(limpo.duplicated(['id_maquina', 'timestamp']).sum())} chaves duplicadas "
        "sobreviveram à limpeza"
    )


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D18 — `.astype(int)` sem validação: o erro não nomeia a coluna que quebrou")
@pytest.mark.parametrize("coluna", ["turno", "idade_equipamento_meses", "id_operador"])
def test_limpar_falha_com_mensagem_que_nomeia_a_coluna(lote, coluna):
    """Plantão às 3h da manhã: o erro tem de dizer qual coluna quebrou."""
    quebrado = lote.copy()
    quebrado.loc[quebrado.index[0], coluna] = np.nan
    with pytest.raises(Exception, match=coluna):
        sn.preprocessamento.limpar(quebrado)


@pytest.mark.defeito
@pytest.mark.xfail(strict=True, reason="D22 — `reset_index(drop=True)` descarta a rastreabilidade da linha de origem")
def test_limpar_preserva_rastreabilidade_da_linha_original(lote):
    """`reset_index(drop=True)` joga fora a única chance de auditar o que saiu.

    Só aparece quando alguma linha é de fato descartada: com o lote inteiro sobrevivendo,
    o índice reconstruído coincide com o original por acidente e o defeito fica invisível.
    """
    com_invalida = fabrica.com_leitura_fora_de_faixa(lote, "rpm", 0.5, posicao=10)
    sobreviventes = com_invalida.index[
        com_invalida["rpm"] >= sn.preprocessamento.RPM_MINIMO
    ]
    limpo = sn.preprocessamento.limpar(com_invalida)

    assert "indice_origem" in limpo.columns or limpo.index.equals(sobreviventes), (
        "não há como casar a linha de saída com a de entrada: o índice foi reconstruído "
        f"como {type(limpo.index).__name__} 0..{len(limpo) - 1} e nenhuma coluna de "
        "origem foi preservada"
    )
