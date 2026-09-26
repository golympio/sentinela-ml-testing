"""Bloco C, parte 3: os casos-limite — onde o pipeline quebra, e onde ele deveria quebrar.

Dois dos sete testes deste arquivo **passam**, e estão aqui de propósito. Sem eles o arquivo
diria só "o SUT quebra nos limites", que é uma frase vazia: qualquer sistema quebra em
algum limite. Com eles, a afirmação fica precisa — o pipeline atravessa sem dificuldade o
lote de um motor só e o lote de valores constantes, e falha exatamente nos casos em que a
**falta de validação** é a causa.

O fio que costura os cinco vermelhos: o SUT não valida **nada** no ponto de serving. Não
valida tamanho de lote (D15), não valida faixa física (D21), não valida unicidade da chave
(D16). `Modelo._matriz` confere forma e finitude — e é só (SPEC P5). É a lição do
`mode='serve'` da aula 3: o contrato que existe no treino desaparece na hora de decidir.
"""
from __future__ import annotations

import numpy as np
import pytest

import sentinela as sn
from suite import fabrica, ficha

SENSORES_CONSTANTES = (
    "temperatura_c", "vibracao_rms", "pressao", "corrente_a", "rpm",
    "horas_operacao", "idade_equipamento_meses", "turno",
)


def _faixa_de_treino_do_risco() -> tuple[float, float]:
    """O intervalo de `maquina_risco` que o modelo viu no treino, da tabela congelada."""
    tabela = sn.features.risco_congelado()
    return min(tabela.values()), max(tabela.values())


# --- os dois que passam ------------------------------------------------------

@pytest.mark.adversarial
def test_lote_com_um_motor_so_funciona():
    """48 h de um motor só atravessam o pipeline e produzem decisão.

    É o caso de uso da planta pequena, e também o controle positivo dos testes de lote
    degenerado abaixo: mostra que o problema deles não é "lote pequeno", é **lote de uma
    linha** — a fronteira exata está entre os dois.
    """
    lote = fabrica.lote_de_um_motor(n_horas=48)
    saida = sn.pipeline.executar(lote)

    assert len(saida) == len(lote), (
        f"o pipeline devolveu {len(saida)} linhas para um lote de {len(lote)}"
    )
    assert saida["predicao"].isin((0, 1)).all(), "decisão fora de {0, 1}"
    assert np.isfinite(saida["probabilidade"]).all(), "probabilidade não finita"


@pytest.mark.adversarial
def test_lote_de_valores_identicos_nao_quebra_o_pipeline():
    """Leituras idênticas repetidas: a decisão é constante e `delta_temp_24h` é zero.

    O caso do sensor travado — o historiador repete o último valor. Não há divisão por
    variância nem normalização por desvio no pipeline, então nada explode; a variação de
    24 h é exatamente zero e todas as linhas recebem a mesma ordem. Um teste verde que
    documenta uma ausência de defeito é informação, não enfeite.
    """
    base = fabrica.lote(n_maquinas=1, n_horas=48)
    travado = base.copy()
    for coluna in SENSORES_CONSTANTES:
        travado[coluna] = base[coluna].iloc[0]

    limpo = sn.preprocessamento.limpar(travado)
    X = sn.features.construir(limpo)
    saida = sn.pipeline.executar(travado)

    assert (X["delta_temp_24h"] == 0.0).all(), (
        f"`delta_temp_24h` não zerou com temperatura constante: "
        f"{np.unique(X['delta_temp_24h'])}"
    )
    assert saida["predicao"].nunique() == 1, (
        f"leituras idênticas produziram decisões diferentes: "
        f"{sorted(saida['predicao'].unique())}"
    )


# --- os cinco que expõem defeito ---------------------------------------------

@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D15 — num lote de uma linha `maquina_risco` vira o próprio rótulo",
)
def test_lote_com_uma_linha_nao_produz_maquina_risco_degenerado():
    """Num lote de uma linha rotulada, `maquina_risco` vira o próprio rótulo.

    `_risco_por_maquina` faz `groupby("id_maquina")["falha_72h"].transform("mean")` quando a
    coluna de rótulo está presente. Com **uma** linha, a média do grupo é o valor daquela
    linha: o alvo entra inteiro na feature. É D02 na sua forma mais extrema, e a consequência
    é numérica além de conceitual — com rótulo 1 a feature vale **1,0**, quase cinco vezes o
    maior valor que o modelo viu no treino.

    O oráculo compara com o que o painel legitimamente teria: o valor da tabela congelada
    para aquele motor.
    """
    piso, teto = _faixa_de_treino_do_risco()
    tabela = sn.features.risco_congelado()
    observados = {}

    for rotulo in (0, 1):
        uma = fabrica.lote_de_uma_linha()
        uma["falha_72h"] = rotulo
        motor = uma["id_maquina"].iloc[0]
        X = sn.features.construir(sn.preprocessamento.limpar(uma))
        observados[rotulo] = (float(X["maquina_risco"].iloc[0]), motor)

    esperado = {r: tabela[m] for r, (_, m) in observados.items()}
    detalhe = "; ".join(
        f"rótulo {r}: maquina_risco = {v} (tabela congelada de {m}: {esperado[r]})"
        for r, (v, m) in observados.items()
    )
    assert all(v == esperado[r] for r, (v, _) in observados.items()), (
        f"um lote de uma linha rotulada faz `maquina_risco` virar o próprio rótulo — "
        f"{detalhe}. A faixa que o modelo viu no treino é [{piso}; {teto}]"
    )


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D15 — lote vazio devolve quadro vazio em silêncio, sem erro claro",
)
def test_lote_vazio_levanta_erro_claro():
    """Um lote vazio tem de levantar `ValueError`, não devolver um quadro vazio em silêncio.

    É o caso que acontece de verdade: o historiador não respondeu, ou o filtro do turno não
    casou com nada. Devolver zero linhas sem reclamar significa que o painel da sala de
    controle mostra "nenhuma ordem de manutenção" — indistinguível de "nenhum motor em
    risco". As duas situações exigem ações opostas do operador.
    """
    vazio = fabrica.lote_vazio()
    assert len(vazio) == 0

    with pytest.raises(ValueError):
        saida = sn.pipeline.executar(vazio)
        pytest.fail(
            f"o pipeline aceitou um lote vazio e devolveu um quadro de {saida.shape} "
            "sem levantar nada: 'sem dado' fica indistinguível de 'sem risco'"
        )


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D21 — o serving aceita leitura fora da faixa física e emite probabilidade",
)
def test_leitura_fisicamente_impossivel_e_rejeitada_antes_da_inferencia():
    """500 °C, pressão negativa: o serving tem de recusar, não emitir probabilidade.

    `Modelo._matriz` confere forma e finitude — e nada mais (SPEC P5). Um termopar em curto
    reporta 500 °C; a ficha técnica declara a faixa 45–95 °C. O SUT aceita, constrói as
    features e devolve um número com três casas decimais, que o painel exibe ao operador
    como se fosse uma medição.

    É exatamente a lição do `mode='serve'` da aula 3: a validação que existe (a ficha) nunca
    é chamada no ponto em que a decisão é tomada.
    """
    impossiveis = [("temperatura_c", 500.0), ("pressao", -3.0)]
    aceitas = []

    for coluna, valor in impossiveis:
        faixa = ficha.FICHA[coluna]
        lote = fabrica.com_leitura_fora_de_faixa(
            fabrica.lote(n_maquinas=2, n_horas=48), coluna, valor
        )
        try:
            saida = sn.pipeline.executar(lote)
        except ValueError:
            continue
        aceitas.append(
            f"{coluna}={valor} (faixa da ficha: {faixa.minimo}–{faixa.maximo} "
            f"{faixa.unidade}) → probabilidade {saida['probabilidade'].iloc[0]:.6f}"
        )

    assert not aceitas, (
        "o ponto de serving aceitou leitura fisicamente impossível e emitiu decisão: "
        + "; ".join(aceitas)
    )


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D16 — leitura reenviada dobra o peso na janela móvel",
)
def test_lote_com_leitura_duplicada_nao_dobra_o_peso_na_janela():
    """Reenvio do historiador: a mesma `(id_maquina, timestamp)` não pode pesar duas vezes.

    `limpar` não desduplica a chave. Uma retransmissão — evento rotineiro — faz a leitura
    entrar duas vezes na janela móvel e puxar a média para o próprio valor. Nenhuma medição
    nova aconteceu; o motor não mudou.
    """
    base = fabrica.lote(n_maquinas=1, n_horas=48)
    duplicado = fabrica.com_leitura_duplicada(base, posicao=20)

    limpo = sn.preprocessamento.limpar(duplicado)
    sobrevivem = int(limpo.duplicated(subset=["id_maquina", "timestamp"]).sum())

    X0 = sn.features.construir(sn.preprocessamento.limpar(base))
    X1 = sn.features.construir(limpo)

    antes = X0["temp_media_6h"].iloc[20:24].to_numpy()
    depois = X1["temp_media_6h"].iloc[20:24].to_numpy()
    movidas = [
        f"hora {20 + i}: {antes[i]:.6f} → {depois[i]:.6f} ({depois[i] - antes[i]:+.6f} °C)"
        for i in range(4)
        if antes[i] != depois[i]
    ]

    assert not movidas, (
        f"duplicar a leitura da hora 20 — {sobrevivem} chave(s) duplicada(s) sobreviveram "
        f"à limpeza, {len(X0)} linhas viraram {len(X1)} — moveu `temp_media_6h`: "
        + "; ".join(movidas)
    )


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D15 — o painel de um registro discorda do lote e perde o alarme",
)
def test_painel_de_um_registro_concorda_com_o_lote():
    """O painel da sala de controle tem de dar a mesma ordem que o lote noturno.

    `prever_registro` é o caminho do painel: uma leitura por vez. Mas o painel **não tem o
    lote** — ele constrói as features da linha que recebeu, sozinha. E é aí que
    `maquina_risco` degenera: no lote ela é a média do motor, no painel ela vira o rótulo
    daquela linha.

    O recorte do teste é o recorte que a operação faz — a lição de D09 e D22. Um teste que
    passasse as features **do lote** para `prever_registro` compararia o SUT consigo mesmo e
    passaria em verde sem tocar no defeito.
    """
    lote = fabrica.lote(n_maquinas=3, n_horas=48)
    saida = sn.pipeline.executar(lote)
    modelo = sn.modelo.carregar("v1")

    discordam = []
    for i in (30, 60, 90):
        no_lote = int(saida["predicao"].iloc[i])

        sozinha = lote.iloc[[i]].copy()
        X = sn.features.construir(sn.preprocessamento.limpar(sozinha))
        registro = {c: float(X[c].iloc[0]) for c in sn.features.ORDEM_FEATURES}
        no_painel = modelo.prever_registro(registro)

        if no_painel != no_lote:
            X_lote = sn.features.construir(sn.preprocessamento.limpar(lote))
            discordam.append(
                f"linha {i}: lote diz {no_lote}, painel diz {no_painel} "
                f"(maquina_risco {X_lote['maquina_risco'].iloc[i]:.6f} no lote contra "
                f"{registro['maquina_risco']:.6f} no painel)"
            )

    assert not discordam, (
        "a mesma leitura recebe ordens diferentes conforme entre pelo lote ou pelo painel: "
        + "; ".join(discordam)
    )
