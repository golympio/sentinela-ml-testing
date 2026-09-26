"""Bloco C, parte 1: perturbação abaixo do ruído do sensor, e o seu par legítimo.

A ficha técnica do SUT declara ruído de **±1,0 °C** na temperatura (SPEC P9,
`ficha.RUIDO_TEMPERATURA_C`). O número não é decorativo: ele diz que duas leituras do mesmo
motor que difiram por menos de 1,0 °C são **fisicamente indistinguíveis** — o sensor não
consegue separá-las. Se a decisão muda dentro dessa faixa, a planta recebe ordens de
manutenção opostas para o mesmo estado físico, e qual delas chega é sorteio do erro do
sensor.

**A lição das aulas 4 e 6 governa o desenho:** teste adversarial não é sobre nunca mudar de
opinião — é sobre não mudar **por motivo errado**. Por isso a perturbação ilegítima vem
sempre acompanhada do seu par legítimo: uma mudança física real (+15 °C sustentados por
24 h) **deve** mudar a decisão, e o teste que a verifica declara o lado esperado do flip, não
uma igualdade. Sem esse par, um modelo que ignorasse a temperatura inteira passaria em todos
os testes de invariância deste arquivo com nota máxima.

Tudo é lido **sem vazamento** — a simulação do serving (SPEC C10). É o quadro que a planta
teria em mãos na hora de decidir, e é a convenção que o Bloco B fixou para todo veredito.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sentinela as sn
from suite import ficha, harness, perturbacao

# Três amplitudes estritamente abaixo do ruído declarado. A menor é **um décimo** dele:
# nenhuma leitura do historiador conseguiria distinguir as duas medições.
AMPLITUDES_SUB_RUIDO = (0.1, 0.2, 0.4)

# A quarta entra na tabela de evidência (V9) como referência: é o ruído declarado em cheio.
AMPLITUDES_MEDIDAS = AMPLITUDES_SUB_RUIDO + (ficha.RUIDO_TEMPERATURA_C,)

VERSOES = ("v1", "v2")

# 24 h consecutivas de cada motor — o recorte do par legítimo. As mesmas linhas servem ao
# controle com ruído, para que a comparação entre os dois não misture tamanho de amostra.
HORAS_SUSTENTADAS = 24
AQUECIMENTO_C = 15.0


@pytest.fixture(scope="session")
def _tabela_de_flip(_lote_teste):
    """A tabela inteira de flip (2 versões × 4 amplitudes), medida uma vez por sessão.

    Injeta `_lote_teste` — o lote de sessão — e o primeiro ato é `limpar`, que copia. A
    convenção de `docs/decisoes.md` proíbe injetar `_lote_x` **num teste**, porque metade
    dos testes deste bloco muta o quadro; aqui o quadro compartilhado nunca é tocado, e
    medir 10 passagens de floresta uma vez só é o que mantém o Bloco C dentro do orçamento
    de tempo de NF6.

    Devolve `(limpo, base, tabela)`: o lote limpo, as decisões sem perturbação por versão,
    e `tabela[versao][amplitude] -> {taxa, para_cima, para_baixo}`.
    """
    limpo = sn.preprocessamento.limpar(_lote_teste)

    base = {}
    tabela = {}
    for versao in VERSOES:
        _, _, decisao = harness.prever_sem_vazamento(limpo, versao)
        base[versao] = decisao
        tabela[versao] = {}
        for amplitude in AMPLITUDES_MEDIDAS:
            perturbado = perturbacao.perturbar_coluna(
                limpo, "temperatura_c", amplitude, seed=42
            )
            _, _, decisao_perturbada = harness.prever_sem_vazamento(perturbado, versao)
            tabela[versao][amplitude] = perturbacao.taxa_de_flip(
                base[versao], decisao_perturbada
            )
    return limpo, base, tabela


# Vermelho nas TRÊS amplitudes e nas duas versões (ver `docs/mapa-defeitos.md`, D14), então
# o xfail vai na função. A marca por `pytest.param` é reservada ao defeito que só existe em
# parte dos parâmetros — marcar a função ali produziria XPASS e derrubaria a suíte.
@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D14 — a decisão muda com perturbação abaixo do ruído de ±1,0 °C do sensor",
)
@pytest.mark.parametrize("amplitude", AMPLITUDES_SUB_RUIDO)
def test_perturbacao_menor_que_o_ruido_do_sensor_nao_muda_a_decisao(
    amplitude, _tabela_de_flip
):
    """Abaixo do ruído do sensor, a decisão **não pode** mudar — em nenhuma das versões.

    O oráculo é a taxa de flip **zero**, e não "pequena": duas leituras que o sensor não
    distingue têm de produzir a mesma ordem de manutenção. Uma taxa de 0,3 % parece
    desprezível num slide e não é: com 4.200 leituras por lote, são doze motores cuja ordem
    depende do erro de medição, e não do estado do motor.
    """
    _, _, tabela = _tabela_de_flip

    culpadas = {v: tabela[v][amplitude] for v in VERSOES if tabela[v][amplitude]["taxa"] > 0}
    detalhe = "; ".join(
        f"{v}: {f['taxa'] * 100:.4f}% ({f['para_cima'] + f['para_baixo']} decisões — "
        f"{f['para_cima']} para cima, {f['para_baixo']} para baixo)"
        for v, f in culpadas.items()
    )
    assert not culpadas, (
        f"perturbação de ±{amplitude} °C — {amplitude / ficha.RUIDO_TEMPERATURA_C:.0%} do "
        f"ruído declarado de ±{ficha.RUIDO_TEMPERATURA_C} °C — mudou decisões: {detalhe}"
    )


@pytest.mark.adversarial
def test_taxa_de_flip_cresce_com_a_amplitude(_tabela_de_flip, medicoes):
    """A taxa cresce com a amplitude — e a tabela inteira vai para `medicoes.json` (V9).

    É o teste que **mede**, não o que acusa. A monotonia é a sanidade mínima do
    instrumento: se perturbar mais produzisse menos flip, o erro estaria nesta suíte.
    """
    _, _, tabela = _tabela_de_flip

    for versao in VERSOES:
        taxas = [tabela[versao][a]["taxa"] for a in AMPLITUDES_MEDIDAS]
        assert all(taxas[i] <= taxas[i + 1] for i in range(len(taxas) - 1)), (
            f"{versao}: a taxa de flip não é monótona nas amplitudes "
            f"{AMPLITUDES_MEDIDAS}: {taxas}"
        )

    # Esquema de SPEC C8: `flip` é `{versao: {amplitude: {taxa, para_cima, para_baixo}}}`.
    # Chave de amplitude como texto porque JSON não tem chave numérica; `sort_keys=True` no
    # despejo mantém o arquivo comparável byte a byte entre duas rodadas (S13).
    medicoes["flip"] = {
        versao: {f"{a}": tabela[versao][a] for a in AMPLITUDES_MEDIDAS}
        for versao in VERSOES
    }


@pytest.mark.adversarial
def test_flips_para_baixo_sao_registrados(_tabela_de_flip):
    """No ruído declarado em cheio, o alarme **some** — e isso é contado à parte.

    `para_cima` é uma equipe deslocada à toa; `para_baixo` é um motor que queima. As duas
    direções não custam o mesmo (é a assimetria de 20× que o limiar de custo do Bloco B
    assume), então a taxa agregada não pode ser o único número reportado: ela esconde
    exatamente o erro caro.
    """
    limpo, _, tabela = _tabela_de_flip
    ruido = ficha.RUIDO_TEMPERATURA_C

    for versao in VERSOES:
        f = tabela[versao][ruido]
        assert f["para_cima"] + f["para_baixo"] == round(f["taxa"] * len(limpo)), (
            f"{versao}: a soma das direções não reconstrói a taxa — {f}"
        )
        assert f["para_baixo"] > 0, (
            f"{versao}: a ±{ruido} °C nenhum alarme sumiu ({f}); se isso for verdade, a "
            "contagem por direção deixou de ser informativa e o oráculo precisa de revisão"
        )


# A v2 é mais instável em 4 de 4 amplitudes medidas: o defeito não depende do parâmetro.
@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D14 — a v2 vira mais decisões que a v1 sob a mesma perturbação sub-ruído",
)
@pytest.mark.parametrize("amplitude", AMPLITUDES_SUB_RUIDO)
def test_v2_nao_e_mais_instavel_que_a_v1(amplitude, _tabela_de_flip):
    """A v2, que a Nortemec quer promover, não pode ser mais sensível ao erro do sensor.

    A v2 é a floresta mais profunda: mais cortes, mais fronteiras de decisão, e portanto
    mais chance de que uma delas passe dentro do erro de medição. Promover um modelo que
    troca robustez por acurácia é exatamente a decisão que o Bloco B já mostrou ter sido
    tomada com o instrumento errado — aqui ela aparece por um terceiro eixo.
    """
    _, _, tabela = _tabela_de_flip
    v1, v2 = tabela["v1"][amplitude], tabela["v2"][amplitude]

    assert v2["taxa"] <= v1["taxa"], (
        f"a ±{amplitude} °C a v2 vira {v2['taxa'] * 100:.4f}% das decisões contra "
        f"{v1['taxa'] * 100:.4f}% da v1 — {v2['taxa'] / v1['taxa']:.2f}× mais instável "
        f"(v2: {v2['para_cima']}↑/{v2['para_baixo']}↓; v1: {v1['para_cima']}↑/"
        f"{v1['para_baixo']}↓)"
    )


@pytest.mark.adversarial
def test_mudanca_fisica_real_de_temperatura_muda_a_decisao(_tabela_de_flip):
    """O par legítimo: +15 °C sustentados por 24 h **devem** mudar a decisão, para cima.

    Este é o teste que dá sentido a todos os outros deste arquivo. Sem ele, um modelo que
    ignorasse a temperatura passaria em cada teste de invariância acima — a invariância
    perfeita e a inutilidade perfeita são indistinguíveis por um oráculo de igualdade
    (aula 4). Por isso aqui o oráculo declara o **lado** esperado, não só a diferença.

    O controle é o mesmo ruído de ±0,4 °C aplicado **nas mesmas linhas**, para que a
    comparação não confunda tamanho de efeito com tamanho de amostra: 15 °C de física real
    têm de mover mais decisões que 0,4 °C de erro de sensor.
    """
    limpo, base, _ = _tabela_de_flip

    # As primeiras 24 h de cada motor, na ordem cronológica por motor.
    janela = (
        limpo.sort_values(["id_maquina", "timestamp"])
        .groupby("id_maquina", sort=False)
        .head(HORAS_SUSTENTADAS)
        .index
    )

    quente = limpo.copy()
    quente.loc[janela, "temperatura_c"] = (
        quente.loc[janela, "temperatura_c"] + AQUECIMENTO_C
    )

    ruidoso = limpo.copy()
    ruidoso.loc[janela, "temperatura_c"] = perturbacao.perturbar_coluna(
        limpo.loc[janela], "temperatura_c", 0.4, seed=42
    )["temperatura_c"]

    for versao in VERSOES:
        _, _, decisao_quente = harness.prever_sem_vazamento(quente, versao)
        _, _, decisao_ruidosa = harness.prever_sem_vazamento(ruidoso, versao)
        fisico = perturbacao.taxa_de_flip(base[versao], decisao_quente)
        sensor = perturbacao.taxa_de_flip(base[versao], decisao_ruidosa)

        assert fisico["para_cima"] > 0, (
            f"{versao}: +{AQUECIMENTO_C} °C sustentados por {HORAS_SUSTENTADAS} h em "
            f"{len(janela)} leituras não levantaram um único alarme ({fisico}) — o modelo "
            "não responde à física que deveria estar medindo"
        )
        assert fisico["para_cima"] > fisico["para_baixo"], (
            f"{versao}: aquecer o motor baixou tantas decisões quanto levantou "
            f"({fisico}) — o sentido do efeito está errado"
        )
        assert fisico["taxa"] > sensor["taxa"], (
            f"{versao}: +{AQUECIMENTO_C} °C reais moveram {fisico['taxa'] * 100:.4f}% das "
            f"decisões e ±0,4 °C de ruído moveram {sensor['taxa'] * 100:.4f}% nas MESMAS "
            f"{len(janela)} linhas — o modelo responde ao erro do sensor tanto quanto à física"
        )


# --- contrafactuais: campos que não deveriam mudar a decisão ------------------
#
# Um contrafactual troca **um** campo e mantém o estado físico do motor. Se a decisão muda,
# o modelo está lendo algo que não é o motor. Os três abaixo trocam, cada um, uma coisa que
# a física do equipamento não conhece: quem estava de plantão, em que unidade o CLP reporta
# a pressão, e com que número se preenche o buraco de um sensor que falhou.


def _flip_por_versao(limpo, base, quadro):
    """`{versao: {taxa, para_cima, para_baixo}}` do contrafactual contra a linha de base."""
    saida = {}
    for versao in VERSOES:
        _, _, decisao = harness.prever_sem_vazamento(quadro, versao)
        saida[versao] = perturbacao.taxa_de_flip(base[versao], decisao)
    return saida


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D06 — trocar o técnico de plantão, sem tocar em sensor, faz alarme sumir",
)
def test_trocar_o_operador_senior_nao_muda_a_decisao(_tabela_de_flip, medicoes):
    """Trocar OP-07 por OP-03, com todos os sensores bit-idênticos, não pode mudar nada.

    `operador_senior` marca o técnico que a manutenção **escalou** para o motor. O próprio
    comentário do SUT entrega a causa: "o técnico sênior (OP-07) é escalado para os motores
    mais críticos da planta". Isso não é uma propriedade do motor — é o registro de que
    **alguém já suspeitou da falha**. Um modelo que se apoia nisso não prevê a falha: ele
    detecta que a organização já a percebeu, e some quando a organização ainda não percebeu,
    que é exatamente o caso em que a previsão valeria alguma coisa.

    O contrafactual é fisicamente coerente: mesmo motor, mesmas leituras, outro técnico de
    plantão. Nada no equipamento mudou.
    """
    limpo, base, _ = _tabela_de_flip
    alvo = limpo["id_operador"] == "OP-07"

    trocado = perturbacao.contrafactual(
        limpo, "id_operador", limpo["id_operador"].where(~alvo, "OP-03")
    )
    sensores = ["temperatura_c", "vibracao_rms", "pressao", "corrente_a", "rpm",
                "horas_operacao", "idade_equipamento_meses"]
    assert all(limpo[c].equals(trocado[c]) for c in sensores), (
        "o contrafactual mexeu em algum sensor — deixaria de ser contrafactual"
    )

    flip = _flip_por_versao(limpo, base, trocado)

    # A taxa de falha por operador é o confundidor, e entra na evidência mesmo quando o
    # assert abaixo derruba o teste — por isso é gravada ANTES dele.
    por_operador = limpo.groupby("id_operador")["falha_72h"].mean().round(6)
    medicoes.setdefault("contrafactual", {})["operador"] = flip
    medicoes["contrafactual"]["taxa_falha_por_operador"] = {
        str(k): float(v) for k, v in por_operador.items()
    }

    n = int(alvo.sum())
    detalhe = "; ".join(
        f"{v}: {f['para_cima'] + f['para_baixo']} decisões ({f['para_cima']}↑/"
        f"{f['para_baixo']}↓) — {(f['para_cima'] + f['para_baixo']) / n:.2%} das linhas de OP-07"
        for v, f in flip.items()
    )
    assert all(f["taxa"] == 0 for f in flip.values()), (
        f"trocar OP-07 por OP-03 em {n} leituras, sem tocar em nenhum sensor, mudou: "
        f"{detalhe}. Taxa de falha observada: OP-07 {por_operador['OP-07']:.4f} contra "
        f"{por_operador.drop('OP-07').mean():.4f} na média dos outros onze"
    )


# Vermelho nos TRÊS destinos e nas duas versões (ver `docs/mapa-defeitos.md`, D24), então o
# xfail vai na função — a marca por `pytest.param` é reservada ao defeito que só existe em
# parte dos parâmetros, como D17.
@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D24 — `turno` é função da hora do timestamp e ainda assim move a decisão: "
           "até 10 flips sem confundidor (faixa de 0,71 p.p. entre turnos)",
)
@pytest.mark.parametrize("destino", (1, 2, 3))
def test_trocar_o_turno_nao_muda_a_decisao(destino, _tabela_de_flip, medicoes):
    """Reetiquetar o turno, com todos os sensores bit-idênticos, não pode mudar nada.

    `turno` é a 13ª feature de `ORDEM_FEATURES`, e é a única das treze que nunca teve teste
    nem exclusão justificada. O guia do aluno fecha o bullet dos contrafactuais com *"quais
    campos entram nessa categoria?"* — e este é o caso mais limpo de todos, porque a resposta
    é verificável dentro do próprio dado em vez de depender de um argumento causal.

    **`turno` é função determinística da hora do `timestamp`**: 0–7 → 1, 8–15 → 2, 16–23 → 3,
    sem uma exceção em 4.200 linhas (o assert de premissa abaixo mede isso e derruba o teste
    se deixar de valer). Ou seja, a coluna é uma **reetiquetagem do relógio** — não traz um
    bit de informação física que o timestamp já não trouxesse, e o timestamp o modelo já usa
    para montar as janelas móveis. Um motor não falha porque é o turno 2.

    O contraste com D06 é o que dá peso ao achado. Lá havia um confundidor forte e medido:
    OP-07 falha 0,3988 contra 0,0794 dos outros, então era *explicável* que o modelo se
    apoiasse nele — errado, mas explicável. Aqui a taxa de falha é praticamente plana entre
    os turnos (0,1600 / 0,1550 / 0,1529, uma faixa de 0,71 p.p.), e mesmo assim a decisão se
    move. Não há sinal para o modelo estar lendo: ele está lendo ruído de uma coluna
    redundante.

    O contrafactual mexe **só** em `turno` e deixa o `timestamp` intacto de propósito. Isso
    produz uma linha que a planta não emitiria — e essa é a segunda leitura do mesmo achado:
    nada no serving percebe a incoerência, na mesma família de D21.
    """
    limpo, base, _ = _tabela_de_flip

    hora = pd.to_datetime(limpo["timestamp"]).dt.hour
    ambiguas = int((limpo.groupby(hora)["turno"].nunique() > 1).sum())
    assert ambiguas == 0, (
        f"premissa do oráculo quebrada: {ambiguas} horas do dia mapeiam para mais de um "
        f"turno. Se `turno` deixou de ser função da hora, ele pode carregar informação "
        f"própria e este contrafactual precisa ser redesenhado"
    )

    alvo = limpo["turno"] != destino
    trocado = perturbacao.contrafactual(
        limpo, "turno", limpo["turno"].where(~alvo, destino)
    )
    sensores = ["temperatura_c", "vibracao_rms", "pressao", "corrente_a", "rpm",
                "horas_operacao", "idade_equipamento_meses"]
    assert all(limpo[c].equals(trocado[c]) for c in sensores), (
        "o contrafactual mexeu em algum sensor — deixaria de ser contrafactual"
    )

    flip = _flip_por_versao(limpo, base, trocado)

    por_turno = limpo.groupby("turno")["falha_72h"].mean().round(6)
    medicoes.setdefault("contrafactual", {}).setdefault("turno", {})[str(destino)] = flip
    medicoes["contrafactual"]["taxa_falha_por_turno"] = {
        str(k): float(v) for k, v in por_turno.items()
    }

    n = int(alvo.sum())
    detalhe = "; ".join(
        f"{v}: {f['para_cima'] + f['para_baixo']} decisões "
        f"({f['para_cima']}↑/{f['para_baixo']}↓)"
        for v, f in flip.items()
    )
    faixa = por_turno.max() - por_turno.min()
    assert all(f["taxa"] == 0 for f in flip.values()), (
        f"reetiquetar {n} leituras para o turno {destino}, sem tocar em nenhum sensor e "
        f"sem mexer no timestamp, mudou: {detalhe}. E `turno` é função da hora do "
        f"timestamp, logo não traz informação física nova. Taxa de falha por turno: "
        f"{por_turno.to_dict()} — faixa de apenas {faixa:.4f} ({faixa * 100:.2f} p.p.), "
        f"sem confundidor que explique a dependência"
    )


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D03 — a mesma pressão física em psi e em bar produz decisões diferentes",
)
def test_converter_a_pressao_para_a_outra_unidade_nao_muda_a_decisao(
    _tabela_de_flip, medicoes
):
    """A mesma pressão física, reportada em psi ou em bar, tem de dar a mesma decisão.

    Teste **metamórfico de unidade**, no espírito do Mars Climate Orbiter da aula 3: a
    transformação preserva a grandeza física e a saída tem de ser invariante a ela.
    `limpar` normaliza `unidade_pressao` para minúsculas e **nunca a usa para converter**;
    `construir` consome `pressao` crua. O resultado é que a coluna mistura duas escalas —
    bar por volta de 3,9 e psi por volta de 56,5 — e a floresta aprendeu a cortar entre
    elas. Ela não mede pressão: ela detecta o fabricante do CLP.
    """
    limpo, base, _ = _tabela_de_flip
    em_bar = limpo["unidade_pressao"] == "bar"

    convertido = perturbacao.contrafactual(
        limpo,
        "pressao",
        limpo["pressao"].where(~em_bar, limpo["pressao"] * ficha.FATOR_PSI_POR_BAR),
    )
    convertido = perturbacao.contrafactual(
        convertido, "unidade_pressao", limpo["unidade_pressao"].where(~em_bar, "psi")
    )

    flip = _flip_por_versao(limpo, base, convertido)
    medicoes.setdefault("contrafactual", {})["pressao_unidade"] = flip

    n = int(em_bar.sum())
    detalhe = "; ".join(
        f"{v}: {f['para_cima'] + f['para_baixo']} decisões ({f['para_cima']}↑/{f['para_baixo']}↓)"
        for v, f in flip.items()
    )
    assert all(f["taxa"] == 0 for f in flip.values()), (
        f"converter {n} leituras de bar para psi — multiplicando por "
        f"{ficha.FATOR_PSI_POR_BAR} e declarando a unidade — mudou: {detalhe}. "
        "A pressão física é a mesma; só o rótulo da unidade mudou"
    )


@pytest.mark.adversarial
@pytest.mark.defeito
@pytest.mark.xfail(
    strict=True,
    reason="D04 — a constante que imputa a vibração ausente decide ordens de manutenção",
)
def test_dropout_de_vibracao_nao_muda_as_decisoes_da_janela(_tabela_de_flip, medicoes):
    """O valor com que se tapa o buraco do sensor não pode decidir nada.

    `limpar` preenche a vibração ausente com `0,0` — um valor **fora** da faixa física de
    1,2 a 8,0 mm/s da ficha técnica. Não é um número neutro: para o modelo, "o sensor
    falhou" fica indistinguível de "o eixo parou", e a leitura viaja por até 24 h de janela
    móvel a partir do buraco.

    O oráculo não pergunta se perder uma leitura muda alguma coisa — perder informação pode
    legitimamente mudar. Ele pergunta **se a constante de imputação decide**: as mesmas
    leituras ausentes, preenchidas com o mínimo físico da ficha em vez de 0,0, têm de
    produzir as mesmas ordens de manutenção. O mínimo da ficha é a escolha mais conservadora
    possível — é o valor válido mais próximo de 0,0 —, então qualquer flip aqui é o piso do
    efeito, não o teto.

    O dropout não é hipotético: o historiador já entregou este lote com ~9,7 % das leituras
    de vibração ausentes.
    """
    limpo, base, _ = _tabela_de_flip
    faixa = ficha.FICHA["vibracao_rms"]
    imputadas = limpo["vibracao_rms"] == 0.0

    reimputado = perturbacao.contrafactual(
        limpo, "vibracao_rms", limpo["vibracao_rms"].where(~imputadas, faixa.minimo)
    )

    flip = _flip_por_versao(limpo, base, reimputado)
    medicoes.setdefault("contrafactual", {})["dropout_vibracao"] = flip

    n = int(imputadas.sum())
    detalhe = "; ".join(
        f"{v}: {f['para_cima'] + f['para_baixo']} decisões ({f['para_cima']}↑/{f['para_baixo']}↓)"
        for v, f in flip.items()
    )
    assert all(f["taxa"] == 0 for f in flip.values()), (
        f"trocar a constante de imputação de 0,0 para {faixa.minimo} mm/s — o mínimo "
        f"físico da ficha — nas {n} leituras ausentes ({n / len(limpo):.2%} do lote) "
        f"mudou: {detalhe}. Nenhuma medição nova entrou; só o número que tapa o buraco"
    )


@pytest.mark.adversarial
@pytest.mark.lento
def test_sensibilidade_por_feature_aponta_dependencia_ilegitima(_tabela_de_flip, medicoes):
    """Ranking por perturbação de uma feature por vez — e o que ele revela.

    Duas das treze features não carregam **nenhuma** física do motor: `operador_senior` é
    quem estava de plantão, e `maquina_risco` é um agregado histórico do motor. Se o modelo
    fosse causalmente sadio, as duas ficariam no fim do ranking, atrás das leituras de
    sensor. O teste mede a posição e a registra.

    **A perturbação é ciente do tipo da feature, e isto é o teste.** O primeiro desenho
    somava ruído de ±1 desvio-padrão a todas as treze, e devolveu `operador_senior` com
    `delta_medio = 0,000000` — **em último lugar**, enquanto o contrafactual de D06 virava
    155 decisões com ela. A causa: `operador_senior` é binária, e ruído de ±0,43 em torno de
    0 ou de 1 nunca cruza o corte em 0,5. O instrumento estava cego exatamente à feature que
    interessava. Para uma feature binária a perturbação equivalente a "±1 desvio" é
    **invertê-la**; para as contínuas, o ruído de ±1 desvio se mantém.
    """
    limpo, _, _ = _tabela_de_flip
    X = sn.features.construir(limpo.drop(columns=["falha_72h"]))

    ranking = []
    for versao in VERSOES:
        m = sn.modelo.carregar(versao)
        p0 = m.prever_proba(X)
        medidas = []
        for coluna in X.columns:
            valores = X[coluna].to_numpy()
            if set(np.unique(valores)) <= {0.0, 1.0}:
                perturbado = perturbacao.contrafactual(X, coluna, 1.0 - valores)
            else:
                perturbado = perturbacao.perturbar_coluna(
                    X, coluna, float(X[coluna].std()), seed=42
                )
            medidas.append(
                (coluna, float(np.abs(m.prever_proba(perturbado) - p0).mean()))
            )
        medidas.sort(key=lambda par: -par[1])
        ranking.extend(
            {"versao": versao, "feature": c, "delta_medio": round(d, 6)}
            for c, d in medidas
        )

    medicoes["sensibilidade"] = ranking

    for versao in VERSOES:
        ordem = [r["feature"] for r in ranking if r["versao"] == versao]
        delta = {r["feature"]: r["delta_medio"] for r in ranking if r["versao"] == versao}
        posicao = {f: i + 1 for i, f in enumerate(ordem)}

        # O único assert é sobre `operador_senior`, e é deliberado. A régua não foi
        # escolhida depois de ver o número: "quem estava de plantão pesa mais que qualquer
        # leitura de sensor" é uma afirmação que se sustenta ou não, e ela se sustenta nas
        # duas versões, com folga de 1,7× a 2,1× sobre a segunda colocada.
        #
        # `maquina_risco` NÃO ganha assert aqui: medida, ela fica em 6º (v1) e 7º (v2) de
        # 13 — meio do pelotão. Cravar "metade superior" seria ajustar a régua ao
        # resultado, e o dano dela já está provado por outro caminho, muito mais forte: o
        # experimento de vazamento de alvo do HANDOFF 03 (D02), onde rever 2 rótulos, sem
        # tocar em nenhum sensor, já move probabilidade. A posição fica registrada em
        # `medicoes.json` como medida, não como oráculo.
        assert posicao["operador_senior"] == 1, (
            f"{versao}: `operador_senior` — quem a manutenção escalou, nenhuma física do "
            f"motor — ficou em {posicao['operador_senior']}º de {len(ordem)}, e não em 1º. "
            "Se isso deixou de ser verdade, a evidência central do Bloco C mudou e o "
            f"relatório precisa refazer o argumento. Ranking: {ordem}"
        )
        assert delta["operador_senior"] > delta[ordem[1]], (
            f"{versao}: `operador_senior` ({delta['operador_senior']:.6f}) empatou com "
            f"`{ordem[1]}` ({delta[ordem[1]]:.6f})"
        )
