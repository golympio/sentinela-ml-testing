"""O instrumento do Bloco C: perturbar, trocar um campo, e contar quantas decisões viram.

Três funções, e uma pergunta só por trás das três: **a decisão mudou por um motivo que a
física justifica?** A lição das aulas 4 e 6 é que teste adversarial não é sobre nunca mudar
de opinião — é sobre não mudar por motivo errado. Por isso todo experimento desenhado com
este módulo vem em par: a perturbação ilegítima (que **não** deveria mudar nada) e a
mudança física real (que **deveria** mudar).

## Ruído uniforme, não gaussiano — e isto decide o valor do oráculo

`perturbar_coluna` sorteia em `[-amplitude, +amplitude]`, uniforme. A escolha não é
estética: a afirmação sob teste é "uma perturbação **estritamente menor** que o ruído do
sensor não muda a decisão", com o ruído de ±1,0 °C que a ficha técnica declara (SPEC P9,
`ficha.RUIDO_TEMPERATURA_C`). Uma gaussiana de σ = 0,4 tem cauda infinita: parte dos
sorteios passaria de 1,0 °C, e um flip causado por essa cauda seria **legítimo** — duas
leituras distinguíveis podem mesmo dar ordens diferentes. O oráculo perderia o direito de
chamar aquele flip de defeito. Com o uniforme limitado, `|ruído| <= amplitude` vale para
todas as linhas, por construção, e todo flip observado abaixo de 1,0 °C é indefensável.

## Perturbar **depois** da limpeza

`preprocessamento.limpar` descarta linhas (`rpm >= 1.0`) e imputa vibração ausente com 0,0.
Perturbar o quadro cru misturaria dois efeitos: a linha perturbada pode sumir no filtro, e
um valor perturbado pode ser sobrescrito pela imputação. O contrato deste módulo é receber
um quadro **já limpo** e devolver outro quadro limpo, do mesmo tamanho e com o mesmo índice.
`limpar` é idempotente, então quem for prever depois pode chamar o harness normalmente.

## O índice é parte do experimento

`features.construir` termina em `saida.loc[df.index, ...]`. Um `reset_index` acidental aqui
reordenaria as features em relação a `y` e produziria uma taxa de flip inteiramente
fabricada — que passaria por resultado. Por isso as três funções preservam índice e ordem,
e é isso que o controle negativo de amplitude 0 verifica de verdade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def perturbar_coluna(
    df: pd.DataFrame, coluna: str, amplitude: float, seed: int = 42
) -> pd.DataFrame:
    """Soma ruído uniforme em `[-amplitude, +amplitude]` a uma coluna numérica.

    Uma leitura por linha, independente — é o que acontece quando o mesmo motor é lido de
    novo pelo mesmo sensor: cada amostra carrega o seu próprio erro.

    `amplitude=0` devolve uma cópia numericamente idêntica à entrada. Não é caso
    degenerado, é o **controle negativo do instrumento**: se a taxa de flip não for zero
    aí, o defeito está nesta suíte e não no SUT.

    Não modifica `df`. Preserva índice, ordem e as demais colunas.
    """
    if coluna not in df.columns:
        raise ValueError(f"{coluna}: coluna ausente no lote a perturbar")
    if not pd.api.types.is_numeric_dtype(df[coluna]):
        raise ValueError(f"{coluna}: só faz sentido perturbar coluna numérica")
    if amplitude < 0:
        raise ValueError(f"{coluna}: amplitude negativa não faz sentido ({amplitude})")

    # RNG local, derivado da semente recebida. Nunca o RNG global do numpy: a ordem dos
    # testes passaria a mudar o resultado, que é a causa nº 2 de flaky da aula 6.
    gerador = np.random.default_rng(seed)
    ruido = gerador.uniform(-amplitude, amplitude, size=len(df))

    perturbado = df.copy()
    perturbado[coluna] = df[coluna].to_numpy(dtype=float) + ruido
    return perturbado


def contrafactual(df: pd.DataFrame, coluna: str, valor) -> pd.DataFrame:
    """Troca **uma** coluna, mantendo todo o resto — inclusive o estado físico do motor.

    `valor` escalar substitui a coluna inteira; `valor` com o mesmo comprimento de `df`
    (Series, array ou lista) substitui linha a linha, o que permite mexer só no subconjunto
    que interessa — por exemplo, trocar `OP-07` por `OP-03` sem tocar nos outros operadores.

    Uma Series é alinhada **por posição**, não por rótulo: o lote do experimento costuma vir
    de um recorte e alinhar por rótulo silenciaria a troca em quadros com índice não trivial.

    Quando o contrafactual exige mover duas colunas juntas para preservar a física — a
    pressão e a sua unidade, no teste metamórfico de D03 —, encadeie duas chamadas. Manter
    uma coluna por chamada é o que deixa explícito, na leitura do teste, exatamente o que
    mudou.

    Não modifica `df`. Preserva índice, ordem e as demais colunas.
    """
    if coluna not in df.columns:
        raise ValueError(f"{coluna}: coluna ausente no lote do contrafactual")

    trocado = df.copy()
    if isinstance(valor, (pd.Series, np.ndarray, list, tuple)):
        valores = np.asarray(valor)
        if len(valores) != len(df):
            raise ValueError(
                f"{coluna}: contrafactual com {len(valores)} valores para {len(df)} linhas"
            )
        trocado[coluna] = pd.Series(valores, index=df.index)
    else:
        trocado[coluna] = valor
    return trocado


def taxa_de_flip(pred_a, pred_b) -> dict:
    """Quantas decisões viraram entre dois vetores binários, e **para que lado**.

    Devolve as três chaves que SPEC C8 exige em `medicoes.json → flip`:

    - `taxa` — fração de linhas em que a decisão mudou;
    - `para_cima` — contagem de `0 -> 1`: ordem de manutenção que não existia;
    - `para_baixo` — contagem de `1 -> 0`: **o alarme que some**, e portanto o motor que
      queima. A direção é registrada separada justamente porque as duas não custam o
      mesmo — é a mesma assimetria de 20× que o limiar de custo do Bloco B assume.

    `taxa` é `float` e as contagens são `int`: `medicoes.json` é comparado byte a byte
    entre duas rodadas com a mesma semente (SPEC S13), então tipo importa.
    """
    a = np.asarray(pred_a).ravel().astype(int)
    b = np.asarray(pred_b).ravel().astype(int)
    if a.size != b.size:
        raise ValueError(f"vetores de tamanhos diferentes: {a.size} e {b.size}")
    if a.size == 0:
        raise ValueError("taxa de flip sobre vetor vazio")
    for nome, v in (("pred_a", a), ("pred_b", b)):
        if not np.isin(v, (0, 1)).all():
            raise ValueError(f"{nome}: decisão que não é 0 nem 1")

    para_cima = int(np.sum((a == 0) & (b == 1)))
    para_baixo = int(np.sum((a == 1) & (b == 0)))
    return {
        "taxa": float((para_cima + para_baixo) / a.size),
        "para_cima": para_cima,
        "para_baixo": para_baixo,
    }
