"""O contrato de dados da planta, validado contra `dados/` — não contra o código.

O Bloco A do enunciado pede teste de dados, e não só de função: as faixas, as unidades
e o domínio de cada coluna vêm da ficha técnica do README do SUT, que vive em
`suite/ficha.py`. Aqui a ficha encontra os três CSVs de verdade.

Parte destes testes **mede** em vez de só julgar: prevalência, taxa de dropout e
proporção de psi vão para `medicoes.json`, porque o relatório precisa desses números.
"""
from __future__ import annotations

import pandas as pd
import pytest

import sentinela as sn
from suite import ficha

pytestmark = pytest.mark.unitario


# D17 está presente em `treino` e `producao` e **ausente** em `teste` — medido em
# docs/mapa-defeitos.md. Marcar os três conjuntos com xfail estrito derrubaria a suíte
# por XPASS em `teste`, que passa por mérito. Daí a marca ser por parâmetro.
D17_RPM = "D17 — `limpar` não valida faixa: há rpm acima de 1.800 atravessando o pipeline"
D17_PRESSAO = (
    "D17 — `limpar` não valida faixa: há pressão fora de 3,0–4,5 bar mesmo após converter psi"
)
CONJUNTOS_COM_D17 = ("treino", "producao")


def _params_d17(motivo: str):
    """Um `pytest.param` por conjunto, com xfail só onde o defeito foi medido."""
    return [
        pytest.param(
            nome,
            marks=[
                pytest.mark.defeito,
                pytest.mark.xfail(strict=True, reason=motivo),
            ],
        )
        if nome in CONJUNTOS_COM_D17
        else pytest.param(nome)
        for nome in sn.dados.CONJUNTOS
    ]


@pytest.fixture(params=sn.dados.CONJUNTOS)
def conjunto(request) -> str:
    return request.param


@pytest.fixture
def bruto(conjunto, request) -> pd.DataFrame:
    """O lote cru do conjunto sob teste, via as fixtures de sessão do conftest."""
    return request.getfixturevalue(f"lote_{conjunto}")


@pytest.fixture
def registro(medicoes, conjunto) -> dict:
    """Onde este conjunto grava o que mediu."""
    return medicoes["contrato_dados"].setdefault(conjunto, {})


def test_todas_as_colunas_declaradas_existem(bruto):
    assert ficha.validar_schema(bruto, sn.dados.COLUNAS) is True


@pytest.mark.parametrize("coluna", sorted(ficha.TIPOS_ESPERADOS))
def test_tipos_das_colunas_batem_com_o_contrato(bruto, coluna):
    assert ficha.validar_tipo(bruto, coluna) is True


def test_temperatura_esta_na_faixa_da_ficha(bruto):
    assert ficha.validar_faixa(bruto, "temperatura_c") is True


def test_corrente_esta_na_faixa_da_ficha(bruto):
    assert ficha.validar_faixa(bruto, "corrente_a") is True


def test_idade_equipamento_esta_na_faixa_da_ficha(bruto):
    assert ficha.validar_faixa(bruto, "idade_equipamento_meses") is True


@pytest.mark.parametrize("nome_conjunto", _params_d17(D17_RPM))
def test_rpm_esta_na_faixa_da_ficha(request, nome_conjunto):
    """A ficha diz 1.650–1.800 rpm. Há leituras acima em treino e produção."""
    bruto = request.getfixturevalue(f"lote_{nome_conjunto}")
    assert ficha.validar_faixa(bruto, "rpm") is True


@pytest.mark.parametrize("nome_conjunto", _params_d17(D17_PRESSAO))
def test_pressao_convertida_esta_na_faixa_da_ficha(request, nome_conjunto):
    """Depois de converter psi→bar, a pressão tem de caber em 3,0–4,5 bar.

    Converter é responsabilidade de quem lê o dado, já que o SUT não converte (D03).
    O que sobra fora da faixa **depois** da conversão é leitura fisicamente impossível.
    """
    bruto = request.getfixturevalue(f"lote_{nome_conjunto}")
    em_bar = ficha.converter_pressao_para_bar(bruto)
    assert ficha.validar_faixa(bruto, "pressao", valores=em_bar) is True


def test_unidade_pressao_so_tem_valores_conhecidos(bruto, registro):
    proporcao_psi = float((bruto["unidade_pressao"].str.strip().str.lower() == "psi").mean())
    registro["proporcao_psi"] = round(proporcao_psi, 6)
    assert ficha.validar_unidade_pressao(bruto) is True


def test_id_operador_segue_o_padrao_op_nn(bruto):
    assert ficha.validar_id_operador(bruto) is True


def test_turno_so_tem_um_dois_ou_tres(bruto):
    assert ficha.validar_dominio(bruto, "turno", ficha.TURNOS) is True


def test_alvo_e_binario_e_a_prevalencia_esta_registrada(bruto, registro):
    registro["prevalencia"] = round(float(bruto[ficha.ALVO].mean()), 6)
    registro["linhas"] = int(len(bruto))
    assert ficha.validar_dominio(bruto, ficha.ALVO, ficha.VALORES_ALVO) is True


def test_chave_id_maquina_timestamp_e_unica(bruto):
    assert ficha.validar_chave_unica(bruto) is True


def test_somente_vibracao_tem_valores_ausentes(bruto, registro):
    """O README documenta dropout **só** em `vibracao_rms`. Qualquer outro NaN é novo."""
    ausentes = {c: int(n) for c, n in bruto.isna().sum().items() if n}
    registro["taxa_dropout_vibracao"] = round(float(bruto["vibracao_rms"].isna().mean()), 6)

    assert set(ausentes) <= {"vibracao_rms"}, (
        f"colunas com ausentes fora do contrato: {sorted(set(ausentes) - {'vibracao_rms'})}"
    )


def test_conjuntos_nao_se_sobrepoem_no_tempo(_lote_treino, _lote_teste, _lote_producao):
    """Treino < teste < produção, sem interseção: é o que torna a linha de base honesta.

    Sobreposição aqui significaria que o modelo foi avaliado em hora que já viu treinar,
    e todo número do relatório perderia sentido.
    """
    janelas = {}
    for nome, df in (
        ("treino", _lote_treino),
        ("teste", _lote_teste),
        ("producao", _lote_producao),
    ):
        ts = pd.to_datetime(df["timestamp"])
        janelas[nome] = (ts.min(), ts.max())

    assert janelas["treino"][1] < janelas["teste"][0], (
        f"treino termina em {janelas['treino'][1]} e teste começa em {janelas['teste'][0]}"
    )
    assert janelas["teste"][1] < janelas["producao"][0], (
        f"teste termina em {janelas['teste'][1]} e produção começa em {janelas['producao'][0]}"
    )
